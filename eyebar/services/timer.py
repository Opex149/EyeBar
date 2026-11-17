"""One monotonic countdown, independent of EyeBar's visible window.

``active`` means running; paused/ready countdowns retain their remaining time.
``stop()`` keeps the original API (zero remaining), while ``reset()`` restores
the last chosen duration without starting it. ``resume()`` starts a ready timer
or continues a paused timer, preserving the fractional second at the pause.
"""
from __future__ import annotations

import math
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class CountdownTimer(QObject):
    tick = pyqtSignal(int)  # осталось секунд
    finished = pyqtSignal()
    changed = pyqtSignal()  # duration or running/paused/ready state changed
    stateChanged = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._end = 0.0
        self._remaining = 0.0
        self._last = -1
        self._revision = 0
        self.initial_duration = 0
        self.state = "idle"  # idle | ready | running | paused | finished
        self._t = QTimer(self)
        self._t.setInterval(250)
        self._t.timeout.connect(self._on_timeout)

    @property
    def active(self) -> bool:
        return self.state == "running"

    @property
    def paused(self) -> bool:
        return self.state == "paused"

    def start(self, seconds: int) -> None:
        duration = max(0, int(seconds))
        previous = self.state
        self._revision += 1
        revision = self._revision
        self.initial_duration = duration
        self._remaining = float(duration)
        self._end = time.monotonic() + duration
        self._last = -1
        self.state = "running"
        # This is the same child QTimer, even when replacing a running countdown.
        self._t.start()
        self._notify_state(previous, revision)
        if self._revision == revision:
            self._on_timeout()

    def pause(self) -> None:
        if not self.active:
            return
        remaining = self._end - time.monotonic()
        if remaining <= 0:
            self._finish()
            return
        previous = self.state
        self._revision += 1
        revision = self._revision
        self._remaining = remaining
        self._end = 0.0
        self.state = "paused"
        self._t.stop()
        self._notify_state(previous, revision)
        if self._revision == revision:
            self._emit_tick(self.remaining(), force=True)

    def resume(self) -> None:
        if self.state not in ("paused", "ready"):
            return
        previous = self.state
        self._revision += 1
        revision = self._revision
        self._end = time.monotonic() + self._remaining
        self._last = -1
        self.state = "running"
        self._t.start()
        self._notify_state(previous, revision)
        if self._revision == revision:
            self._on_timeout()

    def reset(self) -> None:
        previous = self.state
        self._revision += 1
        revision = self._revision
        self._t.stop()
        self._end = 0.0
        self._remaining = float(self.initial_duration)
        self.state = "ready" if self.initial_duration else "idle"
        self._notify_state(previous, revision)
        if self._revision == revision:
            self._emit_tick(self.remaining(), force=True)

    def stop(self) -> None:
        previous = self.state
        self._revision += 1
        revision = self._revision
        self._t.stop()
        self._end = self._remaining = 0.0
        self.state = "idle"
        self._notify_state(previous, revision)
        if self._revision == revision:
            self._emit_tick(0, force=True)

    def remaining(self) -> int:
        if self.active:
            value = self._end - time.monotonic()
        elif self.state in ("paused", "ready"):
            value = self._remaining
        else:
            value = 0.0
        # Rounding down/round() would finish up to half a second before the
        # actual deadline. A late GUI tick never changes the elapsed duration.
        return max(0, math.ceil(value))

    def _notify_state(self, previous: str, revision: int) -> None:
        if previous != self.state:
            self.stateChanged.emit(self.state)
        # A signal handler may start/reset/stop this timer. Do not publish a
        # stale second transition after it has already replaced this operation.
        if revision == self._revision:
            self.changed.emit()

    def _emit_tick(self, left: int, *, force: bool = False) -> None:
        if force or left != self._last:
            self._last = left
            self.tick.emit(left)

    def _finish(self) -> None:
        if not self.active:
            return
        previous = self.state
        self._revision += 1
        revision = self._revision
        self._t.stop()
        self._end = self._remaining = 0.0
        self.state = "finished"
        self._notify_state(previous, revision)
        if revision != self._revision:
            return
        self._emit_tick(0)
        if revision == self._revision:
            self.finished.emit()

    def _on_timeout(self) -> None:
        if not self.active:
            return
        left = self.remaining()
        if left <= 0:
            self._finish()
        else:
            self._emit_tick(left)


def format_seconds(total: int) -> str:
    h, rest = divmod(max(0, total), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
