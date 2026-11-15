"""Таймер обратного отсчёта."""
from __future__ import annotations

import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class CountdownTimer(QObject):
    tick = pyqtSignal(int)  # осталось секунд
    finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._end = 0.0
        self._last = -1
        self.active = False
        self._t = QTimer(self)
        self._t.setInterval(250)
        self._t.timeout.connect(self._on_timeout)

    def start(self, seconds: int) -> None:
        self._end = time.monotonic() + seconds
        self._last = -1
        self.active = True
        self._t.start()
        self._on_timeout()

    def stop(self) -> None:
        self.active = False
        self._t.stop()
        self.tick.emit(0)

    def remaining(self) -> int:
        if not self.active:
            return 0
        return max(0, int(round(self._end - time.monotonic())))

    def _on_timeout(self) -> None:
        left = self.remaining()
        if left != self._last:
            self._last = left
            self.tick.emit(left)
        if left <= 0 and self.active:
            self.active = False
            self._t.stop()
            self.finished.emit()


def format_seconds(total: int) -> str:
    h, rest = divmod(max(0, total), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
