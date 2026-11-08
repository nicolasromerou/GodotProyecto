"""Comprueba el transporte de telemetría con servidores HTTP locales de prueba."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import unittest

from conector import ServerConnector, ingest_url
from datos import Telemetry
from simulacion import Simulation


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError("No se recibió el resultado esperado del conector.")


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.reply = 200
        self.fail_first = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                owner.requests.append((self.path, self.headers.get("Authorization"), json.loads(raw)))
                status = 503 if owner.fail_first and len(owner.requests) == 1 else owner.reply
                body = b'{"accepted":true}'
                self.send_response(status)
                if status == 307:
                    self.send_header("Location", "/ruta-inesperada")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.connector = ServerConnector()
        self.data = Telemetry()
        self.data.publish(Simulation("normal", paused=True).snapshot(0, ""))

    def tearDown(self):
        self.connector.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.assertFalse(self.connector.running)

    def test_endpoint_validation(self):
        self.assertEqual(ingest_url(self.base), self.base + "/api/v1/ingest")
        self.assertEqual(ingest_url(self.base + "/api/v1/"), self.base + "/api/v1/ingest")
        for value in ("http://example.org", "file:///state", "https://user:token@example.org",
                      "https://example.org/?token=secreto", "http://127.0.0.1:0"):
            with self.assertRaises(ValueError):
                ingest_url(value)
        for token in ("", "espacio en token", "token\n"):
            with self.assertRaises(ValueError):
                self.connector.start(self.base, token)

    def test_delivery_is_confirmed_and_latest_wins(self):
        self.connector.start(self.base, "token-prueba")
        first = self.data.snapshot()
        self.connector.publish(first)
        self.data.publish({**first["simulation"], "time": 4})
        last = self.data.snapshot()
        self.connector.publish(last)
        wait_for(lambda: self.connector.status["sent_count"] == 1)
        path, authorization, body = self.requests[0]
        self.assertEqual(path, "/api/v1/ingest")
        self.assertEqual(authorization, "Bearer token-prueba")
        self.assertEqual(body["simulation"]["time"], 4)
        self.assertEqual(body["session_id"], self.data.session_id)
        self.assertGreater(body["delivery_sequence"], 0)
        self.assertTrue(self.connector.status["last_sent"])
        self.assertNotIn("token-prueba", json.dumps(self.connector.status))

    def test_recovers_after_server_failure(self):
        self.fail_first = True
        self.connector.start(self.base, "token-prueba")
        self.connector.publish(self.data.snapshot())
        wait_for(lambda: "503" in self.connector.status["error"])
        self.assertEqual(self.connector.status["sent_count"], 0)
        wait_for(lambda: self.connector.status["sent_count"] == 1)
        self.assertFalse(self.connector.status["error"])
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[0][2]["delivery_sequence"], self.requests[1][2]["delivery_sequence"])

    def test_does_not_forward_credentials_to_redirect(self):
        self.reply = 307
        self.connector.start(self.base, "token-prueba")
        self.connector.publish(self.data.snapshot())
        wait_for(lambda: "307" in self.connector.status["error"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.connector.status["sent_count"], 0)
        self.connector.stop()
        self.assertFalse(self.connector.running)


if __name__ == "__main__":
    unittest.main(verbosity=2)
