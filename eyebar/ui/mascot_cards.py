"""Карточки выбора персонажа с живым предпросмотром (для окна настроек)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from ..mascots.base import FORM_FULL
from .widgets import mascot_preview


class MascotCard(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, ctx, mascot) -> None:
        super().__init__()
        self.ctx = ctx
        self.mascot = mascot
        self.setObjectName("mascotCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(190)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(6)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setPixmap(mascot_preview(mascot, FORM_FULL, 150, 120))
        self.name = QLabel()
        self.name.setObjectName("mascotName")
        self.desc = QLabel()
        self.desc.setObjectName("muted")
        self.desc.setWordWrap(True)
        lay.addWidget(self.preview)
        lay.addWidget(self.name)
        lay.addWidget(self.desc, 1)
        self.retranslate()

    def retranslate(self) -> None:
        t = self.ctx.i18n.t
        self.name.setText(t(self.mascot.name_key))
        self.desc.setText(t(self.mascot.desc_key) if self.mascot.desc_key else "")

    def set_selected(self, on: bool) -> None:
        self.setProperty("selected", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.mascot.id)


class MascotPicker(QWidget):
    """Сетка карточек. Новые персонажи появляются сами — по реестру mascots/."""

    selected = pyqtSignal(str)

    def __init__(self, ctx, current: str) -> None:
        super().__init__()
        self.cards: dict[str, MascotCard] = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        for i, (mid, mascot) in enumerate(ctx.mascots.items()):
            card = MascotCard(ctx, mascot)
            card.clicked.connect(self.selected.emit)
            self.cards[mid] = card
            grid.addWidget(card, i // 2, i % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.set_current(current)

    def set_current(self, mascot_id: str) -> None:
        for mid, card in self.cards.items():
            card.set_selected(mid == mascot_id)

    def retranslate(self) -> None:
        for card in self.cards.values():
            card.retranslate()
