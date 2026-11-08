"""Panel de control de Whisk3D, con estado confirmado por la simulación."""
from datetime import datetime
import os
from pathlib import Path
import time
import tkinter as tk
from tkinter import filedialog, ttk

from trafico import MANUAL_MAX, SCENARIO_COUNTS

BACKGROUND = "#101a24"
CARD = "#1a2836"
CONTROL = "#26394a"
TEXT = "#f2f6fa"
SECONDARY = "#b0c2d1"
ACCENT = "#67dfbd"
CAUTION = "#ffcf81"
RED = "#ff9c9c"

PRESETS = {
    "normal": "Normal",
    "moderate": "Moderado",
    "peak_ns": "Punta N–S",
    "peak_ew": "Punta E–O",
    "saturation": "Saturación",
}
SCENARIOS = {
    **PRESETS,
    "manual": "Manual en I-5",
    "empty": "Sin tráfico",
}
MODES = {
    "fti": "FTI",
    "adaptive": "Adaptativo",
    "fixed": "Fijo",
    "python": "Coordinado",
}
MODE_HINTS = {
    "fti": "Prioriza la demanda por acceso.",
    "adaptive": "Ajusta el verde según las colas de cada cruce.",
    "fixed": "Cambia de fase con tiempos predefinidos.",
    "python": "Coordina las prioridades de los nueve cruces.",
}
VIEWS = {"barrio": "Barrio completo", "cruce": "Cruce de cerca",
         "avenida": "Avenida y mediana", "cenital": "Vista cenital"}
PHASES = {"GREEN": "Paso vehicular", "YELLOW": "Cambio de fase",
          "ALL_RED": "Despeje · todo rojo", "WALK": "Paso peatonal protegido"}
LIGHTS = {"GREEN": ("Verde", ACCENT), "YELLOW": ("Amarillo", CAUTION), "RED": ("Rojo", RED)}


def label(parent, text="", *, color=TEXT, size=10, bold=False, background=BACKGROUND):
    return tk.Label(parent, text=text, bg=background, fg=color, anchor="w",
                    font=("Segoe UI", size, "bold" if bold else "normal"))


