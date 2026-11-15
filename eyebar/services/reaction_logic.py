"""Чистая логика погодных реакций маскота (без Qt — легко тестируется).

Дождь:  при начале дождя бросаем кубик ОДИН раз за эпизод:
        60% — кот достаёт зонтик, 40% — мокнет и злится. Реакция держится, пока идёт дождь.
Ветер:  при начале сильного ветра (и не чаще раза в час, пока ветер не стихает)
        95% — кот стоит, шерсть/усы/хвост развеваются, 5% — его сдувает за край экрана.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable

P_UMBRELLA = 0.60
P_BLOW = 0.05
BLOW_COOLDOWN_S = 3600.0

STRONG_WIND_MS = 10.0  # м/с
STRONG_GUST_MS = 15.0  # м/с
RAIN_CODES = frozenset({51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99})
RAIN_MM = 0.3


def is_rain(data: dict) -> bool:
    return int(data.get("code", 0)) in RAIN_CODES or float(data.get("precip", 0.0)) >= RAIN_MM


def is_windy(data: dict) -> bool:
    return float(data.get("wind", 0.0)) >= STRONG_WIND_MS or float(data.get("gust", 0.0)) >= STRONG_GUST_MS


@dataclass
class Result:
    changed: bool = False
    blow: bool = False


class ReactionLogic:
    def __init__(self, rng: random.Random | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.rng = rng or random.Random()
        self.clock = clock
        self.rain_mode = "none"  # "none" | "umbrella" | "wet"
        self.windy = False
        self._last_wind_roll = float("-inf")

    def update(self, data: dict | None) -> Result:
        if not data:
            return Result()
        before = (self.rain_mode, self.windy)
        blow = False

        if is_rain(data):
            if self.rain_mode == "none":
                self.rain_mode = "umbrella" if self.rng.random() < P_UMBRELLA else "wet"
        else:
            self.rain_mode = "none"

        if is_windy(data):
            now = self.clock()
            if not self.windy or now - self._last_wind_roll >= BLOW_COOLDOWN_S:
                self._last_wind_roll = now
                blow = self.rng.random() < P_BLOW
            self.windy = True
        else:
            self.windy = False

        return Result(changed=before != (self.rain_mode, self.windy), blow=blow)

    def simulate(self, kind: str) -> Result:
        """Для проверки пасхалок без ожидания погоды (запуск с --sim-weather=...)."""
        before = (self.rain_mode, self.windy)
        self.rain_mode = kind if kind in ("umbrella", "wet") else "none"
        self.windy = kind in ("wind", "blow")
        return Result(changed=before != (self.rain_mode, self.windy), blow=kind == "blow")
