"""Lanzador gráfico de FTI desde el código fuente."""
import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter import font as tkfont
import urllib.request

from configuracion import (
    RESOURCE_DIR, VERSION, check_resources, configure_logging, load_settings,
    save_settings, user_dir,
)

BACKGROUND = "#101a24"
CARD = "#1a2836"
TEXT = "#f2f6fa"
SECONDARY = "#b0c2d1"
ACCENT = "#67dfbd"


def open_folder(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    os.startfile(path)


class Launcher:
    def __init__(self, root, settings=None):
        self.root = root
        self.settings = dict(settings or load_settings())
        self.relay = None
        self.panel = None
        self.restart = False
        self.starting = False
        self.wheel_delta = 0
        root.title(f"FTI · Preparar simulación · {VERSION}")
        root.configure(bg=BACKGROUND)
        root.protocol("WM_DELETE_WINDOW", self.finish)
        root.report_callback_exception = self.callback_error
        icon = RESOURCE_DIR / "FTI.ico"
        if icon.is_file():
            root.iconbitmap(str(icon))
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("FTIL.TButton", font=("Segoe UI", 10), padding=(12, 8),
                        background="#26394a", foreground=TEXT)
        style.configure("Start.FTIL.TButton", font=("Segoe UI", 11, "bold"),
                        background=ACCENT, foreground="#09251f", borderwidth=0)
        style.map("Start.FTIL.TButton", background=[("disabled", "#26394a"), ("active", "#99ead5")])
        style.configure("FTIL.TRadiobutton", background=CARD, foreground=TEXT, padding=(7, 7),
                        font=("Segoe UI", 10), indicatorcolor="#26394a")
        style.map("FTIL.TRadiobutton", background=[("active", "#26394a")])
        style.configure("FTIL.TCheckbutton", background=CARD, foreground=TEXT,
                        font=("Segoe UI", 10), padding=(5, 6))
        style.map("FTIL.TCheckbutton", background=[("active", CARD)])

        self.frame = tk.Frame(root, bg=BACKGROUND, padx=20, pady=18)
        self.frame.pack(fill="both", expand=True)
        self.header = tk.Frame(self.frame, bg=BACKGROUND)
        self.header.pack(fill="x")
        self.brand = self._label(self.header, "FTI  /  TRÁFICO INTELIGENTE", ACCENT, 9, True)
        self.brand.pack(anchor="w")
        self.heading = self._label(self.header, "Preparar simulación", TEXT, 24, True)
        self.title_font = tkfont.Font(root=root, family="Segoe UI", size=24, weight="bold")
        self.heading.configure(font=self.title_font)
        self.heading.pack(anchor="w", pady=(6, 2))
        self.intro = self._label(self.header, "Configura el tráfico y abre una sesión.", SECONDARY)
        self.intro.pack(fill="x")
        self.footer = tk.Frame(self.frame, bg=BACKGROUND)
        self.footer.pack(side="bottom", fill="x")
        scroll = tk.Frame(self.frame, bg=BACKGROUND)
        scroll.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(scroll, bg=BACKGROUND, highlightthickness=0, yscrollincrement=1)
        self.scrollbar = ttk.Scrollbar(scroll, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.form = tk.Frame(self.canvas, bg=BACKGROUND)
        self.form_window = self.canvas.create_window(0, 0, anchor="nw", window=self.form)
        self.form.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._form_resize)

        self.scenario = tk.StringVar(value=self.settings["scenario"])
        self.strategy = tk.StringVar(value=self.settings["strategy"])
        self.quality = tk.StringVar(value=self.settings["quality"])
        self.viewer = tk.BooleanVar(value=self.settings["viewer"])
        self.api = tk.BooleanVar(value=self.settings["api"])
        self.api_port = tk.StringVar(value=str(self.settings["api_port"]))
        self.option_rows = []
        self.section_titles = []
        self._options("Demanda de tráfico", {
            "normal": "Normal · 36", "moderate": "Moderado · 90",
            "peak_ns": "Punta N–S · 180", "peak_ew": "Punta E–O · 180",
            "saturation": "Saturación · 324",
        }, self.scenario, 3)
        self._options("Estrategia inicial", {
            "fti": "FTI", "adaptive": "Adaptativo", "fixed": "Fijo", "python": "Coordinado",
        }, self.strategy, 4)
        self._options("Calidad de visualización", {
            "alta": "Alta · MSAA hasta 8×", "normal": "Estándar",
        }, self.quality, 2)
        services = self._section("Servicios de la sesión")
        ttk.Checkbutton(services, text="Abrir visor 3D", variable=self.viewer,
                        style="FTIL.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(services, text="API local de lectura", variable=self.api, command=self._api_state,
                        style="FTIL.TCheckbutton").pack(anchor="w")
        self.port_row = tk.Frame(services, bg=CARD)
        self.port_row.pack(fill="x")
        self.port_caption = self._label(self.port_row, "Puerto · 0 automático", SECONDARY, background=CARD)
        self.port_input = ttk.Entry(self.port_row, width=7, textvariable=self.api_port)
        self._api_state()
        self.status = self._label(self.footer, "", SECONDARY, 9)
        self.status.configure(wraplength=650, justify="left")
        self.status.pack(fill="x", pady=(12, 6))
        self.actions = tk.Frame(self.footer, bg=BACKGROUND)
        self.actions.pack(fill="x")
        self.start_button = ttk.Button(self.actions, text="Iniciar sesión", command=self.start,
                                       style="Start.FTIL.TButton")
        self.logs_button = ttk.Button(self.actions, text="Abrir registros", command=lambda: open_folder(user_dir() / "logs"),
                                      style="FTIL.TButton")
        root.bind("<Return>", lambda _event: self.start())
        self.resize_binding = root.bind("<Configure>", self._resize, add="+")
        self.wheel_binding = root.bind("<MouseWheel>", self._scroll, add="+")
        self.focus_binding = root.bind("<FocusIn>", self._scroll_to_focus, add="+")
        root.minsize(380, 430)
        root.geometry(f"{min(760, root.winfo_screenwidth()-50)}x{min(690, root.winfo_screenheight()-80)}")
        try:
            count = check_resources()
            self.status.configure(text=f"Recursos listos · {count} modelos.")
        except (OSError, ValueError, RuntimeError) as error:
            self.status.configure(text=str(error), fg="#ff9c9c")
            self.start_button.state(["disabled"])

    @staticmethod
    def _label(parent, text, color=TEXT, size=10, bold=False, *, background=BACKGROUND):
        return tk.Label(parent, text=text, bg=background, fg=color, anchor="w",
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def _section(self, title):
        frame = tk.Frame(self.form, bg=CARD, padx=12, pady=8)
        frame.pack(fill="x", pady=(10, 0))
        heading = self._label(frame, title, TEXT, 10, True, background=CARD)
        heading.pack(fill="x", pady=(0, 3))
        self.section_titles.append(heading)
        return frame

    def _options(self, title, choices, variable, columns):
        section = self._section(title)
        row = tk.Frame(section, bg=CARD)
        row.pack(fill="x")
        buttons = [ttk.Radiobutton(row, text=label, variable=variable, value=key,
                                    style="FTIL.TRadiobutton") for key, label in choices.items()]
        self.option_rows.append((row, buttons, columns))

    def _resize(self, event):
        if event.widget is not self.root or self.relay is not None:
            return
        width = max(1, self.root.winfo_width() - 40)
        title_size = 24
        self.title_font.configure(size=title_size)
        while title_size > 14 and self.title_font.measure("Preparar simulación") > width:
            title_size -= 1
            self.title_font.configure(size=title_size)
        for label in (self.brand, self.heading, self.intro, self.status):
            label.configure(wraplength=width, justify="left")
        narrow = self.start_button.winfo_reqwidth() + self.logs_button.winfo_reqwidth() + 12 > width
        self.actions.columnconfigure(0, weight=1)
        self.actions.columnconfigure(1, weight=int(not narrow))
        self.start_button.grid(row=0, column=0 if narrow else 1, sticky="ew" if narrow else "e")
        self.logs_button.grid(row=int(narrow), column=0, sticky="ew" if narrow else "w", pady=(5, 0) if narrow else 0)
        minimum_height = self.header.winfo_reqheight() + self.footer.winfo_reqheight() + 140
        self.root.minsize(380, min(minimum_height, max(430, self.root.winfo_screenheight() - 80)))

    def _form_resize(self, event):
        if self.relay is not None:
            return
        self.canvas.itemconfigure(self.form_window, width=event.width)
        width = max(1, event.width - 24)
        for heading in self.section_titles:
            heading.configure(wraplength=width, justify="left")
        self.port_caption.configure(wraplength=width, justify="left")
        stacked = self.port_caption.winfo_reqwidth() + self.port_input.winfo_reqwidth() + 12 > width
        self.port_caption.grid(row=0, column=0, sticky="w")
        self.port_input.grid(row=int(stacked), column=0 if stacked else 1, sticky="w" if stacked else "e",
                             pady=(4, 0) if stacked else 0)
        self.port_row.columnconfigure(0, weight=1)
        for row, buttons, maximum in self.option_rows:
            item_width = max(button.winfo_reqwidth() for button in buttons) + 4
            columns = max(1, min(maximum, width // item_width))
            for column in range(maximum):
                row.columnconfigure(column, weight=int(column < columns), uniform="launch" if column < columns else "")
            for index, button in enumerate(buttons):
                line, column = divmod(index, columns)
                button.grid(row=line, column=column, sticky="w")

    def _api_state(self):
        self.port_input.state(["!disabled"] if self.api.get() else ["disabled"])

    def _scroll(self, event):
        self.wheel_delta += event.delta
        steps = int(self.wheel_delta / 120)
        if steps:
            self.wheel_delta -= steps * 120
            self.canvas.yview_scroll(-steps * 60, "units")
        return "break"

    def _scroll_to_focus(self, event):
        if not str(event.widget).startswith(f"{self.form}."):
            return
        top = event.widget.winfo_rooty() - self.form.winfo_rooty()
        bottom = top + event.widget.winfo_height()
        visible = self.canvas.canvasy(0)
        height = self.canvas.winfo_height()
        if top < visible or bottom > visible + height:
            offset = top - 8 if top < visible else bottom - height + 8
            self.canvas.yview_moveto(max(0, offset) / max(1, self.form.winfo_height()))

    def start(self):
        if self.starting or self.start_button.instate(["disabled"]):
            return
        try:
            check_resources()
            port = int(self.api_port.get()) if self.api.get() else self.settings["api_port"]
            if self.api.get() and not 0 <= port <= 65535:
                raise ValueError("El puerto local debe estar entre 0 y 65535.")
        except (ValueError, OSError, RuntimeError) as error:
            self.status.configure(text=str(error), fg="#ff9c9c")
            return
        self.settings.update(scenario=self.scenario.get(), strategy=self.strategy.get(),
                             quality=self.quality.get(), viewer=self.viewer.get(),
                             api=self.api.get(), api_port=port)
        self.starting = True
        self.start_button.state(["disabled"])
        self.status.configure(text="Preparando la sesión…", fg=ACCENT)
        self.root.after(20, self._open_session)

    def _open_session(self):
        relay = None
        try:
            from iniciar import Relay
            from panel import TrafficPanel

            relay = Relay(self.settings["scenario"], start_when_visible=self.settings["viewer"],
                          high_quality=self.settings["quality"] == "alta")
            if self.settings["strategy"] == "python":
                relay.command("coordinate", True)
            else:
                relay.command("mode", self.settings["strategy"])
            relay.pump()
            if self.settings["api"]:
                relay.start_api(self.settings["api_port"])
            if self.settings["viewer"]:
                try:
                    relay.launch_viewer()
                except OSError:
                    logging.getLogger("fti").exception("El visor no pudo abrirse; se mantiene el panel")
            try:
                save_settings(self.settings)
            except OSError:
                logging.getLogger("fti").exception("No se pudieron guardar las preferencias")
        except (OSError, RuntimeError, ValueError, ImportError) as error:
            if relay is not None:
                relay.close()
            self.starting = False
            self.start_button.state(["!disabled"])
            self.status.configure(text=str(error), fg="#ff9c9c")
            logging.getLogger("fti").exception("No se pudo preparar la sesión")
            return
        self.relay = relay
        self.frame.destroy()
        self.root.unbind("<Return>")
        self.root.unbind("<Configure>", self.resize_binding)
        self.root.unbind("<MouseWheel>", self.wheel_binding)
        self.root.unbind("<FocusIn>", self.focus_binding)
        self.panel = TrafficPanel(self.root, relay)
        menu = tk.Menu(self.root)
        session = tk.Menu(menu, tearoff=False)
        session.add_command(label="Nueva sesión", command=lambda: self.finish(restart=True))
        session.add_command(label="Abrir exportaciones", command=lambda: open_folder(relay.export_dir))
        session.add_command(label="Abrir registros", command=lambda: open_folder(relay.log_dir))
        session.add_separator()
        session.add_command(label="Salir", command=self.finish)
        menu.add_cascade(label="Sesión", menu=session)
        self.root.configure(menu=menu)
        logging.getLogger("fti").info("Sesión iniciada escenario=%s estrategia=%s",
                                      self.settings["scenario"], self.settings["strategy"])

    def finish(self, restart=False):
        if self.relay is not None:
            try:
                folder = self.relay.export_dir
                folder.mkdir(parents=True, exist_ok=True)
                name = self.relay.data.session_id
                self.relay.data.export_history(folder / f"sesion-{name}.json")
                self.relay.data.export_snapshot(folder / f"estado-{name}.json")
            except (OSError, ValueError) as error:
                logging.getLogger("fti").exception("No se pudo guardar la sesión al salir")
                if not messagebox.askyesno("Guardar sesión", f"No se pudo guardar el historial.\n{error}\n\n¿Cerrar la sesión igualmente?",
                                          parent=self.root):
                    return
            self.relay.close()
        self.restart = restart
        self.root.destroy()

    def callback_error(self, error_type, value, traceback):
        logging.getLogger("fti").error("Error en la interfaz", exc_info=(error_type, value, traceback))
        messagebox.showerror("FTI", f"Ocurrió un error en la interfaz.\n{value}\n\nPuedes consultar los registros para el diagnóstico.",
                             parent=self.root)


def diagnose(path):
    from iniciar import Relay

    count = check_resources()
    relay = Relay("saturation", start_when_visible=True)
    try:
        url = relay.start_api()
        request = urllib.request.Request(url + "/vehicles", headers={"Authorization": f"Bearer {relay.api.token}"})
        with urllib.request.urlopen(request, timeout=3) as response:
            vehicles = json.load(response)
        assert vehicles["count"] == 324
        relay.launch_viewer()
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and not relay.viewer_connected:
            relay.pump()
            if relay.viewer is not None and relay.viewer.poll() is not None:
                raise RuntimeError(relay.viewer_error or "El visor terminó antes de conectar.")
            time.sleep(.02)
        if not relay.viewer_connected or relay.omitted:
            raise RuntimeError("Whisk3D no confirmó la escena completa.")
        result = {"version": VERSION, "python": sys.version, "models": count,
                  "network_vehicles": vehicles["count"], "rendered": relay.viewer_status["count"],
                  "status": "ok", "logs": str(relay.log_dir)}
        Path(path).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        relay.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calidad", choices=("normal", "alta"))
    parser.add_argument("--directo", action="store_true", help="Inicia con las preferencias guardadas")
    parser.add_argument("--diagnostico", type=Path, help="Comprueba API, recursos y enlace real con Whisk")
    args = parser.parse_args()
    configure_logging()
    if args.diagnostico is not None:
        diagnose(args.diagnostico)
        return
    settings = load_settings()
    if args.calidad:
        settings["quality"] = args.calidad
    direct = args.directo
    while True:
        root = tk.Tk()
        launcher = Launcher(root, settings)
        if direct:
            root.after(80, launcher.start)
        try:
            root.mainloop()
        finally:
            if launcher.relay is not None:
                launcher.relay.close()
        if launcher.panel is not None and launcher.panel.error is not None:
            raise launcher.panel.error
        if not launcher.restart:
            break
        direct = False
        settings = load_settings()


if __name__ == "__main__":
    main()
