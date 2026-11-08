"""Comprueba la simulación Python y su enlace real con Whisk3D."""
import argparse
import ctypes
from ctypes import wintypes
import subprocess
import time

from iniciar import SCENE, Relay, stop

PRESETS = (("normal", 36, 4), ("moderate", 90, 10), ("peak_ns", 180, 20),
           ("peak_ew", 180, 20), ("saturation", 324, 36))


def wait_until(relay, predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        relay.pump()
        if predicate(relay.state):
            return
        time.sleep(.025)
    state = relay.state
    summary = {key: state[key] for key in ("scenario", "time", "paused", "epoch", "ack", "command_error")}
    raise RuntimeError(f"No se alcanzó el estado esperado. Python {summary}. Whisk3D {relay.viewer_status}")


class ViewerInput:
    """Envía entradas de prueba únicamente a la ventana del visor lanzado."""
    def __init__(self, pid):
        self.pid = pid
        self.handle = None
        self.win = ctypes.WinDLL("user32", use_last_error=True)
        self.win.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        self.win.PostMessageW.restype = wintypes.BOOL
        self.win.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self.win.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)

    def find(self):
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @callback_type
        def check(handle, _data):
            owner = wintypes.DWORD()
            self.win.GetWindowThreadProcessId(handle, ctypes.byref(owner))
            if owner.value == self.pid:
                title = ctypes.create_unicode_buffer(300)
                self.win.GetWindowTextW(handle, title, len(title))
                if title.value.startswith("FTI I-5"):
                    self.handle = handle
                    return False
            return True

        self.win.EnumWindows(check, 0)
        return self.handle is not None

    def post(self, message, key, flags):
        if not self.handle or not self.win.PostMessageW(self.handle, message, key, flags):
            raise RuntimeError(f"No se pudo enviar la entrada {message} al visor de prueba.")

    def key(self, key):
        scancode = self.win.MapVirtualKeyW(key, 0) << 16
        if 0x25 <= key <= 0x28:
            scancode |= 0x01000000
        self.post(0x100, key, 1 | scancode)
        self.post(0x101, key, 1 | scancode | 0xC0000000)

    def wheel(self, ticks):
        self.post(0x20A, ((ticks * 120) & 0xFFFF) << 16, 0)


def applied(relay, command, **expected):
    wait_until(relay, lambda s: s["ack"] >= command and relay.viewer_connected
               and relay.viewer_status["command"] >= command
               and all(relay.viewer_status[k] == v for k, v in expected.items()))


def controls(relay):
    assert relay.state["metrics"]["vehicles"] == 36
    rejected = relay.command("scenario", "inexistente")
    wait_until(relay, lambda s: s["ack"] == rejected)
    assert relay.results[rejected] and relay.state["scenario"] == "normal"
    rejected = relay.command("pause", "false")
    wait_until(relay, lambda s: s["ack"] == rejected)
    assert relay.results[rejected] and not relay.state["paused"]
    relay.command("scenario", "peak_ns")
    relay.command("coordinate", True)
    wait_until(relay, lambda s: s["metrics"]["vehicles"] == 180 and len(s["cars"]) >= 18 and s["coordination"]
               and s["controller"]["mode"] == "adaptive" and s["ack"] >= 3)
    relay.command("sensor", False)
    wait_until(relay, lambda s: s["controller"]["fallback"] and s["controller"]["running_mode"] == "fixed")
    relay.command("sensor", True)
    wait_until(relay, lambda s: not s["controller"]["fallback"])
    relay.command("pause", True)
    wait_until(relay, lambda s: s["paused"])
    paused_time = relay.state["time"]
    last_state = relay.last_seen
    wait_until(relay, lambda s: relay.last_seen >= last_state + .3 and s["time"] == paused_time)
    relay.command("step")
    wait_until(relay, lambda s: s["time"] > paused_time)
    assert relay.state["paused"] and abs(relay.state["time"] - paused_time - 1 / 30) < 1e-8
    relay.command("scenario", "empty")
    relay.command("mode", "fixed")
    relay.command("pause", False)
    wait_until(relay, lambda s: s["metrics"]["vehicles"] == 0 and not s["paused"] and not s["coordination"]
               and s["controller"]["mode"] == "fixed")
    relay.command("mode", "fti")
    relay.command("scenario", "normal")
    wait_until(relay, lambda s: s["metrics"]["vehicles"] == 36 and s["controller"]["mode"] == "fti"
               and s["time"] > 4)
    relay.command("scenario", "empty")
    relay.command("pedestrian")
    wait_until(relay, lambda s: s["controller"]["stage"] == "WALK")
    assert set(relay.state["lights"].values()) == {"RED"}
    print("CONTROL_OK: comandos rechazados, escenarios, pausa, coordinación, paso peatonal y respaldo fijo.")


