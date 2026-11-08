"""Salida de telemetría hacia un servidor configurable, fuera del hilo de Tk."""
from datetime import datetime, timezone
import http.client
import ipaddress
import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, stream, code, message, headers, url):
        return None


def ingest_url(value):
    try:
        parts = urllib.parse.urlsplit(value.strip())
        port = parts.port
    except (AttributeError, ValueError) as error:
        raise ValueError("Escribe una URL de servidor válida.") from error
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Usa una dirección https:// de servidor o http://127.0.0.1 para pruebas.")
    if parts.username or parts.password or parts.query or parts.fragment or "\n" in value or "\r" in value:
        raise ValueError("La URL debe contener solo el servidor y la ruta de la API.")
    local = parts.hostname.lower() == "localhost"
    try:
        local = local or ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        pass
    if parts.scheme == "http" and not local:
        raise ValueError("La conexión a un servidor remoto requiere HTTPS.")
    if port == 0:
        raise ValueError("Selecciona un puerto entre 1 y 65535.")
    path = parts.path.rstrip("/")
    if not path:
        path = "/api/v1"
    if not path.endswith("/ingest"):
        path += "/ingest"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


class ServerConnector:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._pending = None
        self._sequence = 0
        self._status = {"running": False, "url": "", "last_sent": None,
                        "error": "", "sent_count": 0, "pending": False}

    @property
    def status(self):
        with self._lock:
            return dict(self._status)

    @property
    def running(self):
        return self.status["running"]

    def start(self, url, token):
        endpoint = ingest_url(url)
        if (not isinstance(token, str) or not token.strip()
                or "\r" in token or "\n" in token
                or any(not 33 <= ord(c) <= 126 for c in token.strip())):
            raise ValueError("Escribe el token del servidor.")
        if len(token) > 4096:
            raise ValueError("El token del servidor es demasiado largo.")
        if self._thread is not None and self._thread.is_alive():
            raise ValueError("La conexión anterior sigue terminando. Vuelve a intentarlo en unos segundos.")
        self._stop = threading.Event()
        with self._lock:
            self._pending = None
            self._status.update(running=True, url=endpoint, error="", pending=False)
        self._thread = threading.Thread(target=self._run, args=(endpoint, token.strip()), name="FTI-envio", daemon=True)
        self._thread.start()

    def publish(self, snapshot):
        if not self.running:
            return
        with self._lock:
            self._sequence += 1
            self._pending = {**snapshot, "delivery_sequence": self._sequence}
            self._status["pending"] = True

    def stop(self):
        self._stop.set()
        with self._lock:
            self._pending = None
            self._status.update(running=False, pending=False)

    def close(self):
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=4)

    def _run(self, endpoint, token):
        try:
            self._deliver(endpoint, token)
        except Exception:
            logging.getLogger("fti").exception("El conector de datos terminó inesperadamente")
            with self._lock:
                self._status["error"] = "La conexión terminó. Consulta los registros y vuelve a conectarla."
        finally:
            with self._lock:
                self._status["running"] = False

    def _deliver(self, endpoint, token):
        opener = urllib.request.build_opener(NoRedirect())
        delay = 1.0
        while not self._stop.wait(delay):
            with self._lock:
                payload = self._pending
            if payload is None:
                continue
            try:
                body = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
                if len(body) > 2 * 1024 * 1024:
                    raise ValueError("La instantánea excedió el límite de 2 MiB del servidor.")
                request = urllib.request.Request(endpoint, data=body, method="POST", headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "FTI/1.0",
                })
                with opener.open(request, timeout=3) as response:
                    result = json.loads(response.read(8193))
                    if not isinstance(result, dict) or result.get("accepted") is not True:
                        raise ValueError("El servidor respondió sin confirmar los datos.")
                if self._stop.is_set():
                    return
                with self._lock:
                    if self._pending is payload:
                        self._pending = None
                    self._status.update(last_sent=datetime.now(timezone.utc).isoformat(),
                                        sent_count=self._status["sent_count"] + 1,
                                        error="", pending=self._pending is not None)
                delay = 1.0
            except (OSError, ValueError, http.client.HTTPException, urllib.error.URLError) as error:
                if self._stop.is_set():
                    return
                message = f"El servidor respondió HTTP {error.code}." if isinstance(error, urllib.error.HTTPError) else str(error)
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                with self._lock:
                    self._status["error"] = message
                delay = min(30.0, delay * 2)
