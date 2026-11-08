"""Pruebas de muestreo, exportación y API sin abrir la interfaz."""
import csv
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from api_local import LocalAPI
from datos import Telemetry, atomic_write
from simulacion import Simulation


def state(seconds=0, epoch=0):
    snapshot = Simulation("normal", paused=True).snapshot(0, "")
    snapshot["time"], snapshot["epoch"] = seconds, epoch
    snapshot["network_vehicles"] = [dict(car, junction=5) for car in snapshot["cars"]] + [
        {"id": i, "model": "moto", "x": float(i), "z": 0.0, "yaw": 0.0, "junction": 5}
        for i in range(1, snapshot["metrics"]["vehicles"] - len(snapshot["cars"]) + 1)
    ]
    return snapshot


class DataTests(unittest.TestCase):
    def test_sampling_pause_reset_recording_and_capacity(self):
        data = Telemetry(max_history=3)
        snapshot = state()
        data.publish(snapshot)
        for n in range(20):
            snapshot["time"] = n / 20
            data.publish(snapshot)
        self.assertEqual(data.sample_count, 1)
        for n in range(1, 6):
            snapshot["time"] = n
            data.publish(snapshot)
        self.assertEqual([row["simulation_time_s"] for row in data.history()["items"]], [3, 4, 5])
        self.assertEqual(data.history()["total_samples"], 6)
        data.set_recording(False)
        snapshot["time"] = 6
        data.publish(snapshot)
        self.assertEqual(data.sample_count, 3)
        self.assertEqual(data.snapshot()["simulation"]["time"], 6)
        data.set_recording(True)
        data.publish(snapshot)
        self.assertEqual(data.history()["items"][-1]["simulation_time_s"], 6)
        snapshot["epoch"], snapshot["time"] = 1, 0
        data.publish(snapshot)
        self.assertEqual(data.history()["items"][-1]["epoch"], 1)
        self.assertEqual(data.history()["items"][-1]["simulation_time_s"], 0)
        self.assertEqual(data.history(limit=1)["count"], 1)
        for invalid in (0, -1, 4, True, "1"):
            with self.assertRaises(ValueError):
                data.history(invalid)

    def test_snapshot_isolation_network_and_finite_json(self):
        data = Telemetry()
        snapshot = state()
        snapshot["metrics"]["speed_kmh"] = float("nan")
        snapshot["network_vehicles"][0]["x"] = float("inf")
        data.publish(snapshot, {"connected": True})
        snapshot["cars"].clear()
        first = data.snapshot()
        self.assertIs(first["simulation"]["paused"], True)
        self.assertIsNone(first["simulation"]["metrics"]["speed_kmh"])
        self.assertEqual(data.vehicles()["scope"], "network")
        self.assertEqual(data.vehicles()["count"], 36)
        self.assertIsNone(data.vehicles()["items"][0]["x"])
        self.assertIsNone(data.metrics()["metrics"]["speed_kmh"])
        first["simulation"]["cars"].clear()
        self.assertEqual(len(data.snapshot()["simulation"]["cars"]), 4)
        json.dumps(data.snapshot(), allow_nan=False)
        self.assertIs(data.history()["items"][0]["viewer_connected"], True)

    def test_atomic_csv_json_and_snapshot_exports(self):
        data = Telemetry()
        data.publish(state())
        data.publish(state(1))
        with tempfile.TemporaryDirectory(prefix="fti-datos-") as folder:
            folder = Path(folder)
            csv_path = data.export_history(folder / "Tráfico ñ.csv")
            with csv_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["simulation_time_s"], "1")
            self.assertEqual(rows[0]["network_vehicles"], "36")
            history = data.export_history(folder / "historial.json")
            self.assertEqual(json.loads(history.read_text(encoding="utf-8"))["count"], 2)
            exported = data.export_snapshot(folder / "estado.json")
            self.assertEqual(json.loads(exported.read_text(encoding="utf-8"))["simulation"]["time"], 1)
            previous = history.read_bytes()

            def interrupted(stream):
                stream.write("incompleto")
                raise OSError("ensayo de disco")

            with self.assertRaises(OSError):
                atomic_write(history, interrupted)
            self.assertEqual(history.read_bytes(), previous)
            self.assertEqual(list(folder.glob("*.tmp")), [])
            with self.assertRaises(ValueError):
                data.export_history(folder / "datos.txt")

    def test_concurrent_reads_remain_consistent(self):
        data = Telemetry(max_history=30)
        data.publish(state())
        failures = []

        def reader():
            try:
                for _ in range(80):
                    snapshot = data.snapshot()
                    json.dumps(snapshot, allow_nan=False)
                    self.assertEqual(len(snapshot["simulation"]["network_vehicles"]), 36)
                    self.assertLessEqual(data.history()["count"], 30)
            except BaseException as error:
                failures.append(error)

        threads = [threading.Thread(target=reader) for _ in range(3)]
        for thread in threads:
            thread.start()
        snapshot = state()
        for n in range(100):
            snapshot["time"] = n / 10
            data.publish(snapshot)
        for thread in threads:
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])


