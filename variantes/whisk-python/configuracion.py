"""Recursos de solo lectura y preferencias locales de FTI."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import tempfile

VERSION = "1.0.0"
RESOURCE_DIR = Path(__file__).resolve().parent
DEFAULTS = {
    "scenario": "saturation",
    "strategy": "adaptive",
    "quality": "alta",
    "viewer": True,
    "api": False,
    "api_port": 0,
}


def user_dir():
    configured = os.environ.get("FTI_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    parent = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return parent / "FTI"


def session_dir():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    parent = user_dir() / "logs"
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{stamp}-{os.getpid()}-", dir=parent))


def configure_logging():
    folder = user_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fti")
    if not logger.handlers:
        handler = RotatingFileHandler(folder / "fti.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def validate_settings(settings):
    values = dict(DEFAULTS)
    if not isinstance(settings, dict):
        return values
    choices = {
        "scenario": ("normal", "moderate", "peak_ns", "peak_ew", "saturation"),
        "strategy": ("fti", "adaptive", "fixed", "python"),
        "quality": ("normal", "alta"),
    }
    for key, allowed in choices.items():
        if settings.get(key) in allowed:
            values[key] = settings[key]
    for key in ("viewer", "api"):
        if type(settings.get(key)) is bool:
            values[key] = settings[key]
    port = settings.get("api_port")
    if type(port) is int and 0 <= port <= 65535:
        values["api_port"] = port
    return values


def load_settings():
    try:
        raw = (user_dir() / "preferencias.json").read_text(encoding="utf-8")
        return validate_settings(json.loads(raw))
    except FileNotFoundError:
        return dict(DEFAULTS)
    except (OSError, ValueError):
        logging.getLogger("fti").warning("No se pudieron leer las preferencias", exc_info=True)
        return dict(DEFAULTS)


def save_settings(settings):
    folder = user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(validate_settings(settings), ensure_ascii=False, indent=2) + "\n"
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=folder, suffix=".tmp", encoding="utf-8", delete=False) as stream:
            name = Path(stream.name)
            stream.write(payload)
        name.replace(folder / "preferencias.json")
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def check_resources():
    required = ("flota.json", "whisk3d/whisk3d.exe", "escena/FTI_Cruce_I5.w3d",
                "escena/control.lua", "escena/barrio.obj", "escena/barrio.mtl",
                "escena/vidrio.png", "escena/llanta.png")
    missing = [name for name in required if not (RESOURCE_DIR / name).is_file()]
    if missing:
        raise RuntimeError("Faltan recursos de la aplicación. Extrae la carpeta completa.\n" + "\n".join(missing))
    fleet = json.loads((RESOURCE_DIR / "flota.json").read_text(encoding="utf-8"))
    for model in fleet:
        for extension in ("obj", "mtl"):
            name = f"escena/{model['key']}.{extension}"
            if not (RESOURCE_DIR / name).is_file():
                raise RuntimeError(f"Falta el recurso {name}. Extrae la carpeta completa.")
    return len(fleet)
