"""Control de fases, sensores y cruces peatonales en Python."""
import math

APPROACHES = ("N", "E", "S", "W")
GROUPS = {"NS": ("N", "S"), "EW": ("E", "W")}
MODES = ("fti", "fixed", "adaptive")


class Controller:
    def __init__(self, mode="fti"):
        if mode not in MODES:
            raise ValueError("Modo desconocido")
        self.mode = self.running_mode = mode
        self.stage = "ALL_RED"
        self.active = []
        self.elapsed = 0.0
        self.counts = [0.0] * 4
        self.queues = [0.0] * 4
        self.sensor_age = 0.0
        self.cursor = 3
        self.last_axis = "EW"
        self.wait = [0.0] * 4
        self.clearance = 1.0
        self.priority = ""
        self.pedestrian_pending = False
        self.fallback = False
        self.reason = "Esperando demanda"

    def sense(self, counts, queues=None):
        def sanitize(items):
            result = []
            for value in list(items)[:4]:
                value = float(value or 0.0)
                result.append(max(0.0, value) if math.isfinite(value) else 0.0)
            return (result + [0.0] * 4)[:4]
        self.counts = sanitize(counts)
        self.queues = sanitize(counts if queues is None else queues)
        self.sensor_age = 0.0

    def light(self, approach):
        return self.stage if approach in self.active else "RED"

    def yellow_duration(self):
        return 2.0 if self.running_mode == "fti" else 2.5

    def green_duration(self):
        return {"fti": 5.0, "fixed": 11.0, "adaptive": 16.0}[self.running_mode]

    def request_pedestrian(self):
        if self.pedestrian_pending or self.stage == "WALK":
            return False
        self.pedestrian_pending = True
        self.reason = "Solicitud peatonal en espera de despeje seguro"
        return True

    def step(self, dt, occupied=False):
        self.sensor_age += dt
        self.elapsed += dt
        self.fallback = self.sensor_age >= 5.0
        requested = "fixed" if self.fallback else self.mode
        for i, approach in enumerate(APPROACHES):
            self.wait[i] = self.wait[i] + dt if self.counts[i] > 0 and self.light(approach) != "GREEN" else 0.0
        if self.stage == "WALK":
            if self.elapsed >= 6.0:
                self.stage, self.elapsed = "ALL_RED", 0.0
                self.reason = "Fin de cruce peatonal: intervalo de despeje"
            return
        if requested != self.running_mode and self.stage == "GREEN":
            self.stage, self.elapsed, self.reason = "YELLOW", 0.0, "Transición de modo"
        if self.stage == "YELLOW":
            if self.elapsed >= self.yellow_duration():
                self.stage, self.elapsed, self.active = "ALL_RED", 0.0, []
            return
        if self.stage == "ALL_RED":
            if self.elapsed < self.clearance or occupied:
                self.reason = "Despejando vehículos dentro del cruce" if occupied else "Intervalo de despeje"
                return
            self.running_mode = requested
            if self.pedestrian_pending:
                self.pedestrian_pending = False
                self.active, self.stage, self.elapsed = [], "WALK", 0.0
                self.reason = "Cruce peatonal protegido"
                return
            if requested == "fti":
                for offset in range(1, 5):
                    idx = (self.cursor + offset) % 4
                    if self.counts[idx] > 0:
                        self.cursor, self.active, self.stage, self.elapsed = idx, [APPROACHES[idx]], "GREEN", 0.0
                        self.reason = f"Demanda C{idx + 1}: turno de 5 s"
                        return
                self.reason = "Sin demanda: los cuatro accesos en rojo"
                return
            axis = "EW" if self.last_axis == "NS" else "NS"
            if requested == "adaptive":
                ns, ew = self.queues[0] + self.queues[2], self.queues[1] + self.queues[3]
                priority_has_demand = self.priority in GROUPS and any(self.counts[APPROACHES.index(a)] > 0 for a in GROUPS[self.priority])
                if priority_has_demand:
                    axis = self.priority
                    opposite = "EW" if axis == "NS" else "NS"
                    indexes = (1, 3) if opposite == "EW" else (0, 2)
                    if max(self.wait[i] for i in indexes) >= 30.0:
                        axis = opposite
                elif ns == 0 and ew > 0:
                    axis = "NS" if max(self.wait[0], self.wait[2]) >= 30.0 else "EW"
                elif ew == 0 and ns > 0:
                    axis = "EW" if max(self.wait[1], self.wait[3]) >= 30.0 else "NS"
                elif not self.active and max(self.wait) > 25:
                    axis = "NS" if self.wait[0] + self.wait[2] >= self.wait[1] + self.wait[3] else "EW"
            self.active, self.last_axis, self.stage, self.elapsed = list(GROUPS[axis]), axis, "GREEN", 0.0
            self.reason = ("Respaldo fijo por pérdida de sensores" if self.fallback else
                           "Alternancia fija de 11 s" if requested == "fixed" else
                           "Prioridad V2I con transición" if self.priority == axis else "Balance de colas y espera")
            return
        if self.stage == "GREEN":
            end_turn = self.elapsed >= self.green_duration()
            end_turn |= self.pedestrian_pending and self.elapsed >= 4.0
            if self.running_mode == "adaptive":
                current = sum(self.queues[APPROACHES.index(a)] for a in self.active)
                other = sum(self.queues) - current
                end_turn |= self.elapsed >= 6.5 and other > current + 1.0
                end_turn |= self.elapsed >= 4.0 and current == 0.0 and other > 0.0
                end_turn |= self.elapsed >= 6.5 and bool(self.priority) and self.priority != self.last_axis
            if end_turn:
                self.stage, self.elapsed, self.reason = "YELLOW", 0.0, "Fin de turno: amarillo"

    def snapshot(self):
        return {"mode": self.mode, "running_mode": self.running_mode, "stage": self.stage,
                "active": self.active[:], "elapsed": self.elapsed, "counts": self.counts[:],
                "queues": self.queues[:], "sensor_age": self.sensor_age, "cursor": self.cursor,
                "last_axis": self.last_axis, "wait": self.wait[:], "priority": self.priority,
                "clearance": self.clearance, "fallback": self.fallback, "reason": self.reason,
                "pedestrian_pending": self.pedestrian_pending}
