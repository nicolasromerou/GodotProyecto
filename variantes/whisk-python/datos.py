"""Instantáneas e historial acotado de la simulación, independientes de Tk."""
from collections import deque
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from threading import RLock
import uuid

SCHEMA_VERSION = "1.0"
HISTORY_FIELDS = (
    "session_id", "epoch", "simulation_time_s", "sampled_at", "scenario",
    "controller_mode", "running_mode", "phase", "paused", "sensors_online",
    "coordination", "network_vehicles", "i5_vehicles", "queued",
    "crossings_total", "crossings_last60s", "transfers", "turns",
    "blocked_moves", "average_speed_kmh", "average_wait_s", "viewer_connected",
    "queue_north", "queue_east", "queue_south", "queue_west",
)


def clean(value):
    """Copia valores JSON y sustituye números no finitos por null."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(item) for item in value]
    return None


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def atomic_write(path, write):
    """Completa una exportación antes de reemplazar el archivo de destino."""
    path = Path(path).expanduser().resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, prefix=f".{path.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


class Telemetry:
    def __init__(self, max_history=3600):
        if type(max_history) is not int or not 1 <= max_history <= 86400:
            raise ValueError("El historial debe admitir entre 1 y 86400 muestras.")
        self.session_id = uuid.uuid4().hex
        self.max_history = max_history
        self._lock = RLock()
        self._history = deque(maxlen=max_history)
        self._snapshot = None
        self._recording = True
        self._recorded_key = None
        self._total_samples = 0

    @property
    def recording(self):
        with self._lock:
            return self._recording

    @property
    def sample_count(self):
        with self._lock:
            return len(self._history)

    def set_recording(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("La grabación debe activarse o desactivarse.")
        with self._lock:
            self._recording = enabled

    def publish(self, state, viewer=None):
        if not isinstance(state, dict):
            raise ValueError("La instantánea debe ser un objeto.")
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "sampled_at": utc_now(),
            "simulation": clean(state),
            "viewer": clean(viewer or {}),
        }
        self._accept(snapshot)

    def ingest(self, envelope):
        """Recibe el mismo formato que snapshot() y conserva su sesión de origen."""
        if (not isinstance(envelope, dict) or envelope.get("schema_version") != SCHEMA_VERSION
                or not isinstance(envelope.get("simulation"), dict)
                or not isinstance(envelope.get("viewer", {}), dict)
                or not isinstance(envelope.get("session_id"), str)
                or not 1 <= len(envelope["session_id"]) <= 128
                or not isinstance(envelope.get("sampled_at"), str)):
            raise ValueError("La instantánea recibida no corresponde al esquema 1.0.")
        self._accept({key: clean(envelope.get(key, {})) for key in
                      ("schema_version", "session_id", "sampled_at", "simulation", "viewer")})

    def _accept(self, snapshot):
        current = snapshot["simulation"]
        time_value, epoch = current.get("time"), current.get("epoch")
        with self._lock:
            self._snapshot = snapshot
            if (not self._recording or type(time_value) not in (int, float)
                    or time_value < 0 or type(epoch) is not int):
                return
            key = snapshot["session_id"], epoch, math.floor(time_value + 1e-8)
            if key == self._recorded_key:
                return
            self._recorded_key = key
            self._history.append(self._row(snapshot))
            self._total_samples += 1

    def _row(self, snapshot):
        state = snapshot["simulation"]
        controller, metrics = state.get("controller", {}), state.get("metrics", {})
        queues = list(controller.get("queues", ())) + [None] * 4
        return dict(zip(HISTORY_FIELDS, (
            snapshot["session_id"], state.get("epoch"), state.get("time"), snapshot["sampled_at"],
            state.get("scenario"), controller.get("mode"), controller.get("running_mode"),
            controller.get("stage"), state.get("paused"), state.get("sensors"),
            state.get("coordination"), metrics.get("vehicles"), len(state.get("cars", ())),
            metrics.get("queued"), metrics.get("crossings"), state.get("recent_crossings"),
            metrics.get("transfers"), metrics.get("turns"), metrics.get("blocked_moves"),
            metrics.get("speed_kmh"), metrics.get("mean_wait"),
            snapshot["viewer"].get("connected"), *queues[:4],
        )))

    def snapshot(self):
        with self._lock:
            return clean(self._snapshot)

    def metrics(self):
        with self._lock:
            snapshot = self._snapshot
            if snapshot is None:
                return None
            state = snapshot["simulation"]
            return clean({
                "schema_version": SCHEMA_VERSION,
                "session_id": snapshot["session_id"],
                "sampled_at": snapshot["sampled_at"],
                "epoch": state.get("epoch"),
                "simulation_time_s": state.get("time"),
                "scenario": state.get("scenario"),
                "metrics": state.get("metrics", {}),
                "i5_vehicles": len(state.get("cars", ())),
                "crossings_last60s": state.get("recent_crossings"),
            })

    def vehicles(self):
        with self._lock:
            snapshot = self._snapshot
            if snapshot is None:
                return None
            state = snapshot["simulation"]
            vehicles = state.get("network_vehicles", state.get("cars", []))
            return clean({
                "schema_version": SCHEMA_VERSION,
                "session_id": snapshot["session_id"],
                "sampled_at": snapshot["sampled_at"],
                "epoch": state.get("epoch"),
                "simulation_time_s": state.get("time"),
                "scope": "network" if "network_vehicles" in state else "I-5",
                "count": len(vehicles),
                "items": vehicles,
            })

    def history(self, limit=None):
        if limit is not None and (type(limit) is not int or not 1 <= limit <= self.max_history):
            raise ValueError(f"limit debe ser un entero entre 1 y {self.max_history}.")
        with self._lock:
            items = list(self._history)
            if limit is not None:
                items = items[-limit:]
            return clean({
                "schema_version": SCHEMA_VERSION,
                "session_id": self._snapshot["session_id"] if self._snapshot else self.session_id,
                "recording": self._recording,
                "capacity": self.max_history,
                "sample_interval_simulation_s": 1,
                "total_samples": self._total_samples,
                "count": len(items),
                "items": items,
            })

    def export_history(self, path, format=None):
        path = Path(path)
        format = (format or path.suffix.lstrip(".")).lower()
        if format not in ("csv", "json"):
            raise ValueError("Elige un archivo CSV o JSON.")
        payload = self.history()
        if format == "json":
            return atomic_write(path, lambda stream: json.dump(payload, stream, ensure_ascii=False,
                                                               allow_nan=False, indent=2))

        def write_csv(stream):
            writer = csv.DictWriter(stream, fieldnames=HISTORY_FIELDS)
            writer.writeheader()
            writer.writerows(payload["items"])
        return atomic_write(path, write_csv)

    def export_snapshot(self, path):
        payload = self.snapshot()
        if payload is None:
            raise ValueError("Todavía no hay una instantánea para exportar.")
        return atomic_write(path, lambda stream: json.dump(payload, stream, ensure_ascii=False,
                                                           allow_nan=False, indent=2))
