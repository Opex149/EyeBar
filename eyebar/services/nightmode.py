"""Night-mode schedule and optional, explicitly consented Windows power plan."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

POWER_SAVER = "a1841308-3541-4fab-bc81-f71556f20b4a"
_GUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


from .night_logic import in_night_window


def _powercfg(*args: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Power plans are only available on Windows"
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "powercfg.exe"
        done = subprocess.run([str(executable), *args], capture_output=True, text=True,
                              timeout=6, creationflags=flags, errors="replace", shell=False)
        return done.returncode == 0, (done.stdout + "\n" + done.stderr)
    except (OSError, subprocess.TimeoutExpired):
        return False, "powercfg failed or timed out"


def active_scheme() -> str | None:
    ok, out = _powercfg("/getactivescheme")
    match = _GUID.search(out) if ok else None
    return match.group(0).lower() if match else None


def activate_scheme(guid: str) -> bool:
    if not _GUID.fullmatch(guid):
        return False
    return _powercfg("/setactive", guid)[0]


class NightModeController(QObject):
    changed = pyqtSignal(bool)
    powerError = pyqtSignal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.active = False
        self._power_warning_sent = False
        self._manual: bool | None = None  # resets at next schedule boundary
        self._last_schedule: bool | None = None
        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(30_000)
        self._tick_timer.timeout.connect(self.refresh)

    def start(self) -> None:
        self._tick_timer.start()
        self.refresh()

    def set_manual(self, active: bool) -> None:
        self._manual = bool(active)
        self.refresh()

    def refresh(self) -> None:
        scheduled = bool(self.config.get("night_auto")) and in_night_window(
            datetime.now(), str(self.config.get("night_start")), str(self.config.get("night_end")))
        if self._last_schedule is not None and scheduled != self._last_schedule:
            self._manual = None
        self._last_schedule = scheduled
        expected = scheduled if self._manual is None else self._manual
        if expected != self.active:
            self._power_warning_sent = False
            self.active = expected
            self.changed.emit(expected)
        # Only touch system power plan with a persisted, explicit user opt-in.
        if self.active and self.config.get("night_power_enabled"):
            self._ensure_power_saver()
        else:
            self._restore_power()

    def _ensure_power_saver(self) -> None:
        if os.name != "nt" or self.config.get("night_previous_scheme"):
            return
        current = active_scheme()
        if current is None:
            self._report_error("Не удалось определить текущий план питания Windows.")
            return
        if current == POWER_SAVER:
            return  # user's own setting; do not claim ownership
        # Persist the previous plan BEFORE mutating Windows. Never change it
        # if the config cannot be written (e.g. read-only AppData directory).
        self.config.data["night_previous_scheme"] = current
        if not self.config.save():
            self.config.data["night_previous_scheme"] = ""
            self._report_error("Не удалось сохранить исходный план питания; Windows не изменена.")
            return
        if not activate_scheme(POWER_SAVER):
            self.config.set("night_previous_scheme", "")
            self._report_error("Энергосберегающий план Windows недоступен; настройки Windows не изменены.")

    def _restore_power(self) -> None:
        previous = self.config.get("night_previous_scheme")
        if not previous:
            return
        if os.name != "nt":
            return
        current = active_scheme()
        if current == POWER_SAVER and activate_scheme(previous):
            self.config.set("night_previous_scheme", "")
        elif current is not None and current != POWER_SAVER:
            # User changed the plan manually: leave it alone, release ownership.
            self.config.set("night_previous_scheme", "")
        else:
            self._report_error("Не удалось восстановить прежний план питания; проверь настройки Windows.")

    def _report_error(self, message: str) -> None:
        if not self._power_warning_sent:
            self._power_warning_sent = True
            self.powerError.emit(message)

    def stop(self) -> None:
        self._tick_timer.stop()
        self._restore_power()
