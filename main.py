import sys
import os
import json
import shutil
from pathlib import Path

# Suppress Qt multimedia / FFmpeg verbose output
os.environ["QT_LOGGING_RULES"] = (
    "qt.multimedia.ffmpeg=false;"
    "qt.multimedia.ffmpeg.warning=false;"
    "qt.multimedia.decoder=false"
)
os.environ["AV_LOG_FORCE_NOCOLOR"] = "1"

from PyQt6.QtWidgets import (QApplication, QMessageBox, QInputDialog,
                              QLineEdit, QSplashScreen, QLabel)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QColor


def _load_env(env_path: Path):
    if not env_path.exists():
        example = env_path.parent / ".env.example"
        if example.exists():
            shutil.copy(example, env_path)
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


def _load_config(base_dir: Path) -> dict:
    config_path = base_dir / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _check_ffmpeg() -> bool:
    return (shutil.which("ffmpeg") is not None
            and shutil.which("ffprobe") is not None)


def _ensure_api_key(env_path: Path) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key and key != "your_gemini_api_key_here":
        return key

    key, ok = QInputDialog.getText(
        None,
        "VideoForge — Configuración inicial",
        "Introduce tu clave API de Google AI Studio\n"
        "(obtén una gratis en aistudio.google.com):",
        QLineEdit.EchoMode.Password,
    )
    if ok and key.strip():
        key = key.strip()
        # Persist to .env
        lines = []
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
        new_lines = []
        replaced = False
        for line in lines:
            if line.startswith("GEMINI_API_KEY="):
                new_lines.append(f"GEMINI_API_KEY={key}")
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f"GEMINI_API_KEY={key}")
        env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.environ["GEMINI_API_KEY"] = key
        return key
    return ""


def main():
    base_dir = Path(__file__).parent
    _load_env(base_dir / ".env")

    app = QApplication(sys.argv)
    app.setApplicationName("VideoForge")
    app.setApplicationVersion("1.0.0")
    app.setStyle("Fusion")

    # Apply dark theme
    try:
        from gui.styles import load_styles
        app.setStyleSheet(load_styles())
    except ImportError:
        pass

    # FFmpeg check (warning only — GUI works without it)
    if not _check_ffmpeg():
        QMessageBox.warning(
            None,
            "VideoForge — FFmpeg no encontrado",
            "FFmpeg no está en el PATH del sistema.\n\n"
            "El pipeline de video no funcionará hasta que lo añadas.\n\n"
            "Si acabas de instalarlo, abre una nueva terminal y\n"
            "ejecuta:  python main.py\n\n"
            "La interfaz se abrirá igualmente.",
            QMessageBox.StandardButton.Ok,
        )

    # Gemini API key
    api_key = _ensure_api_key(base_dir / ".env")
    if not api_key:
        QMessageBox.warning(
            None,
            "VideoForge — Sin API Key",
            "No se ha configurado la clave API de Gemini.\n"
            "Las funciones de IA no estarán disponibles.\n\n"
            "Puedes añadirla más tarde en Propiedades → API.",
            QMessageBox.StandardButton.Ok,
        )

    config = _load_config(base_dir)

    # Ensure data dirs exist
    for d in ["data/scripts", "data/projects", "data/temp"]:
        (base_dir / d).mkdir(parents=True, exist_ok=True)

    from gui.main_window import MainWindow
    window = MainWindow(config=config, api_key=api_key, base_dir=str(base_dir))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