def demand_controls(relay):
    for key, total, visible in PRESETS:
        applied(relay, relay.command("scenario", key), scenario=key, count=visible)
        assert relay.state["metrics"]["vehicles"] == total
    for count in (0, 17, 36):
        applied(relay, relay.command("manual_count", count), scenario="manual", count=count)
        assert relay.state["manual_count"] == count and len(relay.state["cars"]) == count
    rejected = relay.command("manual_count", -1)
    applied(relay, rejected, scenario="manual", count=36)
    assert relay.results[rejected] and relay.state["manual_count"] == 36
    applied(relay, relay.command("reset"), scenario="manual", count=36)
    assert relay.state["manual_count"] == 36
    print("DEMANDA_OK: cinco perfiles, cantidades manuales de 0, 17 y 36, rechazo y reinicio.")


def render(relay):
    relay.command("mode", "adaptive")
    relay.command("scenario", "saturation")
    wait_until(relay, lambda s: s["scenario"] == "saturation" and s["time"] > 4)
    relay.command("pause", True)
    wait_until(relay, lambda s: s["paused"] and len(s["cars"]) == 36)
    with (SCENE.parent / "verificar-editor.log").open("wb") as log:
        viewer = subprocess.Popen(relay.viewer_command("--script", "verificar.w3s"), cwd=SCENE.parent,
                                  stdout=log, stderr=subprocess.STDOUT)
        try:
            wait_until(relay, lambda _: viewer.poll() is not None, seconds=50)
        finally:
            if viewer.poll() is None:
                viewer.kill()
                viewer.wait(timeout=3)
    output = (SCENE.parent / "verificar-editor.log").read_text(encoding="utf-8", errors="replace")
    if viewer.returncode != 0 or "=== TEST OK" not in output:
        raise RuntimeError(output[-5500:])
    if not relay.viewer_status or relay.viewer_status["count"] != 36 or relay.omitted:
        raise RuntimeError("Faltaron instancias del visor para mostrar los autos de I-5.")
    print("\n".join(line for line in output.splitlines()
                    if "fti_" in line or "=== TEST" in line))


