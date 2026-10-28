#!/usr/bin/env python3
"""Project-scoped MCP stdio bridge. Python standard library only.

It launches bounded, headless Godot jobs. It never controls another running
editor, imports arbitrary files, evaluates arbitrary scripts, or opens a port.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parent.parent
PROTOCOLS = ("2025-03-26", "2024-11-05")
MAX_MESSAGE_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 20000
TEST_SCRIPTS = ("res://tests/test_controller.gd", "res://tests/test_world.gd")
TEST_COMPLETIONS = {
    TEST_SCRIPTS[0]: r"Controller: [1-9]\d* checks; 0 failures",
    TEST_SCRIPTS[1]: r"WORLD_TESTS [1-9]\d* passed, 0 failed",
}


def empty_schema() -> dict:
    return {"type": "object", "properties": {}, "additionalProperties": False}


TOOLS = [
    {"name": "fti_project_info", "description": "Describe este proyecto FTI de Godot y su conexión local. No consulta otros proyectos ni un editor en ejecución.", "inputSchema": empty_schema()},
    {"name": "fti_validate", "description": "Importa y valida este proyecto en Godot headless. Puede generar su caché .godot; no abre ventanas.", "inputSchema": empty_schema()},
    {"name": "fti_run_tests", "description": "Ejecuta las pruebas GDScript de semáforos y autos en este proyecto. Devuelve registros y códigos de salida.", "inputSchema": empty_schema()},
    {
        "name": "fti_simulate",
        "description": "Ejecuta una simulación determinista independiente a 60 Hz y devuelve su estado JSON. No cambia la ventana del editor ni una simulación abierta.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["fti", "adaptive", "fixed"], "default": "fti"},
                "seconds": {"type": "number", "minimum": 0, "maximum": 120, "default": 30},
                "sensor_enabled": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    },
]


class InvalidParams(Exception):
    pass


def resolve_godot(explicit: str | None) -> Path | None:
    configured = explicit or os.environ.get("GODOT_PATH")
    if configured:
        candidate = Path(configured).expanduser().resolve()
        return candidate if candidate.is_file() else None
    desktop = Path.home() / "Desktop"
    candidates = [desktop / "Godot_v4.7.2-stable_win64.exe"]
    candidates += sorted(desktop.glob("Godot*_win64.exe"), reverse=True)
    for name in ("godot", "godot4", "godot.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    return next((item.resolve() for item in candidates if item.is_file()), None)


def output_excerpt(stream) -> str:
    stream.seek(0, 2)
    size = stream.tell()
    if size <= MAX_OUTPUT_BYTES:
        stream.seek(0)
        return stream.read().decode("utf-8", "replace")
    half = MAX_OUTPUT_BYTES // 2
    stream.seek(0)
    first = stream.read(half)
    stream.seek(-half, 2)
    last = stream.read(half)
    return (first + b"\n[output truncated]\n" + last).decode("utf-8", "replace")


def scan_output(streams, completion_pattern: str | None = None) -> dict:
    """Inspect every log line; output clipping must never hide a failure."""
    errors = ("SCRIPT ERROR:", "Parse Error:", "ERROR:")
    # This exact Windows warning can occur in a restricted environment even
    # though the project uses no network. All other errors remain failures.
    environmental = {"ERROR: Failed to read the root certificate store.",
                     "ERROR: Failed to read root certificate store."}
    warnings: list[str] = []
    has_errors = False
    completion = None
    for stream in streams:
        stream.seek(0)
        for raw_line in stream:
            line = raw_line.decode("utf-8", "replace").strip()
            if line in environmental:
                if line not in warnings:
                    warnings.append(line)
            elif any(marker in line for marker in errors):
                has_errors = True
            if completion_pattern and re.fullmatch(completion_pattern, line):
                completion = line
    return {"has_errors": has_errors, "environment_warning": warnings or None,
            "completion_marker": completion}


def run_godot(godot: Path | None, args: list[str], timeout: int = 60,
              completion_pattern: str | None = None) -> dict:
    if godot is None:
        return {"ok": False, "error": "No se encontró Godot. Define GODOT_PATH o inicia el puente con --godot RUTA_EXE."}
    startup = None
    if os.name == "nt":
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
    with tempfile.TemporaryDirectory(prefix="fti-godot-") as scratch, tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        profile = Path(scratch)
        appdata = profile / "AppData"
        localdata = profile / "LocalAppData"
        appdata.mkdir()
        localdata.mkdir()
        environment = os.environ.copy()
        environment.update({"APPDATA": str(appdata), "LOCALAPPDATA": str(localdata)})
        command = [str(godot), "--headless", "--path", str(PROJECT),
                   "--log-file", str(profile / "godot.log"), *args]
        try:
            process = subprocess.run(command, cwd=PROJECT, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=err, timeout=timeout,
                                     shell=False, startupinfo=startup, env=environment)
            # Some GDScript errors leave Godot's process return code at zero.
            diagnostics = scan_output((out, err), completion_pattern)
            completed = completion_pattern is None or diagnostics["completion_marker"] is not None
            ok = process.returncode == 0 and not diagnostics["has_errors"] and completed
            result = {"ok": ok, "exit_code": process.returncode,
                      "stdout": output_excerpt(out), "stderr": output_excerpt(err),
                      "environment_warning": diagnostics["environment_warning"]}
            if completion_pattern is not None:
                result["completion_marker"] = diagnostics["completion_marker"]
                if not completed:
                    result["error"] = "Godot no devolvió el marcador de finalización exitosa de las pruebas."
            return result
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Godot superó el límite de {timeout} s.", "stdout": output_excerpt(out), "stderr": output_excerpt(err)}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}


def call_tool(name: str, arguments: dict, godot: Path | None) -> dict:
    known = {tool["name"] for tool in TOOLS}
    if name not in known:
        raise InvalidParams("Herramienta desconocida: " + name)
    allowed = {"mode", "seconds", "sensor_enabled"} if name == "fti_simulate" else set()
    if set(arguments) - allowed:
        raise InvalidParams("Argumentos desconocidos: " + ", ".join(sorted(set(arguments) - allowed)))
    if name == "fti_project_info":
        return {"ok": True, "project": str(PROJECT), "godot": str(godot) if godot else None,
                "transport": "stdio", "live_editor_control": False, "models_included": False,
                "scope": "Este proyecto y trabajos headless independientes",
                "tools": [item["name"] for item in TOOLS]}
    if name == "fti_validate":
        return run_godot(godot, ["--editor", "--import"])
    if name == "fti_run_tests":
        results = []
        for script in TEST_SCRIPTS:
            result = run_godot(godot, ["--script", script],
                               completion_pattern=TEST_COMPLETIONS[script])
            results.append({"script": script, **result})
        return {"ok": all(item["ok"] for item in results), "tests": results}
    mode = arguments.get("mode", "fti")
    seconds = arguments.get("seconds", 30)
    sensors = arguments.get("sensor_enabled", True)
    if mode not in ("fti", "adaptive", "fixed"):
        raise InvalidParams("mode debe ser fti, adaptive o fixed")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 120:
        raise InvalidParams("seconds debe ser un número finito entre 0 y 120")
    if not isinstance(sensors, bool):
        raise InvalidParams("sensor_enabled debe ser booleano")
    result = run_godot(godot, ["--script", "res://tools/simulate.gd", "--",
                               "mode=" + mode, "seconds=" + str(seconds),
                               "sensor_enabled=" + str(sensors).lower()])
    if not result["ok"]:
        return result
    markers = [line.removeprefix("FTI_JSON:") for line in result.get("stdout", "").splitlines() if line.startswith("FTI_JSON:")]
    if not markers:
        return {**result, "ok": False, "error": "Godot no devolvió el marcador FTI_JSON."}
    try:
        snapshot = json.loads(markers[-1])
    except json.JSONDecodeError:
        return {**result, "ok": False, "error": "Estado JSON de Godot no válido."}
    return {"ok": True, "independent_headless_run": True, "snapshot": snapshot}


class Server:
    def __init__(self, godot: Path | None):
        self.godot = godot
        self.initialized = False
        self.ready = False

    @staticmethod
    def error(request_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            return self.error(None, -32600, "Solicitud JSON-RPC inválida")
        request_id = message.get("id")
        notification = "id" not in message
        method = message["method"]
        params = message.get("params", {})
        if notification:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "params debe ser un objeto")
        if method == "initialize":
            if self.initialized:
                return self.error(request_id, -32600, "La sesión ya fue inicializada")
            version = params.get("protocolVersion", PROTOCOLS[0])
            self.initialized = True
            result = {"protocolVersion": version if version in PROTOCOLS else PROTOCOLS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "fti-godot-local", "version": "1.0.0"},
                      "instructions": "Puente limitado al proyecto FTI. Las simulaciones son procesos headless independientes; no controla un editor abierto."}
        elif method == "ping":
            result = {}
        elif not self.ready:
            return self.error(request_id, -32002, "Completa initialize y notifications/initialized primero")
        elif method == "tools/list":
            if params.get("cursor"):
                return self.error(request_id, -32602, "Cursor desconocido")
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return self.error(request_id, -32602, "name y arguments no válidos")
            try:
                payload = call_tool(name, arguments, self.godot)
                result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}], "isError": not payload["ok"]}
            except InvalidParams as exc:
                return self.error(request_id, -32602, str(exc))
            except Exception as exc:
                result = {"content": [{"type": "text", "text": json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)}], "isError": True}
        else:
            return self.error(request_id, -32601, "Método no disponible: " + method)
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", help="Ruta del ejecutable de Godot, opcional si GODOT_PATH o autodetección funcionan")
    args = parser.parse_args()
    server = Server(resolve_godot(args.godot))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    while True:
        line = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
        if not line:
            return
        if len(line) > MAX_MESSAGE_BYTES:
            response = server.error(None, -32600, "Mensaje demasiado grande; se cierra la sesión")
            print(json.dumps(response, ensure_ascii=False), flush=True)
            return
        try:
            message = json.loads(line.decode("utf-8"))
            if isinstance(message, list):
                if not message or any(isinstance(item, dict) and item.get("method") == "initialize" for item in message):
                    response = server.error(None, -32600, "Batch vacío o initialize en batch")
                else:
                    replies = [server.handle(item) for item in message]
                    response = [item for item in replies if item is not None] or None
            else:
                response = server.handle(message)
        except (json.JSONDecodeError, UnicodeDecodeError):
            response = server.error(None, -32700, "JSON inválido")
        if response is not None:
            print(json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
