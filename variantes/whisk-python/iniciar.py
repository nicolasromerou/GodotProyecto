"""Arranca la simulación Python, el panel y el visor Whisk3D."""
from collections import deque
import logging
import subprocess
import sys
import time

from canal_local import LocalChannel
from api_local import LocalAPI
from configuracion import RESOURCE_DIR, session_dir, user_dir
from conector import ServerConnector
from datos import Telemetry
from simulacion import Simulation
from trafico import APPROACH_FOR_HEADING

ROOT = RESOURCE_DIR
ENGINE = ROOT / "whisk3d" / "whisk3d.exe"
ADAPT_VIEW = "--vista-adaptable"
SCENE = ROOT / "escena" / "FTI_Cruce_I5.w3d"
MAX_VISIBLE = 72
VIEW_INTERVAL = .05
VIEWS = {"barrio": (40, 49), "cruce": (38, 48), "avenida": (158, 40), "cenital": (0, 87)}
VIEWER_MODES = ("fti", "adaptive", "fixed", "python")
VIEWER_SCENARIOS = ("normal", "peak_ns", "peak_ew", "saturation")


class Relay:
    def __init__(self, scenario="normal", start_when_visible=False, high_quality=True):
        self.simulation = Simulation(scenario, paused=start_when_visible)
        self.channel = LocalChannel()
        self.next_id = self.command_id = 0
        self.command_error = ""
        self.state = self.simulation.snapshot(self.command_id, self.command_error)
        self.last_seen = time.monotonic()
        self.next_view = 0.0
        self.pending = deque()
        self.results = {}
        self.slots = {}
        self.set_view("barrio")
        self.viewer_status = None
        self.viewer_last_seen = 0.0
        self.start_when_visible = start_when_visible
        self.high_quality = high_quality
        self.omitted = 0
        self.viewer = None
        self.viewer_started_at = 0.0
        self._viewer_error = ""
        self.log_dir = session_dir()
        self.export_dir = user_dir() / "exportaciones"
        self.data = Telemetry()
        self.api = LocalAPI(self.data)
        self.connector = ServerConnector()
        self._data_next = 0.0
        self._data_ack = -1
        self._closed = False
        self._publish_data()

    def _publish_data(self):
        network = self.simulation.network
        state = dict(self.state)
        cars, junctions = [], []
        for index, ((cx, cz), junction) in enumerate(zip(network.centers, network.junctions), 1):
            junctions.append({"id": index, "x": cx, "z": cz,
                              "sensors_online": junction.sensor_enabled,
                              "controller": junction.controller.snapshot(),
                              "lights": {side: junction.controller.light(side) for side in "NESW"}})
            for car in junction.vehicles:
                cars.append({"id": car.id, "model": car.model, "junction": index,
                             "x": cx + car.x, "z": cz + car.z, "local_x": car.x, "local_z": car.z,
                             "yaw": car.yaw, "speed_kmh": car.speed * 3.6, "wait_seconds": car.waiting,
                             "heading": car.heading, "approach": APPROACH_FOR_HEADING[car.heading],
                             "lane": car.lane, "turn": car.planned_turn})
        state.update(network_vehicles=cars, junctions=junctions, units={
            "position": "m", "speed": "km/h", "time": "s", "yaw": "rad",
            "origin": "I-5", "axes": "X east, Z south; yaw from +Z toward +X",
        })
        connected = self.viewer_connected
        synchronized = (connected and self.viewer_status["epoch"] == state["epoch"]
                        and self.viewer_status["command"] >= state["ack"])
        self.data.publish(state, {"connected": connected, "synchronized": synchronized,
                                 "epoch": self.viewer_status["epoch"] if connected else None,
                                 "command": self.viewer_status["command"] if connected else None,
                                 "rendered": self.viewer_status["count"] if connected else 0,
                                 "omitted": self.omitted,
                                 "camera": {"view": self.view, "azimuth": self.azimuth,
                                            "elevation": self.elevation, "zoom": self.zoom}})
        if self.connector.running:
            self.connector.publish(self.data.snapshot())
        self._data_ack = self.command_id

    def start_api(self, port=0):
        url = self.api.start(port)
        logging.getLogger("fti").info("API local iniciada en %s", url)
        return url

    def stop_api(self):
        self.api.stop()
        logging.getLogger("fti").info("API local detenida")

    def connect_server(self, url, token):
        self.connector.start(url, token)
        self.connector.publish(self.data.snapshot())
        logging.getLogger("fti").info("Conector de servidor iniciado")

    def disconnect_server(self):
        self.connector.stop()
        logging.getLogger("fti").info("Conector de servidor detenido")

    def command(self, action, value=None):
        self.next_id += 1
        self.pending.append({"id": self.next_id, "action": action, "value": value})
        return self.next_id

    def set_view(self, view):
        self.view = view
        self.azimuth, self.elevation = VIEWS[view]
        self.zoom = 100

    def _viewer_action(self, action, value):
        # Códigos del visor nativo (W3dFtiAccion). La simulación resuelve los toggles
        # en orden sobre el estado real, incluso cuando llegan dos seguidos.
        if action in (1, 2, 7, 8):
            self.command({1: "toggle_pause", 2: "reset", 7: "toggle_sensor", 8: "pedestrian"}[action])
        elif action == 3 and 0 <= value < len(VIEWS):
            self.set_view(tuple(VIEWS)[value])
        elif action == 4:
            self.azimuth = (self.azimuth + value) % 360
        elif action == 5:
            self.elevation = max(12, min(87, self.elevation + value))
        elif action == 6:
            self.zoom = max(60, min(175, self.zoom + value))
        elif action == 9 and 0 <= value < len(VIEWER_MODES):
            mode = VIEWER_MODES[value]
            if mode == "python":
                self.command("coordinate", True)
            else:
                self.command("mode", mode)
        elif action == 10 and 0 <= value < len(VIEWER_SCENARIOS):
            self.command("scenario", VIEWER_SCENARIOS[value])

    @property
    def viewer_connected(self):
        return (self.viewer_status is not None and time.monotonic() - self.viewer_last_seen < 2.0
                and (self.viewer is None or self.viewer.poll() is None))

    @property
    def viewer_error(self):
        if self._viewer_error:
            return self._viewer_error
        code = self.viewer.poll() if self.viewer is not None else None
        if code not in (None, 0):
            return f"Whisk3D se cerró con código {code}. Revisa whisk-launch.log."
        return ""

    def viewer_command(self, *args):
        quality = ["--fti-calidad-alta"] if self.high_quality else []
        return [str(ENGINE), ADAPT_VIEW, *quality, "--fti-canal", self.channel.name, *args]

    def launch_viewer(self, *, restart=False):
        if self.viewer is not None and self.viewer.poll() is None and not restart:
            return self.viewer
        try:
            if self.viewer is not None:
                stop(self.viewer)
                # Descarta confirmaciones y acciones del proceso anterior.
                replacement = LocalChannel()
                self.channel.close()
                self.channel = replacement
            self.viewer_status = None
            self.viewer_last_seen = self.viewer_started_at = self.next_view = 0.0
            with (self.log_dir / "whisk-launch.log").open("wb") as log:
                self.viewer = subprocess.Popen(self.viewer_command("--open", str(SCENE), "--juego"),
                                               cwd=self.log_dir, stdout=log, stderr=subprocess.STDOUT,
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.TimeoutExpired) as error:
            self._viewer_error = f"No se pudo abrir Whisk3D: {error}"
            raise OSError(self._viewer_error) from error
        self._viewer_error = ""
        self.viewer_started_at = time.monotonic()
        return self.viewer

    def _viewer_state(self):
        state = self.state
        live = {(car["model"], car["id"]) for car in state["cars"]}
        self.slots = {key: slot for key, slot in self.slots.items() if key in live}
        used = {}
        for (model, _), slot in self.slots.items():
            used.setdefault(model, set()).add(slot)
        frame = []
        for car in state["cars"]:
            if len(frame) == MAX_VISIBLE:
                break
            model = car["model"]
            key = (model, car["id"])
            taken = used.setdefault(model, set())
            if key not in self.slots:
                slot = next((index for index in range(1, MAX_VISIBLE + 1) if index not in taken), None)
                if slot is None:
                    continue
                self.slots[key] = slot
                taken.add(slot)
            frame.append({**car, "id": int(car["id"]), "slot": self.slots[key]})
        self.omitted = len(state["cars"]) - len(frame)
        controller = state["controller"]
        mode = controller["running_mode"]
        if controller["fallback"] and mode == "fixed":
            mode = "fallback"
        elif state["coordination"] and mode == "adaptive":
            mode = "python"
        return {"time": state["time"], "epoch": state["epoch"], "cars": frame,
                "lights": state["lights"], "view": self.view,
                "azimuth": self.azimuth, "elevation": self.elevation, "zoom": self.zoom,
                "command": state["ack"], "paused": state["paused"], "sensors": state["sensors"],
                "scenario": state["scenario"], "mode": mode}

    def pump(self):
        now = time.monotonic()
        elapsed = now - self.last_seen
        self.last_seen = now
        if self.viewer is None or self.viewer.poll() is None:
            ack = self.channel.read_ack()
            if ack and (not self.viewer_status or ack["sequence"] > self.viewer_status["sequence"]):
                self.viewer_status = ack
                self.viewer_last_seen = now
            for action, value in self.channel.read_actions():
                self._viewer_action(action, value)
        paused_before = self.simulation.paused
        epoch_before = self.simulation.epoch
        while self.pending:
            command = self.pending.popleft()
            try:
                self.simulation.control(command["action"], command["value"])
                if command["action"] in ("pause", "toggle_pause"):
                    self.start_when_visible = False
                self.command_error = ""
            except ValueError as error:
                self.command_error = str(error)
            self.command_id = command["id"]
            self.results[self.command_id] = self.command_error
            logging.getLogger("fti").debug("Acción %s id=%s error=%s", command["action"],
                                           self.command_id, self.command_error)
            if len(self.results) > 48:
                del self.results[next(iter(self.results))]
        if self.start_when_visible and self.viewer_connected and self.viewer_status["epoch"] == self.simulation.epoch:
            self.simulation.control("pause", False)
            self.start_when_visible = False
        self.simulation.advance(0.0 if paused_before or epoch_before != self.simulation.epoch else elapsed)
        self.state = self.simulation.snapshot(self.command_id, self.command_error)
        if now >= self.next_view and self.channel.publish(self._viewer_state()):
            if now >= self.next_view + VIEW_INTERVAL:
                self.next_view = now
            self.next_view += VIEW_INTERVAL
        if now >= self._data_next or self._data_ack != self.command_id:
            self._publish_data()
            self._data_next = now + .1

    def close(self):
        if self._closed:
            return
        self._closed = True
        for action in (self.connector.close, self.api.stop, lambda: stop(self.viewer), self.channel.close):
            try:
                action()
            except (OSError, RuntimeError):
                logging.getLogger("fti").exception("Error al cerrar un recurso de la sesión")


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def main():
    from launcher import main as launch
    launch()


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, ImportError) as error:
        sys.exit(f"No se pudo iniciar la demo: {error}")