def interactive(high_quality=True):
    relay = Relay(scenario="saturation", start_when_visible=True, high_quality=high_quality)
    try:
        assert relay.state["paused"] and relay.state["metrics"]["vehicles"] == 324
        viewer = relay.launch_viewer()
        wait_until(relay, lambda _: relay.viewer_connected, seconds=35)
        assert relay.viewer_status["count"] == 36 and viewer.poll() is None
        wait_until(relay, lambda s: not s["paused"] and s["time"] >= 1)
        native = ViewerInput(viewer.pid)
        wait_until(relay, lambda _: native.find())
        native.key(0x20)  # Espacio en Whisk: pausa del reloj Python y confirmación del visor.
        wait_until(relay, lambda s: s["paused"] and relay.viewer_status["paused"])
        frozen = relay.state["time"]
        after = time.monotonic() + .35
        wait_until(relay, lambda s: time.monotonic() >= after and s["time"] == frozen)
        applied(relay, relay.command("pause", False), paused=False)
        start = relay.next_id
        native.key(0x20)
        native.key(0x20)
        wait_until(relay, lambda s: s["ack"] >= start + 2 and not s["paused"]
                   and relay.viewer_status["command"] >= start + 2 and not relay.viewer_status["paused"])
        applied(relay, relay.command("pause", True), paused=True)
        demand_controls(relay)
        old_epoch = relay.state["epoch"]
        native.key(ord("R"))
        wait_until(relay, lambda s: s["epoch"] > old_epoch and s["time"] == 0
                   and relay.viewer_status["epoch"] == s["epoch"])
        native.key(0x78)  # F9: Normal
        wait_until(relay, lambda s: s["scenario"] == "normal" and relay.viewer_status["scenario"] == "normal"
                   and relay.viewer_status["count"] == 4)
        native.key(ord("S"))
        wait_until(relay, lambda s: not s["sensors"] and not relay.viewer_status["sensors"])
        applied(relay, relay.command("sensor", True), sensors=True)
        native.key(ord("2"))
        wait_until(relay, lambda _: relay.view == "cruce" and relay.viewer_status["view"] == "cruce")
        native.key(0x27)  # flecha derecha
        native.wheel(1)
        wait_until(relay, lambda _: relay.azimuth == 48 and relay.zoom == 110
                   and relay.viewer_status["azimuth"] == 48 and relay.viewer_status["zoom"] == 110)
        for view, angle, elevation in (("cruce", 100, 24), ("avenida", 205, 35), ("cenital", 315, 87), ("barrio", 0, 52)):
            relay.set_view(view)
            relay.azimuth, relay.elevation = angle, elevation
            wait_until(relay, lambda _: relay.viewer_status["view"] == view
                       and relay.viewer_status["azimuth"] == angle and relay.viewer_status["elevation"] == elevation)
        relay.command("scenario", "empty")
        wait_until(relay, lambda s: relay.viewer_status["epoch"] == s["epoch"] and relay.viewer_status["count"] == 0)
        native.key(ord("P"))
        wait_until(relay, lambda s: s["controller"]["pedestrian_pending"])
        applied(relay, relay.command("pause", False), paused=False)
        wait_until(relay, lambda s: s["controller"]["stage"] == "WALK"
                   and set(relay.viewer_status["lights"].values()) == {"RED"})
        applied(relay, relay.command("pause", True), paused=True)
        native.key(0x7B)  # F12: Saturación
        wait_until(relay, lambda s: relay.viewer_status["epoch"] == s["epoch"] and relay.viewer_status["count"] == 36)
        stop(viewer)
        wait_until(relay, lambda _: not relay.viewer_connected, seconds=5)
        relay.launch_viewer()
        wait_until(relay, lambda _: relay.viewer_connected and relay.viewer_status["count"] == 36, seconds=35)
        native = ViewerInput(relay.viewer.pid)
        wait_until(relay, lambda _: native.find())
        native.key(0x77)  # F8: Coordinado
        wait_until(relay, lambda s: s["coordination"])
        relay.command("pause", False)
        green_axes = set()

        def sustained_flow(state):
            for axis, sides in (("NS", "NS"), ("EW", "EW")):
                if any(state["lights"][side] == "GREEN" for side in sides):
                    green_axes.add(axis)
            return (state["coordination"] and len(green_axes) == 2 and relay.viewer_connected
                    and state["metrics"]["crossings"] >= 50 and not relay.omitted)

        wait_until(relay, sustained_flow, seconds=55)
        print("SINCRONIA_OK: pausa doble y reanudación, reinicio, escenarios, sensores, paso peatonal, cuatro vistas, flechas, rueda y reapertura.")
        print(f"COORDINADO_OK: {relay.state['metrics']['crossings']} cruces y ambos ejes de I-5 habilitados.")
    finally:
        relay.close()


def panel_controls(high_quality):
    import tkinter as tk

    from panel import TrafficPanel

    relay = Relay(scenario="saturation", start_when_visible=True, high_quality=high_quality)
    try:
        root = tk.Tk()
        try:
            viewer = relay.launch_viewer()
            panel = TrafficPanel(root, relay)
            root.geometry("720x680")
            exercise_panel(root, panel, relay, viewer)
        finally:
            root.destroy()
    finally:
        relay.close()


