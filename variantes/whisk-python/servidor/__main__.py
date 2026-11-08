"""Arranque configurable del servicio de recepción de datos."""
import argparse
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", help="Archivo SQLite para el estado y el historial.")
    parser.add_argument("--history", type=int, default=3600, help="Máximo de muestras conservadas.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.history <= 86400:
        parser.error("El puerto debe estar entre 1 y 65535 y el historial entre 1 y 86400.")
    token = os.environ.get("FTI_API_TOKEN", "")
    if len(token) < 24 or not token.isascii():
        parser.error("Configura FTI_API_TOKEN con al menos 24 caracteres ASCII.")
    read_token = os.environ.get("FTI_READ_TOKEN", "")
    if read_token and (len(read_token) < 24 or not read_token.isascii() or read_token == token):
        parser.error("FTI_READ_TOKEN requiere al menos 24 caracteres ASCII y un valor distinto de FTI_API_TOKEN.")
    import uvicorn
    from .app import create_app
    uvicorn.run(create_app(database=args.database, capacity=args.history), host=args.host,
                port=args.port, http="h11", ws="none", proxy_headers=False)


if __name__ == "__main__":
    main()
