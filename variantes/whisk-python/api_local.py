"""API HTTP de lectura para clientes locales de la simulación FTI."""
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
from threading import RLock, Thread
from urllib.parse import parse_qs, urlsplit

from datos import SCHEMA_VERSION

PREFIX = "/api/v1"


class LocalAPI:
    """El servidor consulta Telemetry y nunca accede a Tk ni al simulador."""
    def __init__(self, data):
        self.data = data
        self._lock = RLock()
        self._server = None
        self._thread = None
        self._token = ""

    @property
    def running(self):
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def url(self):
        with self._lock:
            return f"http://127.0.0.1:{self._server.server_port}{PREFIX}" if self._server else ""

    @property
    def token(self):
        with self._lock:
            return self._token

    def start(self, port=0):
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("El puerto debe ser un entero entre 0 y 65535.")
        with self._lock:
            if self._server is not None:
                return self.url
            token = secrets.token_urlsafe(32)
            owner = self

            class Handler(BaseHTTPRequestHandler):
                server_version = "FTI"
                sys_version = ""
                protocol_version = "HTTP/1.1"

                def setup(self):
                    super().setup()
                    self.connection.settimeout(3)

                def log_message(self, *_args):
                    pass

                def send_json(self, status, payload, *, head=False):
                    body = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")).encode("utf-8")
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    if not head:
                        try:
                            self.wfile.write(body)
                        except (BrokenPipeError, ConnectionResetError):
                            pass

                def error(self, code, message):
                    self.send_json(code, {"schema_version": SCHEMA_VERSION, "error": message})

                def do_GET(self):
                    try:
                        self.read_request()
                    except (ValueError, UnicodeError):
                        self.error(400, "Solicitud o parámetros inválidos.")

                def read_request(self):
                    parsed = urlsplit(self.path)
                    allowed_hosts = (f"127.0.0.1:{self.server.server_port}",
                                     f"localhost:{self.server.server_port}")
                    if self.headers.get("Host", "") not in allowed_hosts:
                        self.error(400, "Host local inválido.")
                        return
                    if parsed.path == PREFIX + "/health" and not parsed.query:
                        self.send_json(200, {"schema_version": SCHEMA_VERSION, "status": "ok"})
                        return
                    authorization = self.headers.get("Authorization", "")
                    if not compare_digest(authorization.encode("utf-8"), ("Bearer " + token).encode("utf-8")):
                        self.error(401, "Se requiere el token de sesión en Authorization: Bearer.")
                        return
                    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
                    if parsed.path == PREFIX + "/history":
                        if set(query) - {"limit"}:
                            raise ValueError("Parámetro desconocido.")
                        limit = query.get("limit")
                        if limit is not None and (len(limit) != 1 or not limit[0].isascii() or not limit[0].isdigit()):
                            raise ValueError("limit inválido.")
                        self.send_json(200, owner.data.history(int(limit[0]) if limit else None))
                        return
                    if query:
                        raise ValueError("El recurso no admite parámetros.")
                    readers = {
                        PREFIX + "/state": owner.data.snapshot,
                        PREFIX + "/metrics": owner.data.metrics,
                        PREFIX + "/vehicles": owner.data.vehicles,
                    }
                    reader = readers.get(parsed.path)
                    if reader is None:
                        self.error(404, "Recurso no encontrado.")
                        return
                    payload = reader()
                    if payload is None:
                        self.error(503, "La simulación aún no ha publicado datos.")
                        return
                    self.send_json(200, payload)

                def reject_write(self):
                    self.error(405, "La API admite consultas GET.")

                do_POST = reject_write
                do_PUT = reject_write
                do_PATCH = reject_write
                do_DELETE = reject_write
                do_OPTIONS = reject_write

                def do_HEAD(self):
                    self.send_json(405, {"schema_version": SCHEMA_VERSION,
                                         "error": "La API admite consultas GET."}, head=True)

            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            server.daemon_threads = True
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .1},
                            name="FTI API local", daemon=True)
            self._server, self._thread, self._token = server, thread, token
            try:
                thread.start()
            except RuntimeError:
                self._server = self._thread = None
                self._token = ""
                server.server_close()
                raise
            return self.url

    def stop(self):
        with self._lock:
            server, thread = self._server, self._thread
            if server is None:
                return
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            self._server = self._thread = None
            self._token = ""
