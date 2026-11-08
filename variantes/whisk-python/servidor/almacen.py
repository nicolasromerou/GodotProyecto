"""Recepción atómica y consulta de telemetría persistida en SQLite."""
import json
import math
from pathlib import Path
import sqlite3
from threading import RLock

from datos import SCHEMA_VERSION, Telemetry


class Store:
    def __init__(self, database, capacity=3600):
        self.capacity = capacity
        self._lock = RLock()
        self.data = Telemetry(max_history=capacity)
        if str(database) != ":memory:":
            database = Path(database).expanduser().resolve()
            database.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(database), timeout=5, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS latest (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                envelope TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS samples (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                source_session TEXT NOT NULL,
                epoch INTEGER NOT NULL,
                second INTEGER NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(source_session, epoch, second)
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                source_session TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS totals (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                count INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO totals VALUES(1,0);
        """)
        row = self.db.execute("SELECT envelope FROM latest WHERE singleton=1").fetchone()
        if row:
            self.data.ingest(json.loads(row[0]))
        self.db.execute("DELETE FROM samples WHERE sequence NOT IN (SELECT sequence FROM samples ORDER BY sequence DESC LIMIT ?)",
                        (capacity,))
        self.db.commit()

    def ingest(self, envelope, sequence):
        session, simulation = envelope["session_id"], envelope["simulation"]
        epoch, time_value = simulation["epoch"], simulation["time"]
        accepted = {"schema_version": SCHEMA_VERSION, "accepted": True,
                    "session_id": session, "epoch": epoch, "simulation_time_s": time_value}
        encoded = json.dumps(envelope, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        row = self.data._row(envelope)
        encoded_row = json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        with self._lock:
            with self.db:
                last = self.db.execute("SELECT sequence FROM deliveries WHERE source_session=?", (session,)).fetchone()
                if last and sequence <= last[0]:
                    return {**accepted, "duplicate": True, "reason": "delivery_already_received"}
                self.db.execute("INSERT INTO latest VALUES(1,?) ON CONFLICT(singleton) DO UPDATE SET envelope=excluded.envelope",
                                (encoded,))
                inserted = self.db.execute(
                    "INSERT OR IGNORE INTO samples(source_session,epoch,second,payload) VALUES(?,?,?,?)",
                    (session, epoch, math.floor(time_value + 1e-8), encoded_row))
                if inserted.rowcount:
                    self.db.execute("UPDATE totals SET count=count+1 WHERE singleton=1")
                self.db.execute("INSERT INTO deliveries VALUES(?,?) ON CONFLICT(source_session) DO UPDATE SET sequence=excluded.sequence",
                                (session, sequence))
                self.db.execute("DELETE FROM samples WHERE sequence NOT IN (SELECT sequence FROM samples ORDER BY sequence DESC LIMIT ?)",
                                (self.capacity,))
            # Se publica después del commit para que una avería de disco no anuncie
            # como recibida una instantánea que todavía no quedó persistida.
            self.data.ingest(envelope)
        return accepted

    def history(self, limit=None):
        if limit is not None and not 1 <= limit <= self.capacity:
            raise ValueError(f"limit debe estar entre 1 y {self.capacity}.")
        with self._lock:
            rows = self.db.execute("SELECT payload FROM samples ORDER BY sequence DESC LIMIT ?",
                                   (limit or self.capacity,)).fetchall()
            count, = self.db.execute("SELECT count FROM totals WHERE singleton=1").fetchone()
            latest = self.data.snapshot()
        items = [json.loads(row[0]) for row in reversed(rows)]
        return {"schema_version": SCHEMA_VERSION,
                "session_id": latest["session_id"] if latest else None,
                "recording": True, "capacity": self.capacity,
                "sample_interval_simulation_s": 1,
                "total_samples": count, "count": len(items), "items": items}

    def close(self):
        with self._lock:
            self.db.close()
