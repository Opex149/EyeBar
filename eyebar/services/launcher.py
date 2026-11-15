"""Запуск закреплённых приложений."""
from __future__ import annotations

import os
import subprocess
import sys


def launch(path: str) -> bool:
    """Запускает программу; рабочая папка — папка самого файла (важно для игр)."""
    if not path or not os.path.exists(path):
        return False
    try:
        workdir = os.path.dirname(path) or None
        if sys.platform == "win32":
            os.startfile(path, cwd=workdir)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([path], cwd=workdir)
        return True
    except OSError:
        return False
