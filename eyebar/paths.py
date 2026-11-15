"""Пути к ресурсам и пользовательским данным (работает и в .exe, и из исходников)."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def resource_dir() -> Path:
    """Read-only bundled resource root (locales/, assets/, etc.).

    In a PyInstaller one-file build, _MEIPASS points to the extraction folder,
    NOT to the directory of EyeBar.exe. User data must never be stored here.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Resolve a data file in both source and PyInstaller builds."""
    return resource_dir().joinpath(*parts)


def user_data_dir() -> Path:
    """Папка для config.json."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    d = base / "EyeBar"
    d.mkdir(parents=True, exist_ok=True)
    return d
