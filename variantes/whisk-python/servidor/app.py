"""API versionada para recibir y consultar datos de la aplicación FTI."""
from contextlib import asynccontextmanager
from datetime import datetime
from hmac import compare_digest
import json
import math
import os
import re
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware
from urllib.parse import urlsplit

from datos import SCHEMA_VERSION
from .almacen import Store

MAX_BODY = 2 * 1024 * 1024
PREFIX = "/api/v1"
KEY = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
SESSION = re.compile(r"^[a-f0-9]{32}$")
INGEST_BODY = {
    "required": True,
    "content": {"application/json": {"schema": {
        "type": "object",
        "required": ["schema_version", "session_id", "sampled_at", "delivery_sequence", "simulation"],
        "properties": {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "session_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
            "sampled_at": {"type": "string", "format": "date-time"},
            "delivery_sequence": {"type": "integer", "minimum": 1},
            "viewer": {"type": "object"},
            "simulation": {
                "type": "object",
                "required": ["time", "epoch", "cars", "metrics", "controller"],
                "properties": {
                    "time": {"type": "number", "minimum": 0, "description": "Segundos de simulación."},
                    "epoch": {"type": "integer", "minimum": 0},
                    "cars": {"type": "array", "maxItems": 5000, "items": {"type": "object"}},
                    "network_vehicles": {"type": "array", "maxItems": 5000, "items": {"type": "object"}},
                    "metrics": {"type": "object", "required": ["vehicles"]},
                    "controller": {"type": "object"},
                },
            },
        },
    }}},
}


