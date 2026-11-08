"""Ensayo HTTP real de recepción, consultas y persistencia del servidor FTI."""
import copy
import asyncio
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import secrets
import socket
import tempfile
from threading import Thread
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import uvicorn

from datos import Telemetry
from servidor.app import MAX_BODY, create_app
from verificar_datos import state


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="fti-servidor-")
        self.database = Path(self.folder.name) / "datos.sqlite3"
        self.token = secrets.token_urlsafe(32)
        self.source = Telemetry()
        self.start()

    def tearDown(self):
        self.stop()
        self.folder.cleanup()

    def start(self):
        self.socket = socket.socket()
        self.socket.bind(("127.0.0.1", 0))
        port = self.socket.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}/api/v1"
        self.application = create_app(token=self.token, read_token=getattr(self, "read_token", ""),
                                      database=self.database, capacity=3,
                                      cors_origins=["https://panel.example.test"])
        config = uvicorn.Config(self.application,
                                log_level="error", lifespan="on", http="h11", ws="none")
        self.server = uvicorn.Server(config)
        self.thread = Thread(target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 8
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(self.server.started, "El servidor no inició.")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive(), "El servidor no terminó.")
        self.socket.close()

    def request(self, route, payload=None, *, token=True, raw=None, headers=None):
        request_headers = {"Authorization": "Bearer " + self.token} if token else {}
        if payload is not None:
            raw = json.dumps(payload, allow_nan=False).encode("utf-8")
        if raw is not None:
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        request = Request(self.url + route, data=raw, headers=request_headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read()), response.headers

    def packet(self, seconds=0, sequence=1, epoch=0):
        self.source.publish(state(seconds, epoch), {"connected": True})
        packet = self.source.snapshot()
        packet["delivery_sequence"] = sequence
        return packet

    def test_receive_query_reset_and_history_capacity(self):
        self.assertEqual(self.request("/health", token=False)[0], 200)
        self.assertEqual(self.request("/state", token=False)[0], 401)
        self.assertEqual(self.request("/state")[0], 503)
        first = self.packet()
        status, response, _ = self.request("/ingest", first)
        self.assertEqual(status, 200)
        self.assertTrue(response["accepted"])
        self.assertEqual(response["session_id"], self.source.session_id)
        received = self.request("/state")[1]
        self.assertEqual(received["session_id"], first["session_id"])
        self.assertEqual(received["sampled_at"], first["sampled_at"])
        self.assertEqual(received["simulation"], first["simulation"])
        for n in range(1, 5):
            self.assertEqual(self.request("/ingest", self.packet(n, n + 1))[0], 200)
        history = self.request("/history")[1]
        self.assertEqual(history["count"], 3)
        self.assertEqual(history["total_samples"], 5)
        self.assertEqual([row["simulation_time_s"] for row in history["items"]], [2, 3, 4])
        self.assertEqual(self.request("/history?limit=1")[1]["count"], 1)
        self.assertEqual(self.request("/vehicles")[1]["count"], 36)
        self.assertEqual(self.request("/metrics")[1]["simulation_time_s"], 4)
        self.request("/ingest", self.packet(0, 6, epoch=1))
        self.assertEqual(self.request("/history")[1]["items"][-1]["epoch"], 1)
        for origin, allowed in (("https://panel.example.test", True), ("https://otro.test", False)):
            _, _, headers = self.request("/state", headers={"Origin": origin})
            self.assertEqual(headers.get("Access-Control-Allow-Origin"), origin if allowed else None)

    def test_duplicate_and_out_of_order_survive_restart(self):
        newest = self.packet(10, 10)
        self.assertTrue(self.request("/ingest", newest)[1]["accepted"])
        for sequence in (10, 9, 1):
            older = copy.deepcopy(newest)
            older["delivery_sequence"] = sequence
            older["simulation"]["time"] = 1
            response = self.request("/ingest", older)[1]
            self.assertTrue(response["accepted"])
            self.assertTrue(response["duplicate"])
        self.assertEqual(self.request("/state")[1]["simulation"]["time"], 10)
        self.stop()
        self.start()
        self.assertEqual(self.request("/state")[1]["simulation"]["time"], 10)
        self.assertEqual(self.request("/history")[1]["count"], 1)
        self.assertTrue(self.request("/ingest", newest)[1]["duplicate"])
        newer = self.packet(11, 11)
        self.assertTrue(self.request("/ingest", newer)[1]["accepted"])
        self.assertEqual(self.request("/state")[1]["simulation"]["time"], 11)

    def test_bad_payload_auth_and_body_limits(self):
        valid = self.packet()
        self.assertEqual(self.request("/ingest", valid, token=False)[0], 401)
        self.assertEqual(self.request("/ingest", valid, headers={"Authorization": "Bearer distinto"})[0], 401)
        cases = []
        for key, value in (("schema_version", "otra"), ("session_id", "sesión"),
                           ("delivery_sequence", True), ("delivery_sequence", -1),
                           ("sampled_at", "2026-11-07T10:00:00")):
            bad = copy.deepcopy(valid)
            bad[key] = value
            cases.append(bad)
        for field, value in (("time", -1), ("time", True), ("epoch", -1), ("paused", "false")):
            bad = copy.deepcopy(valid)
            bad["simulation"][field] = value
            cases.append(bad)
        bad = copy.deepcopy(valid)
        bad["simulation"]["cars"].append(bad["simulation"]["cars"][0])
        cases.append(bad)
        for bad in cases:
            self.assertEqual(self.request("/ingest", bad)[0], 422)
        self.assertEqual(self.request("/ingest", raw=b'{"a":1,"a":2}')[0], 422)
        self.assertEqual(self.request("/ingest", raw=b'{"time": NaN}')[0], 422)
        self.assertEqual(self.request("/ingest", raw=b"[]")[0], 422)
        self.assertEqual(self.request("/ingest", raw=b"\xff")[0], 422)
        address = self.url.split("/")[2]
        with closing(http.client.HTTPConnection(address, timeout=3)) as client:
            client.putrequest("POST", "/api/v1/ingest")
            client.putheader("Authorization", "Bearer " + self.token)
            client.putheader("Content-Type", "application/json")
            client.putheader("Content-Length", str(MAX_BODY + 1))
            client.endheaders()
            response = client.getresponse()
            self.assertEqual(response.status, 413)
            response.read()
        self.assertEqual(self.request("/ingest", valid, headers={"Content-Type": "text/plain"})[0], 415)
        for query in ("limit=0", "limit=4", "limit=-1", "limit=abc", "limit=", "limit=1&limit=2", "otro=1"):
            self.assertEqual(self.request("/history?" + query)[0], 422)
        self.assertEqual(self.request("/ingest", valid)[0], 200)

    def test_concurrent_ingest_and_storage_rollback(self):
        packets = [self.packet(n, n) for n in range(1, 21)]
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda packet: self.request("/ingest", packet), packets))
        self.assertTrue(all(result[0] == 200 for result in results))
        self.assertEqual(self.request("/state")[1]["simulation"]["time"], 20)
        history = self.request("/history")[1]["items"]
        times = [row["simulation_time_s"] for row in history]
        self.assertEqual(times, sorted(set(times)))
        store = self.application.state.store
        with store._lock:
            store.db.execute("PRAGMA query_only=ON")
        try:
            self.assertEqual(self.request("/ingest", self.packet(21, 21))[0], 503)
            self.assertEqual(self.request("/state")[1]["simulation"]["time"], 20)
        finally:
            with store._lock:
                store.db.execute("PRAGMA query_only=OFF")
        self.assertEqual(self.request("/ingest", self.packet(21, 21))[0], 200)
        self.assertEqual(self.request("/state")[1]["simulation"]["time"], 21)

    def test_read_only_token_can_query_but_cannot_ingest(self):
        self.stop()
        self.read_token = secrets.token_urlsafe(32)
        self.start()
        self.assertEqual(self.request("/ingest", self.packet())[0], 200)
        headers = {"Authorization": "Bearer " + self.read_token}
        for route in ("/state", "/metrics", "/vehicles", "/history"):
            self.assertEqual(self.request(route, headers=headers)[0], 200)
        self.assertEqual(self.request("/ingest", self.packet(1, 2), headers=headers)[0], 401)
        self.assertEqual(self.request("/state")[1]["simulation"]["time"], 0)

    def test_invalid_read_token_fails_before_storage_initializes(self):
        async def validate():
            for read_token in ("corto", "ñ" * 24, self.token):
                application = create_app(token=self.token, read_token=read_token,
                                         database=self.database, cors_origins=[])
                with self.assertRaisesRegex(RuntimeError, "FTI_READ_TOKEN"):
                    async with application.router.lifespan_context(application):
                        pass
                self.assertFalse(hasattr(application.state, "store"))
        asyncio.run(validate())


if __name__ == "__main__":
    unittest.main(verbosity=2)