class TrafficPanel:
    def __init__(self, root, relay):
        self.root, self.relay = root, relay
        self.error = None
        self.pending = None
        self.notice = ""
        self.notice_until = 0.0
        self.last_refresh = 0.0
        self.pump_job = None
        self.wheel_delta = 0
        self.layout_width = 0
        self.scenario_key = relay.state["scenario"]
        self.manual_target = relay.state["manual_count"]
        self.inputs = []
        self.card_groups = []
        self.option_groups = []
        self.data_action_groups = []
        self.layout_mode = None
        root.title("FTI | Control del cruce I-5")
        root.configure(bg=BACKGROUND)
        self._styles()
        self._header()
        self.canvas = tk.Canvas(root, background=BACKGROUND, highlightthickness=0, yscrollincrement=1)
        scrollbar = ttk.Scrollbar(root, command=self.canvas.yview, style="FTI.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=BACKGROUND, padx=16, pady=9)
        self.canvas_body = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self._setup()
        self._metrics()
        self._signals()
        self._view_controls()
        self._tests()
        self._data_controls()
        self.canvas.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        root.bind("<MouseWheel>", self._scroll)
        root.bind("<FocusIn>", self._scroll_to_focus, add="+")
        root.bind("<Destroy>", self._cancel_pump, add="+")
        root.minsize(350, 310)
        self.header.bind("<Configure>", self._update_min_height)
        root.geometry(f"{min(720, root.winfo_screenwidth() - 45)}x{min(735, root.winfo_screenheight() - 100)}")
        self._pump()

    def _styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("FTI.TButton", background=CONTROL, foreground=TEXT, padding=(10, 6),
                        font=("Segoe UI", 10, "bold"), borderwidth=1, bordercolor=CONTROL,
                        lightcolor=CONTROL, darkcolor=CONTROL, focuscolor=SECONDARY)
        style.map("FTI.TButton", background=[("active", "#344e62")],
                  foreground=[("disabled", "#91a4b5")])
        style.configure("Primary.FTI.TButton", background=ACCENT, foreground="#09251f",
                        lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=ACCENT)
        style.map("Primary.FTI.TButton", background=[("disabled", CONTROL), ("active", "#99ead5")])
        style.layout("Choice.FTI.TRadiobutton", style.layout("Toolbutton"))
        style.configure("Choice.FTI.TRadiobutton", background=CONTROL, foreground=TEXT,
                        padding=(5, 7), font=("Segoe UI", 10), borderwidth=1,
                        bordercolor=CONTROL, lightcolor=CONTROL, darkcolor=CONTROL,
                        focuscolor=SECONDARY, anchor="center")
        style.map("Choice.FTI.TRadiobutton",
                  background=[("selected", ACCENT), ("active", "#344e62")],
                  foreground=[("disabled", "#91a4b5"), ("selected", "#09251f")])
        style.configure("FTI.TSpinbox", foreground=TEXT, fieldbackground=CONTROL,
                        background=CONTROL, arrowcolor=TEXT, padding=5, bordercolor=CONTROL,
                        selectbackground="#344e62", selectforeground=TEXT)
        style.configure("FTI.TEntry", foreground=TEXT, fieldbackground=CONTROL,
                        padding=6, bordercolor=CONTROL)
        style.map("FTI.TEntry", fieldbackground=[("readonly", CONTROL)],
                  foreground=[("readonly", TEXT)])
        style.configure("FTI.Vertical.TScrollbar", background=CONTROL, troughcolor=BACKGROUND,
                        arrowcolor=SECONDARY, bordercolor=BACKGROUND, lightcolor=CONTROL, darkcolor=CONTROL)
        style.configure("FTI.Horizontal.TScale", background=ACCENT, troughcolor=CONTROL)

    def _button(self, parent, text, command, primary=False, *, simulate=True):
        style = "Primary.FTI.TButton" if primary else "FTI.TButton"
        button = ttk.Button(parent, text=text, command=command, style=style)
        if simulate:
            self.inputs.append(button)
        return button

    def _options(self, parent, choices, variable, command, columns, *, simulate=True):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x")
        buttons = {key: ttk.Radiobutton(row, text=name, value=key, variable=variable,
                                        command=command, style="Choice.FTI.TRadiobutton", takefocus=True)
                   for key, name in choices.items()}
        self.option_groups.append((row, buttons, columns))
        if simulate:
            self.inputs.extend(buttons.values())
        return buttons

    def _section(self, title):
        section = tk.Frame(self.body, bg=CARD, padx=13, pady=9)
        section.pack(fill="x", pady=(10, 0))
        label(section, title, size=11, bold=True, background=CARD).pack(fill="x", pady=(0, 5))
        return section

    def _header(self):
        header = self.header = tk.Frame(self.root, bg=BACKGROUND, padx=16, pady=8)
        header.pack(fill="x")
        self.eyebrow = label(header, "RED DE TRÁFICO  /  WHISK3D", color=ACCENT, size=9, bold=True)
        self.eyebrow.pack(anchor="w")
        row = tk.Frame(header, bg=BACKGROUND)
        row.pack(fill="x", pady=(1, 0))
        row.columnconfigure(0, weight=1)
        self.heading = label(row, "Control del cruce I-5", size=23, bold=True)
        self.heading_width = self.heading.winfo_reqwidth()
        self.header_actions = tk.Frame(row, bg=BACKGROUND)
        self.pause = self._button(self.header_actions, "Reanudar", self._toggle_pause, primary=True)
        self.pause.configure(width=0)
        self.restart = self._button(self.header_actions, "Reiniciar",
                                    lambda: self._send("reset", None, "Escenario reiniciado"))
        self.restart.configure(width=0)
        self.header_actions_width = self.pause.winfo_reqwidth() + self.restart.winfo_reqwidth() + 8
        self.status = label(header, color=SECONDARY)
        self.status.pack(fill="x", pady=(4, 0))
        self.feedback = label(header, color=SECONDARY, size=9)
        self.feedback.pack(fill="x", pady=(3, 0))
        navigation = self.navigation = tk.Frame(header, bg=BACKGROUND)
        navigation.pack(fill="x", pady=(6, 0))
        self.navigation_buttons = {}
        for name, section in (("Tráfico", "demand_section"), ("Cámara", "view_section"),
                              ("Pruebas", "test_section"), ("Datos", "data_section")):
            button = ttk.Button(navigation, text=name, style="FTI.TButton", width=0,
                                command=lambda key=section: self._scroll_to(getattr(self, key).winfo_y() - 11))
            self.navigation_buttons[section] = button
        self.reopen = ttk.Button(navigation, text="Recuperar visor", width=0,
                                 command=self._reopen_viewer, style="FTI.TButton")
        self.reopen.state(["disabled"])
        self.reopen_needed = False

    def _setup(self):
        section = self.demand_section = self._section("Demanda de tráfico")
        label(section, "Elige un perfil para la red o una cantidad para I-5.",
              color=SECONDARY, size=9, background=CARD).pack(fill="x", pady=(0, 5))
        self.scenario = tk.StringVar(value=self.scenario_key)
        choices = {key: f"{name} · {SCENARIO_COUNTS[key]}" for key, name in PRESETS.items()}
        choices["manual"] = SCENARIOS["manual"]
        self.scenario_buttons = self._options(section, choices, self.scenario, self._select_scenario, 3)
        self.scenario_detail = label(section, color=SECONDARY, size=9, background=CARD)
        self.scenario_detail.pack(fill="x", pady=(5, 0))
        self.manual_row = tk.Frame(section, bg=CARD)
        self.manual_label = label(self.manual_row, f"Autos en I-5 (0–{MANUAL_MAX})", color=SECONDARY,
                                  size=9, background=CARD)
        self.manual_count = tk.StringVar(value=self.manual_target if self.manual_target is not None else 12)
        self.manual_input = ttk.Spinbox(self.manual_row, from_=0, to=MANUAL_MAX, width=4,
                                        textvariable=self.manual_count, style="FTI.TSpinbox")
        self.manual_input.bind("<Return>", self._apply_manual)
        self.manual_input.bind("<MouseWheel>", self._scroll)
        self.inputs.append(self.manual_input)
        self.manual_apply = self._button(self.manual_row, "Aplicar", self._apply_manual, primary=True)
        self._show_manual()

        mode = self._section("Estrategia de semáforos")
        self.mode = tk.StringVar()
        self.mode_buttons = self._options(mode, MODES, self.mode, self._change_mode, 4)
        self.mode_detail = label(mode, color=SECONDARY, size=9, background=CARD)
        self.mode_detail.pack(fill="x", pady=(5, 0))

    def _cards(self, parent):
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x")
        cards = []
        self.card_groups.append((row, cards))
        return row, cards

    def _metrics(self):
        row, cards = self._cards(self.body)
        row.pack_configure(pady=(10, 0))
        self.metrics = []
        self.metric_titles = []
        for title in ("Autos en I-5", "Autos en la red", "En cola en la red", "Cruces últimos 60 s"):
            card = tk.Frame(row, bg=CARD, padx=10, pady=6)
            cards.append(card)
            number = label(card, "—", size=19, bold=True, background=CARD)
            number.pack(fill="x")
            caption = label(card, title, color=SECONDARY, size=9, background=CARD)
            caption.pack(fill="x")
            self.metrics.append(number)
            self.metric_titles.append(caption)

    def _signals(self):
        section = self._section("Semáforos del cruce I-5")
        row, cards = self._cards(section)
        self.signals = []
        for name in ("Norte", "Este", "Sur", "Oeste"):
            card = tk.Frame(row, bg=CONTROL, padx=10, pady=5)
            cards.append(card)
            label(card, name, color=SECONDARY, size=9, background=CONTROL).pack(fill="x")
            light = label(card, size=12, bold=True, background=CONTROL)
            light.pack(fill="x")
            queue = label(card, color=SECONDARY, size=9, background=CONTROL)
            queue.pack(fill="x")
            self.signals.append((light, queue))
        self.phase = label(section, color=SECONDARY, background=CARD)
        self.phase.pack(fill="x", pady=(4, 0))

    def _view_controls(self):
        section = self.view_section = self._section("Cámara de Whisk3D")
        self.view = tk.StringVar(value=self.relay.view)
        self.view_buttons = self._options(section, VIEWS, self.view, self._change_view, 4, simulate=False)
        self.azimuth = tk.DoubleVar(value=self.relay.azimuth)
        self.elevation = tk.DoubleVar(value=self.relay.elevation)
        self.zoom = tk.DoubleVar(value=self.relay.zoom)
        self.angle_labels = []
        for title, variable, low, high, unit in (("Giro", self.azimuth, 0, 360, "°"),
                                                  ("Inclinación", self.elevation, 12, 87, "°"),
                                                  ("Zoom", self.zoom, 60, 175, "%")):
            row = tk.Frame(section, bg=CARD)
            row.pack(fill="x", pady=(5, 0))
            caption = label(row, background=CARD, color=SECONDARY, size=9)
            caption.configure(width=15)
            caption.pack(side="left")
            self.angle_labels.append((title, caption, variable, unit))
            ttk.Scale(row, from_=low, to=high, variable=variable, command=self._change_angle,
                      style="FTI.Horizontal.TScale").pack(
                side="left", fill="x", expand=True)
        self._sync_camera()
        self.view_hint = label(section, "En el visor, usa 1–4 para cambiar de vista, arrastra con el botón central para girar y usa la rueda para acercarte.",
                               color=SECONDARY, size=9, background=CARD)
        self.view_hint.configure(justify="left")
        self.view_hint.pack(fill="x", pady=(4, 0))

    def _tests(self):
        section = self.test_section = self._section("Pruebas del cruce")
        row = tk.Frame(section, bg=CARD)
        row.pack(fill="x")
        self.sensor = self._button(row, "Simular fallo", self._toggle_sensor)
        self.pedestrian = self._button(row, "Pedir paso peatonal",
                                       lambda: self._send("pedestrian", None, "Solicitud peatonal enviada"))
        self.step = self._button(row, "Avanzar un paso",
                                 lambda: self._send("step", None, "Un paso de simulación aplicado"))
        self.sensor_detail = label(section, color=SECONDARY, size=9, background=CARD)
        self.sensor_detail.pack(fill="x", pady=(4, 0))

    def _data_controls(self):
        section = self.data_section = self._section("Datos de la simulación")
        self.data_summary = label(section, color=SECONDARY, size=9, background=CARD)
        self.data_summary.pack(fill="x", pady=(0, 6))
        self.data_metrics = label(section, color=SECONDARY, size=9, background=CARD)
        self.data_metrics.pack(fill="x", pady=(0, 6))
        row = tk.Frame(section, bg=CARD)
        row.pack(fill="x")
        self.recording = self._button(row, "Pausar registro", self._toggle_recording, simulate=False)
        self.open_logs = self._button(row, "Abrir registros", self._open_logs, simulate=False)
        self.data_action_groups.append((row, (self.recording, self.open_logs)))

        label(section, "Exportar", color=SECONDARY, size=9, background=CARD).pack(fill="x", pady=(10, 5))
        row = tk.Frame(section, bg=CARD)
        row.pack(fill="x")
        self.export_buttons = {
            "csv": self._button(row, "Historial CSV", lambda: self._export_data("csv"), simulate=False),
            "json": self._button(row, "Historial JSON", lambda: self._export_data("json"), simulate=False),
            "snapshot": self._button(row, "Estado JSON", lambda: self._export_data("snapshot"), simulate=False),
        }
        self.data_action_groups.append((row, tuple(self.export_buttons.values())))
        self.export_detail = label(section, "El historial contiene una muestra por segundo simulado. "
                                   "Estado JSON guarda los semáforos y los vehículos actuales.",
                                   color=SECONDARY, size=9, background=CARD)
        self.export_detail.pack(fill="x", pady=(5, 0))
        self.export_result = label(section, color=SECONDARY, size=9, background=CARD)
        self.export_result.pack(fill="x", pady=(4, 0))

        label(section, "API local", color=SECONDARY, size=9, background=CARD).pack(fill="x", pady=(11, 5))
        self.api_status = label(section, color=SECONDARY, size=9, background=CARD)
        self.api_status.pack(fill="x", pady=(0, 5))
        self.api_url = tk.StringVar()
        self.api_address = ttk.Entry(section, textvariable=self.api_url, state="readonly", style="FTI.TEntry")
        self.api_address.pack(fill="x")
        row = tk.Frame(section, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        self.api_toggle = self._button(row, "Activar API", self._toggle_api, simulate=False)
        self.api_copy_url = self._button(row, "Copiar URL", self._copy_api_url, simulate=False)
        self.api_copy_token = self._button(row, "Copiar token", self._copy_api_token, simulate=False)
        self.data_action_groups.append((row, (self.api_toggle, self.api_copy_url, self.api_copy_token)))
        self.api_detail = label(section, "Otros programas pueden consultar esta sesión con la URL y el token. "
                                "La API ofrece el estado, las métricas, los vehículos y el historial.",
                                color=SECONDARY, size=9, background=CARD)
        self.api_detail.pack(fill="x", pady=(5, 0))

        label(section, "Servidor de visualización", color=SECONDARY, size=9,
              background=CARD).pack(fill="x", pady=(12, 5))
        self.server_detail = label(section, "Envía los datos de esta sesión a tu servidor para visualizarlos "
                                   "desde otros equipos. Usa la dirección de su API.",
                                   color=SECONDARY, size=9, background=CARD)
        self.server_detail.pack(fill="x", pady=(0, 5))
        label(section, "Dirección del servidor", color=SECONDARY, size=9,
              background=CARD).pack(fill="x")
        self.server_url = tk.StringVar(value=self.relay.connector.status.get("url", ""))
        self.server_address = ttk.Entry(section, textvariable=self.server_url, style="FTI.TEntry")
        self.server_address.pack(fill="x", pady=(3, 6))
        label(section, "Token del servidor", color=SECONDARY, size=9,
              background=CARD).pack(fill="x")
        self.server_token = tk.StringVar()
        self.server_credential = ttk.Entry(section, textvariable=self.server_token, show="•", style="FTI.TEntry")
        self.server_credential.pack(fill="x", pady=(3, 6))
        self.server_toggle = self._button(section, "Conectar servidor", self._toggle_server, simulate=False)
        self.server_toggle.pack(anchor="w")
        self.server_status = label(section, color=SECONDARY, size=9, background=CARD)
        self.server_status.pack(fill="x", pady=(5, 0))

    def _resize(self, event):
        width = event.width
        if width == self.layout_width:
            return
        self.layout_width = width
        self.canvas.itemconfigure(self.canvas_body, width=width)
        content_width = max(1, width - 58)
        header_width = max(1, self.root.winfo_width() - 32)
        for widget in (self.view_hint, self.scenario_detail, self.mode_detail, self.sensor_detail, self.phase,
                       self.data_summary, self.data_metrics, self.export_detail, self.export_result,
                       self.api_status, self.api_detail,
                       self.server_detail, self.server_status):
            widget.configure(wraplength=content_width, justify="left")
        for widget in (self.feedback, self.status):
            widget.configure(wraplength=header_width, justify="left")
        compact = width < 625
        narrow = width < 510 or self.heading_width + self.header_actions_width + 8 > header_width
        self.layout_mode = compact, narrow
        self.eyebrow.configure(text="FTI  /  WHISK3D" if narrow else "RED DE TRÁFICO  /  WHISK3D")
        self.heading.configure(text="Cruce I-5" if narrow else "Control del cruce I-5",
                               wraplength=header_width if narrow else 0, justify="left")
        self.heading.grid(row=0, column=0, columnspan=2 if narrow else 1, sticky="w")
        self.header_actions.grid(row=int(narrow), column=int(not narrow), sticky="w" if narrow else "e",
                                 pady=(5, 0) if narrow else 0)
        actions_inline = self.header_actions_width <= header_width
        self.restart.grid(row=int(not actions_inline), column=0, sticky="w",
                          padx=(0, 8) if actions_inline else 0, pady=0 if actions_inline else (4, 0))
        self.pause.grid(row=0, column=int(actions_inline), sticky="w")
        self._layout_navigation()
        columns = 2 if compact else 4
        for widget in self.metric_titles:
            widget.configure(wraplength=max(1, (width - 32 - (columns - 1) * 6) // columns - 20),
                             justify="left")
        for _light, queue in self.signals:
            queue.configure(wraplength=max(1, (content_width - (columns - 1) * 6) // columns - 20),
                            justify="left")
        for row, cards in self.card_groups:
            for column in range(4):
                row.columnconfigure(column, weight=int(column < columns),
                                    uniform="cards" if column < columns else "")
            for index, card in enumerate(cards):
                line, column = divmod(index, columns)
                card.grid(row=line, column=column, sticky="nsew",
                          padx=(6 if column else 0, 0), pady=(6 if line else 0, 0))
        for row, buttons, wide_columns in self.option_groups:
            button_width = max(button.winfo_reqwidth() for button in buttons.values()) + 5
            columns = max(1, min(2 if compact else wide_columns, (content_width + 5) // button_width))
            for column in range(wide_columns):
                row.columnconfigure(column, weight=int(column < columns),
                                    uniform="options" if column < columns else "")
            for index, button in enumerate(buttons.values()):
                line, column = divmod(index, columns)
                button.grid(row=line, column=column, sticky="ew",
                            padx=(5 if column else 0, 0), pady=(5 if line else 0, 0))
        manual_inline = sum(widget.winfo_reqwidth() for widget in
                            (self.manual_label, self.manual_input, self.manual_apply)) + 12 <= content_width
        self.manual_label.grid(row=0, column=0, columnspan=1 if manual_inline else 2, sticky="w")
        self.manual_input.grid(row=int(not manual_inline), column=int(manual_inline), sticky="w",
                               padx=(6, 0) if manual_inline else 0)
        self.manual_apply.grid(row=int(not manual_inline), column=2 if manual_inline else 1, sticky="w", padx=(6, 0))
        tests_inline = not narrow and self.sensor.winfo_reqwidth() + self.pedestrian.winfo_reqwidth() + 7 <= content_width
        self.sensor.grid(row=0, column=0, sticky="w", padx=(0, 7) if tests_inline else 0)
        self.pedestrian.grid(row=int(not tests_inline), column=int(tests_inline), sticky="w",
                             pady=0 if tests_inline else (6, 0))
        self.step.grid(row=1 if tests_inline else 2, column=0, columnspan=2 if tests_inline else 1,
                       sticky="w", pady=(6, 0))
        for row, buttons in self.data_action_groups:
            button_width = max(button.winfo_reqwidth() for button in buttons) + 6
            columns = max(1, min(len(buttons), (content_width + 6) // button_width))
            for column in range(len(buttons)):
                row.columnconfigure(column, weight=int(column < columns), uniform="data" if column < columns else "")
            for index, button in enumerate(buttons):
                line, column = divmod(index, columns)
                button.grid(row=line, column=column, sticky="ew",
                            padx=(6 if column else 0, 0), pady=(5 if line else 0, 0))

    def _update_min_height(self, _event):
        min_height = min(max(310, self.header.winfo_reqheight() + 110),
                         max(310, self.root.winfo_screenheight() - 65))
        if self.root.minsize()[1] != min_height:
            self.root.minsize(350, min_height)

    def _layout_navigation(self):
        buttons = [*self.navigation_buttons.values()]
        available = self.root.winfo_width() - 32
        widths = [button.winfo_reqwidth() + 6 for button in buttons]
        columns = len(buttons) if sum(widths) <= available else max(1, available // max(widths))
        if not self.reopen_needed:
            self.reopen.grid_remove()
        elif sum(widths) + self.reopen.winfo_reqwidth() + 6 <= available:
            buttons.append(self.reopen)
            columns += 1
        else:
            row = (len(buttons) + columns - 1) // columns
            self.reopen.grid(row=row, column=0, columnspan=columns, sticky="w", pady=(4, 0))
        for index, button in enumerate(buttons):
            row, column = divmod(index, columns)
            button.grid(row=row, column=column, columnspan=1, sticky="w", padx=(0, 6), pady=(4 if row else 0, 0))

    def _scroll(self, event):
        self.wheel_delta += event.delta
        steps = int(self.wheel_delta / 120)
        if steps:
            self.wheel_delta -= steps * 120
            self.canvas.yview_scroll(-steps * 60, "units")
        return "break"

    def _scroll_to(self, offset):
        self.canvas.yview_moveto(max(0, offset) / max(1, self.body.winfo_height()))

    def _scroll_to_focus(self, event):
        widget = event.widget
        if str(widget).startswith(f"{self.body}."):
            top = widget.winfo_rooty() - self.body.winfo_rooty()
            bottom = top + widget.winfo_height()
            visible_top = self.canvas.canvasy(0)
            height = self.canvas.winfo_height()
            if top < visible_top:
                self._scroll_to(top - 8)
            elif bottom > visible_top + height:
                self._scroll_to(bottom - height + 8)

    def _change_view(self):
        self.relay.set_view(self.view.get())
        self._sync_camera()

    def _change_angle(self, _value=None):
        self.relay.azimuth = round(self.azimuth.get())
        self.relay.elevation = round(self.elevation.get())
        self.relay.zoom = round(self.zoom.get())
        self._sync_camera()

    def _sync_camera(self):
        view = self.relay.view
        if self.view.get() != view:
            self.view.set(view)
        values = (self.relay.azimuth, self.relay.elevation, self.relay.zoom)
        for (title, caption, variable, unit), value in zip(self.angle_labels, values):
            if variable.get() != value:
                variable.set(value)
            caption.configure(text=f"{title} {value}{unit}")

    def _reopen_viewer(self):
        try:
            self.relay.launch_viewer(restart=True)
            self.notice = "Abriendo Whisk3D…"
        except OSError as error:
            self.notice = self.relay.viewer_error or str(error)
        now = time.monotonic()
        self.notice_until = now + 5
        self._refresh(now)

    def _send(self, action, value, notice):
        now = time.monotonic()
        if self.pending:
            return
        self.pending = (self.relay.command(action, value), notice, self.relay.viewer_connected, now + 3.0)
        self._refresh(now)

    def _show_manual(self):
        if self.scenario.get() == "manual":
            self.manual_row.pack(fill="x", pady=(6, 0))
        else:
            self.manual_row.pack_forget()

    def _select_scenario(self):
        key = self.scenario.get()
        self._show_manual()
        if key == "manual":
            self.manual_input.focus_set()
            self.manual_input.selection_range(0, "end")
        elif key != self.scenario_key:
            self._send("scenario", key, f"Perfil {SCENARIOS[key]} cargado")

    def _apply_manual(self, _event=None):
        try:
            count = int(self.manual_count.get())
        except ValueError:
            count = -1
        if not 0 <= count <= MANUAL_MAX:
            now = time.monotonic()
            self.notice = f"Escribe una cantidad entera de 0 a {MANUAL_MAX} autos."
            self.notice_until = now + 4
            self._refresh(now)
            return
        self._send("manual_count", count, f"Modo manual aplicado · {count} autos en I-5")

    def _change_mode(self):
        key = self.mode.get()
        if key == "python":
            self._send("coordinate", True, "Coordinación de red activada")
        else:
            self._send("mode", key, "Estrategia solicitada")

    def _toggle_pause(self):
        self._send("toggle_pause", None, "Estado de la simulación actualizado")

    def _toggle_sensor(self):
        self._send("toggle_sensor", None, "Estado de los sensores actualizado")

    def _data_notice(self, text):
        now = time.monotonic()
        self.notice, self.notice_until = text, now + 6
        self._refresh(now)

    def _toggle_recording(self):
        self.relay.data.set_recording(not self.relay.data.recording)
        text = "Registro reanudado" if self.relay.data.recording else "Registro pausado"
        self._data_notice(text)

    def _export_data(self, kind):
        extension = "json" if kind == "snapshot" else kind
        title = "Guardar estado de la simulación" if kind == "snapshot" else "Guardar historial de la simulación"
        try:
            folder = Path(self.relay.export_dir)
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            category = "estado" if kind == "snapshot" else "historial"
            filename = filedialog.asksaveasfilename(
                parent=self.root, title=title, initialdir=str(folder),
                initialfile=f"FTI-{category}-{stamp}.{extension}",
                defaultextension=f".{extension}",
                filetypes=[(extension.upper(), f"*.{extension}")])
            if not filename:
                return
            if kind == "snapshot":
                saved = self.relay.data.export_snapshot(filename)
            else:
                saved = self.relay.data.export_history(filename, kind)
            self.export_result.configure(text=f"Guardado en {saved}", fg=ACCENT)
            self._data_notice(f"Archivo guardado · {Path(saved).name}")
        except (OSError, ValueError, RuntimeError) as error:
            self.export_result.configure(text=str(error), fg=RED)
            self._data_notice("No se pudo guardar el archivo. Revisa el detalle en Datos.")

    def _toggle_api(self):
        try:
            if self.relay.api.running:
                self.relay.stop_api()
                text = "API detenida"
            else:
                self.relay.start_api()
                text = "API disponible para consultar esta sesión"
            self._data_notice(text)
        except (OSError, ValueError, RuntimeError) as error:
            self._data_notice(f"No se pudo cambiar el estado de la API. {error}")

    def _copy_api(self, value, notice):
        if not self.relay.api.running:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(value)
            self._data_notice(notice)
        except tk.TclError as error:
            self._data_notice(f"No se pudo copiar al portapapeles. {error}")

    def _copy_api_url(self):
        self._copy_api(self.relay.api.url + "/state", "URL del estado copiada")

    def _copy_api_token(self):
        self._copy_api(self.relay.api.token, "Token de esta sesión copiado")

    def _toggle_server(self):
        try:
            if self.relay.connector.running:
                self.relay.disconnect_server()
                text = "Enlace con el servidor detenido"
            else:
                self.relay.connect_server(self.server_url.get().strip(), self.server_token.get())
                text = "Enlace activado. Esperando la confirmación del servidor."
            self._data_notice(text)
        except (OSError, ValueError, RuntimeError) as error:
            self._data_notice(f"No se pudo cambiar el enlace con el servidor. {error}")

    def _open_logs(self):
        try:
            os.startfile(str(self.relay.log_dir))
            self._data_notice("Carpeta de registros abierta")
        except OSError as error:
            self._data_notice(f"No se pudo abrir la carpeta de registros. {error}")

    def _pump(self):
        self.pump_job = None
        try:
            self.relay.pump()
            now = time.monotonic()
            if now - self.last_refresh >= .12:
                self._refresh(now)
                self.last_refresh = now
            self.pump_job = self.root.after(16, self._pump)
        except Exception as error:
            self.error = error
            self.root.destroy()

    def _cancel_pump(self, event):
        if event.widget == self.root and self.pump_job is not None:
            self.root.after_cancel(self.pump_job)
            self.pump_job = None

    def _refresh(self, now):
        state = self.relay.state
        controller = state["controller"]
        connected = now - self.relay.last_seen <= 2
        viewer_ok = self.relay.viewer_connected
        viewer_state = self.relay.viewer_status
        if self.pending:
            command, notice, wait_for_viewer, deadline = self.pending
            applied = state["ack"] >= command
            result = self.relay.results.get(command)
            confirmed = viewer_ok and viewer_state["epoch"] == state["epoch"] and viewer_state["command"] >= command
            if now >= deadline or (applied and (result or not wait_for_viewer or confirmed or not viewer_ok)):
                if not applied:
                    notice = "Python aún no confirma la solicitud."
                elif not result and state["ack"] > command:
                    notice = "Solicitud procesada. Ya hay un cambio posterior."
                elif wait_for_viewer and not confirmed and not result:
                    notice = "Python aplicó el cambio. Whisk3D aún no lo confirma."
                self.notice, self.notice_until = result or notice, now + 3
                self.pending = None
        self._sync_camera()
        active = self.pending is None
        for button in self.inputs:
            button.state(["!disabled"] if active else ["disabled"])
        if self.scenario_key != state["scenario"] or self.manual_target != state["manual_count"]:
            self.scenario_key = state["scenario"]
            self.manual_target = state["manual_count"]
            self.scenario.set(self.scenario_key)
            if self.manual_target is not None:
                self.manual_count.set(self.manual_target)
            self._show_manual()
        selected = "python" if state["coordination"] else controller["mode"]
        if self.pending is None and self.mode.get() != selected:
            self.mode.set(selected)
        running = controller["running_mode"]
        effective = "python" if state["coordination"] and running == "adaptive" else running
        explanation = MODE_HINTS[effective]
        if controller["fallback"]:
            explanation = ("Respaldo por fallo de sensores." if running == "fixed"
                           else "Cambiando a respaldo por fallo de sensores.")
        elif effective != selected:
            explanation = f"{MODES[selected]} pendiente de cambio de fase."
        self.mode_detail.configure(text=f"En uso {MODES[effective]} · {explanation}")
        name = SCENARIOS[self.scenario_key]
        if self.manual_target is not None:
            demand = f"{name} · {self.manual_target} autos en el cruce"
        else:
            demand = f"{name} · {state['metrics']['vehicles']} autos en la red"
        self.scenario_detail.configure(text=f"Activo  {demand}")
        self.pause.configure(text="Reanudar" if state["paused"] else "Pausar")
        time_text = f"{state['time']:05.1f} s"
        motion = "Pausado" if state["paused"] else "En marcha"
        viewer_closed = self.relay.viewer is None or self.relay.viewer.poll() is not None
        frame_ready = viewer_ok and viewer_state["epoch"] == state["epoch"]
        startup_wait = self.relay.viewer_status is None and now - self.relay.viewer_started_at < 25.0
        reopen_needed = viewer_closed or (not viewer_ok and not startup_wait)
        if reopen_needed != self.reopen_needed:
            self.reopen_needed = reopen_needed
            self.reopen.state(["!disabled"] if reopen_needed else ["disabled"])
            self._layout_navigation()
        if viewer_closed:
            link = "Visor cerrado"
        elif frame_ready:
            link = f"Visor conectado · {viewer_state['count']} dibujados"
        elif startup_wait:
            link = "Cargando el visor"
        else:
            link = "Esperando imagen del visor"
        self.status.configure(text=f"{link}   |   {motion}   |   {time_text}" if connected else "Simulación Python sin actualizar",
                              fg=ACCENT if connected and frame_ready and not viewer_closed else CAUTION)

        metrics = state["metrics"]
        numbers = (len(state["cars"]), metrics["vehicles"], metrics["queued"], state["recent_crossings"])
        for widget, number in zip(self.metrics, numbers):
            widget.configure(text=str(number))
        for index, direction in enumerate("NESW"):
            light, queue = self.signals[index]
            text, color = LIGHTS[state["lights"][direction]]
            light.configure(text=f"● {text}", fg=color)
            count = int(controller["queues"][index])
            queue.configure(text=f"Cola detectada  {count}" if state["sensors"] else "Sensor sin señal")
        stage = controller["stage"]
        phase = PHASES[stage]
        if controller["pedestrian_pending"]:
            phase += "  ·  Paso peatonal pendiente"
        self.phase.configure(text=phase)
        if stage == "WALK" or controller["pedestrian_pending"]:
            self.pedestrian.state(["disabled"])
        self.sensor.configure(text="Simular fallo" if state["sensors"] else "Restaurar sensores")
        sensor = "Sensores en servicio" if state["sensors"] else "Sensores fuera de servicio"
        if controller["fallback"]:
            sensor += "  ·  Respaldo fijo en uso" if running == "fixed" else "  ·  Cambio a respaldo pendiente"
        self.sensor_detail.configure(text=sensor, fg=SECONDARY if state["sensors"] else CAUTION)

        data = self.relay.data
        self.step.state(["!disabled"] if active and state["paused"] else ["disabled"])
        self.recording.configure(text="Pausar registro" if data.recording else "Reanudar registro")
        recording = "Registro activo" if data.recording else "Registro pausado"
        samples = "1 muestra conservada" if data.sample_count == 1 else f"{data.sample_count} muestras conservadas"
        self.data_summary.configure(text=f"{recording} · {samples}")
        self.data_metrics.configure(text=f"Velocidad media {metrics['speed_kmh']:.1f} km/h"
                                         f" · Espera media {metrics['mean_wait']:.1f} s")
        api_running = self.relay.api.running
        api_url = self.relay.api.url + "/state" if api_running else ""
        if self.api_url.get() != api_url:
            self.api_url.set(api_url)
        self.api_status.configure(text="Disponible en este equipo" if api_running else "API apagada",
                                  fg=ACCENT if api_running else SECONDARY)
        self.api_toggle.configure(text="Detener API" if api_running else "Activar API")
        for button in (self.api_copy_url, self.api_copy_token):
            button.state(["!disabled"] if api_running else ["disabled"])
        server = self.relay.connector.status
        server_running = server["running"]
        for entry in (self.server_address, self.server_credential):
            entry.state(["disabled"] if server_running else ["!disabled"])
        self.server_toggle.configure(text="Desconectar servidor" if server_running else "Conectar servidor")
        server_text = "Enlace inactivo"
        if server_running:
            server_text = f"Enlace activo · {server['sent_count']} envíos confirmados"
            if server["last_sent"]:
                sent_at = datetime.fromisoformat(server["last_sent"]).astimezone().strftime("%H:%M:%S")
                server_text += f" · Última entrega {sent_at}"
        if server["error"]:
            server_text += f"\n{server['error']}"
        self.server_status.configure(text=server_text, fg=CAUTION if server["error"] else SECONDARY)

        hint = ""
        if self.relay.viewer_error:
            hint = self.relay.viewer_error
        elif reopen_needed:
            hint = "Usa Recuperar visor para volver a mostrar la simulación."
        elif startup_wait and self.relay.start_when_visible:
            hint = "Puedes reanudar en Python o esperar la primera imagen."
        elif self.relay.omitted:
            hint = f"El visor alcanzó su capacidad. {self.relay.omitted} autos fuera de imagen."
        if self.notice_until > now:
            hint = self.notice
        if self.pending:
            hint = "Confirmando en Whisk3D…" if state["ack"] >= self.pending[0] else "Aplicando en Python…"
        if not connected:
            hint = "Esperando la próxima actualización de la simulación."
        self.feedback.configure(text=hint)


def show_panel(relay):
    window = tk.Tk()
    panel = TrafficPanel(window, relay)
    window.mainloop()
    if panel.error:
        raise panel.error