def parse_envelope(raw):
    def no_constant(_value):
        raise ValueError("Los números deben ser finitos.")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Hay campos repetidos.")
            result[key] = value
        return result

    envelope = json.loads(raw, parse_constant=no_constant, object_pairs_hook=unique_object)
    if not isinstance(envelope, dict):
        raise ValueError("La instantánea debe ser un objeto JSON.")
    nodes = [0]

    def bounded(value, depth=0):
        nodes[0] += 1
        if depth > 12 or nodes[0] > 75000:
            raise ValueError("La instantánea contiene demasiados elementos.")
        if isinstance(value, str) and len(value) > 4096:
            raise ValueError("Un texto excedió el tamaño permitido.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Los números deben ser finitos.")
        if isinstance(value, dict):
            if any(len(key) > 128 for key in value):
                raise ValueError("Un nombre de campo excedió el tamaño permitido.")
            for item in value.values():
                bounded(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                bounded(item, depth + 1)

    bounded(envelope)
    session = envelope.get("session_id")
    sequence = envelope.get("delivery_sequence")
    if (envelope.get("schema_version") != SCHEMA_VERSION or not isinstance(session, str)
            or not SESSION.fullmatch(session) or type(sequence) is not int or not 1 <= sequence < 2 ** 63):
        raise ValueError("Esquema, sesión o secuencia de entrega inválidos.")
    sampled_at = envelope.get("sampled_at")
    if not isinstance(sampled_at, str) or len(sampled_at) > 64:
        raise ValueError("sampled_at debe ser una fecha ISO 8601 con zona horaria.")
    if datetime.fromisoformat(sampled_at.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("sampled_at requiere zona horaria.")
    simulation, viewer = envelope.get("simulation"), envelope.get("viewer", {})
    if not isinstance(simulation, dict) or not isinstance(viewer, dict):
        raise ValueError("simulation y viewer deben ser objetos.")
    epoch, seconds = simulation.get("epoch"), simulation.get("time")
    if (type(epoch) is not int or not 0 <= epoch < 2 ** 63
            or type(seconds) not in (int, float) or not 0 <= seconds < 1e12):
        raise ValueError("epoch o time inválidos.")
    metrics, controller = simulation.get("metrics"), simulation.get("controller")
    if not isinstance(metrics, dict) or not isinstance(controller, dict):
        raise ValueError("Faltan metrics o controller.")
    for field in ("vehicles", "queued", "crossings", "transfers", "turns", "blocked_moves"):
        if field in metrics and (type(metrics[field]) is not int or metrics[field] < 0):
            raise ValueError(f"metrics.{field} debe ser un entero positivo o cero.")
    if type(metrics.get("vehicles")) is not int or metrics["vehicles"] > 5000:
        raise ValueError("metrics.vehicles debe indicar hasta 5000 vehículos.")
    for field in ("speed_kmh", "mean_wait"):
        if field in metrics and (type(metrics[field]) not in (int, float) or metrics[field] < 0):
            raise ValueError(f"metrics.{field} debe ser un número positivo o cero.")
    for field in ("paused", "sensors", "coordination"):
        if field in simulation and type(simulation[field]) is not bool:
            raise ValueError(f"{field} debe ser verdadero o falso.")
    if "queues" in controller:
        queues = controller["queues"]
        if (not isinstance(queues, list) or len(queues) != 4
                or any(type(n) not in (int, float) or n < 0 for n in queues)):
            raise ValueError("controller.queues debe contener cuatro cantidades.")
    for field in ("cars", "network_vehicles"):
        vehicles = simulation.get(field, [] if field == "network_vehicles" else None)
        if not isinstance(vehicles, list) or len(vehicles) > 5000:
            raise ValueError(f"{field} debe ser una lista de hasta 5000 vehículos.")
        ids = set()
        for car in vehicles:
            if not isinstance(car, dict):
                raise ValueError("Un vehículo tiene formato inválido.")
            identity, model = car.get("id"), car.get("model")
            if (type(identity) is not int or not 1 <= identity < 2 ** 63 or identity in ids
                    or not isinstance(model, str) or not KEY.fullmatch(model)):
                raise ValueError("Identificador o modelo de vehículo inválido.")
            for axis in ("x", "z", "yaw"):
                coordinate = car.get(axis)
                if type(coordinate) not in (int, float) or abs(coordinate) > 1e9:
                    raise ValueError("Pose de vehículo inválida.")
            ids.add(identity)
    if "network_vehicles" in simulation:
        network_ids = {car["id"] for car in simulation["network_vehicles"]}
        if metrics["vehicles"] != len(network_ids) or not {car["id"] for car in simulation["cars"]} <= network_ids:
            raise ValueError("La cantidad de vehículos no coincide con las poses de la red.")
    envelope = {key: envelope.get(key, {}) for key in
                ("schema_version", "session_id", "sampled_at", "simulation", "viewer")}
    return envelope, sequence


def create_app(*, token=None, read_token=None, database=None, capacity=3600, cors_origins=None):
    @asynccontextmanager
    async def lifespan(application):
        configured_token = token if token is not None else os.environ.get("FTI_API_TOKEN", "")
        if not isinstance(configured_token, str) or len(configured_token) < 24 or not configured_token.isascii():
            raise RuntimeError("Configura FTI_API_TOKEN con al menos 24 caracteres ASCII.")
        configured_read_token = read_token if read_token is not None else os.environ.get("FTI_READ_TOKEN", "")
        if (not isinstance(configured_read_token, str)
                or configured_read_token and (len(configured_read_token) < 24 or not configured_read_token.isascii()
                                              or configured_read_token == configured_token)):
            raise RuntimeError("FTI_READ_TOKEN requiere al menos 24 caracteres ASCII y un valor distinto de FTI_API_TOKEN.")
        application.state.token = configured_token
        application.state.read_token = configured_read_token
        application.state.store = Store(database or os.environ.get("FTI_DATA_DB", "datos/fti.sqlite3"), capacity)
        try:
            yield
        finally:
            application.state.store.close()

    application = FastAPI(title="FTI · Datos de simulación", version="1.0",
                          lifespan=lifespan, docs_url="/docs", redoc_url=None)
    origins = (cors_origins if cors_origins is not None else
               [origin.strip() for origin in os.environ.get("FTI_CORS_ORIGINS", "").split(",") if origin.strip()])
    for origin in origins:
        parsed = urlsplit(origin)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.path or parsed.query or parsed.fragment or "*" in origin):
            raise ValueError("FTI_CORS_ORIGINS requiere orígenes HTTP/HTTPS concretos.")
    if origins:
        application.add_middleware(CORSMiddleware, allow_origins=origins,
                                   allow_methods=["GET"], allow_headers=["Authorization", "Content-Type"])
    security = HTTPBearer(auto_error=False)

    def authenticate(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)):
        provided = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
        provided_bytes = provided.encode("utf-8")
        authorized = compare_digest(provided_bytes, request.app.state.token.encode("utf-8"))
        if request.method == "GET" and request.app.state.read_token:
            authorized |= compare_digest(provided_bytes, request.app.state.read_token.encode("utf-8"))
        if not authorized:
            raise HTTPException(status_code=401, detail="Token de acceso inválido.",
                                headers={"WWW-Authenticate": "Bearer"})

    @application.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.exception_handler(sqlite3.Error)
    async def storage_error(_request, _error):
        return JSONResponse({"schema_version": SCHEMA_VERSION,
                             "error": "El almacenamiento no pudo completar la operación."}, status_code=503)

    @application.get(PREFIX + "/health")
    def health():
        return {"schema_version": SCHEMA_VERSION, "status": "ok"}

    @application.post(PREFIX + "/ingest", dependencies=[Depends(authenticate)],
                      openapi_extra={"requestBody": INGEST_BODY})
    async def ingest(request: Request):
        if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            raise HTTPException(415, "Envía Content-Type application/json.")
        length = request.headers.get("content-length")
        if length is not None and (len(length) > 10 or not length.isascii()
                                   or not length.isdigit() or int(length) > MAX_BODY):
            raise HTTPException(413, "La instantánea excede 2 MiB.")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > MAX_BODY:
                raise HTTPException(413, "La instantánea excede 2 MiB.")
            raw.extend(chunk)
        try:
            envelope, sequence = parse_envelope(raw)
        except (ValueError, UnicodeError, OverflowError, RecursionError) as error:
            raise HTTPException(422, str(error)) from error
        return await run_in_threadpool(request.app.state.store.ingest, envelope, sequence)

    def latest(request, resource):
        payload = getattr(request.app.state.store.data, resource)()
        if payload is None:
            raise HTTPException(503, "Todavía no se ha recibido una instantánea.")
        return payload

    @application.get(PREFIX + "/state", dependencies=[Depends(authenticate)])
    def state(request: Request):
        return latest(request, "snapshot")

    @application.get(PREFIX + "/metrics", dependencies=[Depends(authenticate)])
    def metrics(request: Request):
        return latest(request, "metrics")

    @application.get(PREFIX + "/vehicles", dependencies=[Depends(authenticate)])
    def vehicles(request: Request):
        return latest(request, "vehicles")

    @application.get(PREFIX + "/history", dependencies=[Depends(authenticate)],
                     openapi_extra={"parameters": [{
                         "name": "limit", "in": "query", "required": False,
                         "schema": {"type": "integer", "minimum": 1, "maximum": capacity},
                         "description": "Máximo de muestras recientes.",
                     }]})
    def history(request: Request):
        query = request.query_params
        values = query.getlist("limit")
        if set(query) - {"limit"} or len(values) > 1:
            raise HTTPException(422, "Se admite un único parámetro limit.")
        try:
            limit = int(values[0]) if values and values[0].isascii() and values[0].isdigit() else None
            if values and limit is None:
                raise ValueError("limit debe ser un entero positivo.")
            return request.app.state.store.history(limit)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    return application


app = create_app()
