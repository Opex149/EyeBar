"""Базовый контракт талисмана: любой персонаж реализует Mascot.paint()."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PyQt6.QtGui import QPainter

FORM_MINI = "mini"  # компактная форма для мини-бара
FORM_FULL = "full"  # полная форма для StandBy

LOGICAL_W = 200.0
LOGICAL_H = 160.0

EMOTIONS = ("normal", "happy", "angry", "sleepy", "curious", "surprised", "love", "sad", "dancing")


@dataclass
class MascotState:
    eye_dx: float = 0.0  # -1..1, куда смотрят глаза
    eye_dy: float = 0.0
    blink: float = 1.0  # открытость глаз 0..1
    tail: float = -1.0  # -1..1, фаза виляния хвостом
    tail2: float = 0.0  # то же, но с запаздыванием (для плавного кончика)
    breath: float = 0.0  # -1..1, «дыхание» корпуса
    pulse: float = 0.0  # 0..1, пульс индикатора
    alert: bool = False  # показать "! !" вместо времени
    glow: float = 1.0  # яркость свечения (пульсирует при тревоге)
    hh: str = "00"
    mm: str = "00"
    # --- v3.0: эмоции и погода ---
    emotion: str = "normal"  # один из EMOTIONS
    umbrella: float = 0.0  # 0..1 — насколько раскрыт зонтик
    rain: float = 0.0  # 0..1 — интенсивность капель
    wind: float = 0.0  # 0..1 — сила ветра (усы, шерсть, хвост)
    bob: float = 0.0  # подпрыгивание при радости, логических пикселей
    music_accessory: str = "off"  # off | earbuds | headphones
    temp_text: str = "--°"  # температура для вышивки / шильдика на персонаже
    sleep_phase: float = 0.0  # v1.1: 0..1 smooth head dip, only the cat uses it
    yawn: float = 0.0  # 0..1 mouth opening
    stretch: float = 0.0  # 0..1 paws stretch; no change of mascot size
    t: float = 0.0  # часы анимации, секунды
    outline_color: str = "#38BDF8"  # optional renderer accent override
    backlight: float = 1.0  # 0..1, optional renderer backlight brightness


class Mascot(ABC):
    id: str = ""
    name_key: str = ""  # ключ локализации, например "mascots.cyber_cat"
    desc_key: str = ""  # ключ описания для карточки в настройках

    @abstractmethod
    def paint(self, p: QPainter, form: str, state: MascotState) -> None:
        """Рисует персонажа в логических координатах 200x160.
        Масштабирование под размер виджета уже применено."""
