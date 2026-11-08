"""Reloj y acciones de la simulación. El visor solo recibe instantáneas."""
from semaforos import APPROACHES, MODES
from trafico import STEP, TrafficNetwork
from traffic_coordinator import plan


class Simulation:
    def __init__(self, scenario, paused):
        self.network = TrafficNetwork(scenario)
        self.paused = paused
        self.coordination = False
        self.previous_mode = self.network.mode
        self.next_plan = 0.0
        self.accumulator = 0.0
        self.epoch = 0

    def control(self, action, value=None):
        network = self.network
        junction = network.central
        if action in ("pause", "sensor", "coordinate") and type(value) is not bool:
            raise ValueError("El valor debe ser verdadero o falso.")
        if action == "mode":
            if value not in MODES:
                raise ValueError("Estrategia no reconocida.")
            self._coordinate(False)
            network.set_mode(value)
        elif action in ("scenario", "reset", "manual_count"):
            if action == "reset":
                network.load(network.scenario, network.manual_count)
            elif action == "manual_count":
                network.load("manual", value)
            else:
                network.load(value)
            self.epoch += 1
            self.accumulator = self.next_plan = 0.0
        elif action in ("pause", "toggle_pause"):
            self.paused = not self.paused if action == "toggle_pause" else value
            self.accumulator = 0.0
        elif action == "step":
            if not self.paused:
                raise ValueError("Pausa la simulación antes de avanzar un paso.")
            self.network.tick()
        elif action in ("sensor", "toggle_sensor"):
            junction.sensor_enabled = not junction.sensor_enabled if action == "toggle_sensor" else value
            self.next_plan = network.time
        elif action == "pedestrian":
            if not junction.controller.request_pedestrian():
                raise ValueError("Ya hay un paso peatonal solicitado.")
        elif action == "coordinate":
            self._coordinate(value)
        else:
            raise ValueError("Acción no reconocida.")

    def _coordinate(self, enabled):
        if self.coordination == enabled:
            return
        network = self.network
        self.coordination = enabled
        if enabled:
            self.previous_mode = network.mode
            network.set_mode("adaptive")
            self.next_plan = network.time
        else:
            for junction in network.junctions:
                junction.controller.priority = ""
                junction.priority_until = 0
            network.set_mode(self.previous_mode)

    def advance(self, elapsed):
        # Acota la recuperación tras minimizar o bloquear la ventana.
        # El paso físico nunca crece para compensar una caída de FPS.
        if not self.paused:
            self.accumulator = min(self.accumulator + elapsed, STEP * 3)
            while self.accumulator >= STEP - 1e-9:
                self.network.tick()
                self.accumulator -= STEP
        if self.coordination and self.network.time >= self.next_plan:
            decisions = plan(self.network.planning())["decisions"]
            for decision in decisions:
                junction = self.network.junctions[decision["id"] - 1]
                axis = decision["priority"]
                junction.controller.priority = axis
                junction.priority_until = self.network.time + 5 if axis else 0
            self.next_plan = self.network.time + 2.5

    def snapshot(self, command_id, command_error):
        network = self.network
        junction = network.central
        return {"time": network.time, "scenario": network.scenario, "manual_count": network.manual_count,
                "controller": junction.controller.snapshot(),
                "lights": {side: junction.controller.light(side) for side in APPROACHES},
                "cars": [{"id": car.id, "x": car.x, "z": car.z, "yaw": car.yaw, "model": car.model}
                         for car in junction.vehicles],
                "metrics": network.metrics(), "recent_crossings": network.recent_crossings,
                "sensors": junction.sensor_enabled, "paused": self.paused, "coordination": self.coordination,
                "epoch": self.epoch, "ack": command_id, "command_error": command_error}
