"""Qt-обёртка над ReactionLogic: сигналы для окон."""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from .reaction_logic import ReactionLogic, Result


class WeatherReactions(QObject):
    changed = pyqtSignal(str, bool)  # rain_mode ("none"/"umbrella"/"wet"), windy
    blowAway = pyqtSignal()  # редкая пасхалка: кота сдувает ветром

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.logic = ReactionLogic()

    @property
    def rain_mode(self) -> str:
        return self.logic.rain_mode

    @property
    def windy(self) -> bool:
        return self.logic.windy

    def update(self, data) -> None:
        self._emit(self.logic.update(data))

    def simulate(self, kind: str) -> None:
        self._emit(self.logic.simulate(kind))

    def _emit(self, res: Result) -> None:
        if res.changed:
            self.changed.emit(self.logic.rain_mode, self.logic.windy)
        if res.blow:
            self.blowAway.emit()
