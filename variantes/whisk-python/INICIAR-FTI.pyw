"""Abre el lanzador gráfico de FTI con Python para Windows."""


if __name__ == "__main__":
    try:
        from launcher import main

        main()
    except Exception as error:
        import os
        from pathlib import Path
        import traceback

        details = traceback.format_exc()
        try:
            base = Path(os.environ.get("FTI_DATA_DIR") or
                        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "FTI")
            folder = base / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            report = folder / "arranque-error.log"
            report.write_text(details, encoding="utf-8")
            message = f"No se pudo abrir FTI.\n{error}\n\nDetalle del error en\n{report}"
        except OSError:
            message = f"No se pudo abrir FTI.\n{error}\n\nNo se pudo escribir el registro de diagnóstico."
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "FTI · Error de arranque", 0x10)
        except Exception:
            pass
        raise SystemExit(1)