def exercise_panel(root, panel, relay, viewer):
    def until(predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            root.update()
            if panel.error:
                raise panel.error
            if predicate():
                return
            time.sleep(.02)
        raise RuntimeError(f"El panel no alcanzó el estado esperado. {panel.status['text']} | {panel.feedback['text']}")

    def click(button):
        until(lambda: button.winfo_ismapped() and button.instate(["!disabled"]))
        x, y = button.winfo_width() // 2, button.winfo_height() // 2
        button.event_generate("<Enter>", x=x, y=y)
        button.event_generate("<ButtonPress-1>", x=x, y=y)
        button.event_generate("<ButtonRelease-1>", x=x, y=y)
        root.update()

    def confirmed(**expected):
        return (panel.pending is None and relay.viewer_connected
                and all(relay.viewer_status[key] == value for key, value in expected.items()))

    until(lambda: confirmed(count=36, paused=False), seconds=45)
    click(panel.pause)
    until(lambda: confirmed(paused=True))
    for key, total, count in PRESETS:
        click(panel.scenario_buttons[key])
        until(lambda: confirmed(scenario=key, count=count))
        assert relay.state["metrics"]["vehicles"] == total and panel.scenario.get() == key

    root.geometry("350x630")
    until(lambda: panel.layout_mode == (True, True))
    for button in panel.scenario_buttons.values():
        assert button.winfo_x() + button.winfo_width() <= button.master.winfo_width()
    click(panel.scenario_buttons["manual"])
    before = relay.next_id
    panel.manual_count.set("37")
    click(panel.manual_apply)
    assert relay.next_id == before and "36" in panel.feedback["text"]
    panel.manual_count.set("17")
    click(panel.manual_apply)
    until(lambda: confirmed(scenario="manual", count=17))

    root.geometry("720x680")
    for key in ("fti", "adaptive", "fixed", "python"):
        click(panel.mode_buttons[key])
        until(lambda: panel.pending is None and panel.mode.get() == key
              and (relay.state["coordination"] if key == "python" else relay.state["controller"]["mode"] == key))
    click(panel.navigation_buttons["view_section"])
    for view in ("cruce", "cenital", "avenida", "barrio"):
        click(panel.view_buttons[view])
        until(lambda: confirmed(view=view))
    native = ViewerInput(viewer.pid)
    until(native.find)
    native.key(ord("3"))
    native.wheel(2)
    until(lambda: confirmed(view="avenida", zoom=120) and panel.view.get() == "avenida" and panel.zoom.get() == 120)

    click(panel.navigation_buttons["test_section"])
    for enabled in (False, True):
        click(panel.sensor)
        until(lambda: confirmed(sensors=enabled))
    click(panel.pedestrian)
    until(lambda: panel.pending is None and relay.state["controller"]["pedestrian_pending"])
    click(panel.pause)
    until(lambda: confirmed(paused=False, count=17) and relay.state["controller"]["stage"] == "WALK")
    assert set(relay.viewer_status["lights"].values()) == {"RED"}

    stop(viewer)
    until(lambda: not relay.viewer_connected and panel.reopen.instate(["!disabled"]))
    click(panel.reopen)
    until(lambda: confirmed(count=17, scenario="manual"), seconds=45)
    print("PANEL_OK: clics en demanda, modo manual a 350 px, estrategias, cámara, sensores, peatones y reapertura.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--arranque", action="store_true", help="Abre el visor con el lanzador real y comprueba la reapertura")
    parser.add_argument("--panel", action="store_true", help="Prueba el panel Tk y sus controles con el visor")
    parser.add_argument("--calidad", choices=("normal", "alta"), default="alta")
    args = parser.parse_args()
    high_quality = args.calidad == "alta"
    relay = Relay(high_quality=high_quality)
    try:
        controls(relay)
        if args.render:
            render(relay)
    finally:
        relay.close()
    if args.arranque:
        interactive(high_quality)
    if args.panel:
        panel_controls(high_quality)


if __name__ == "__main__":
    main()