class APITests(unittest.TestCase):
    def setUp(self):
        self.data = Telemetry(max_history=10)
        self.api = LocalAPI(self.data)
        self.api.start()

    def tearDown(self):
        self.api.stop()

    def get(self, resource, token=True, headers=None, method="GET"):
        auth = {"Authorization": "Bearer " + self.api.token} if token else {}
        auth.update(headers or {})
        request = Request(self.api.url + resource, headers=auth, method=method)
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read()), response.headers

    def test_authenticated_routes_and_query_validation(self):
        status, payload, headers = self.get("/health", token=False)
        self.assertEqual((status, payload["status"]), (200, "ok"))
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(self.get("/state", token=False)[0], 401)
        self.assertEqual(self.get("/state", headers={"Authorization": "Bearer incorrecto"})[0], 401)
        self.assertEqual(self.get("/state")[0], 503)
        self.data.publish(state())
        for resource in ("/state", "/metrics", "/vehicles", "/history", "/history?limit=1"):
            status, payload, headers = self.get(resource)
            self.assertEqual(status, 200, resource)
            self.assertEqual(payload["schema_version"], "1.0")
            self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.get("/vehicles")[1]["count"], 36)
        self.assertEqual(self.get("/vehicles")[1]["items"][0]["junction"], 5)
        for query in ("?limit=0", "?limit=11", "?limit=-1", "?limit=abc", "?limit=",
                      "?limit=1&limit=2", "?otro=1", "?limit"):
            self.assertEqual(self.get("/history" + query)[0], 400, query)
        self.assertEqual(self.get("/state?limit=1")[0], 400)
        self.assertEqual(self.get("/inexistente")[0], 404)
        self.assertEqual(self.get("/state", headers={"Host": "external.invalid"})[0], 400)
        self.assertEqual(self.get("/state", method="POST")[0], 405)

    def test_stop_restart_and_port_conflict(self):
        first_url, first_token = self.api.url, self.api.token
        self.assertEqual(self.api.start(), first_url)
        self.assertEqual(self.api.token, first_token)
        self.api.stop()
        self.assertFalse(self.api.running)
        self.assertEqual(self.api.url, "")
        self.assertEqual(self.api.token, "")
        self.api.stop()
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            with self.assertRaises(OSError):
                self.api.start(occupied.getsockname()[1])
        self.assertFalse(self.api.running)
        self.api.start()
        self.assertNotEqual(self.api.token, first_token)
        self.assertEqual(self.get("/health", token=False)[0], 200)
        for port in (-1, 65536, True, "0"):
            with self.assertRaises(ValueError):
                self.api.start(port)

    def test_stop_does_not_wait_on_idle_client(self):
        split = self.api.url.split("/")[2]
        host, port = split.split(":")
        client = socket.create_connection((host, int(port)), timeout=2)
        try:
            before = time.monotonic()
            self.api.stop()
            self.assertLess(time.monotonic() - before, 1)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
