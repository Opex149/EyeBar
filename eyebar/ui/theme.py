"""Минималистичная тёмная тема: матовый графит, тёплый белый, тонкие рамки."""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

BG = "#0A0A0C"
SURFACE = "#121215"
TEXT = "#F4F4F5"
TEXT_SOFT = "#E4E4E7"
MUTED = "#A1A1AA"
ACCENT = "#38BDF8"  # только для мелких индикаторов активности

STYLE = """
* { font-family: "Segoe UI Variable Text", "Segoe UI", "Noto Sans", sans-serif; font-size: 13px; }
QLabel { color: #F4F4F5; background: transparent; }
QLabel#muted { color: #A1A1AA; }
QLabel#cardTitle { color: #A1A1AA; font-size: 12px; }
QLabel#big { font-size: 26px; font-weight: 500; color: #F4F4F5; }
QLabel#hint { color: #71717A; }
QLabel#section { color: #A1A1AA; font-size: 12px; font-weight: 600; padding-top: 8px; }
QLabel#mascotName { font-size: 14px; font-weight: 600; }
QLabel#trackTitle { font-size: 13px; font-weight: 600; color: #F4F4F5; }
QLabel#mid { font-size: 17px; font-weight: 500; color: #F4F4F5; }

QDialog { background: #121215; color: #F4F4F5; }
QMenu { background: #17171A; color: #F4F4F5; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 18px; border-radius: 6px; }
QMenu::item:selected { background: rgba(255,255,255,0.08); }
QMenu::separator { height: 1px; background: rgba(255,255,255,0.08); margin: 4px 8px; }
QToolTip { background: #17171A; color: #F4F4F5; border: 1px solid rgba(255,255,255,0.08);
  padding: 4px 8px; }

QPushButton { background: rgba(255,255,255,0.05); border: none; border-radius: 10px;
  color: #F4F4F5; padding: 7px 14px; }
QPushButton:hover { background: rgba(255,255,255,0.10); }
QPushButton:pressed { background: rgba(255,255,255,0.16); }
QPushButton#icon { background: transparent; padding: 0; min-width: 30px; max-width: 30px;
  min-height: 30px; max-height: 30px; border-radius: 15px; }
QPushButton#icon:hover { background: rgba(255,255,255,0.10); }
QPushButton#icon:pressed { background: rgba(255,255,255,0.16); }
QPushButton#iconMid { background: rgba(255,255,255,0.07); padding: 0; min-width: 40px; max-width: 40px;
  min-height: 40px; max-height: 40px; border-radius: 20px; }
QPushButton#iconMid:hover { background: rgba(255,255,255,0.14); }
QPushButton#iconMid:pressed { background: rgba(255,255,255,0.20); }
QPushButton#chip { padding: 7px 12px; text-align: left; }
QPushButton#chip:checked { background: rgba(255,255,255,0.16); border: 1px solid rgba(228,228,231,0.45); }
QPushButton#iconBig { min-width: 56px; max-width: 56px; min-height: 56px; max-height: 56px;
  border-radius: 28px; padding: 0; }

QFrame#card { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 20px; }
QFrame#card QPlainTextEdit { background: transparent; border: none; padding: 0; }
QFrame#mascotCard { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 16px; }
QFrame#mascotCard:hover { background: rgba(255,255,255,0.06); }
QFrame#mascotCard[selected="true"] { background: rgba(255,255,255,0.08);
  border: 1px solid rgba(228,228,231,0.55); }

QPlainTextEdit, QLineEdit, QSpinBox, QComboBox, QKeySequenceEdit {
  background: rgba(255,255,255,0.04); color: #F4F4F5; border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; padding: 5px 8px; selection-background-color: #3F3F46; }
QComboBox QAbstractItemView { background: #17171A; color: #F4F4F5; border: none; }
QCheckBox { color: #F4F4F5; spacing: 8px; }

QSlider::groove:horizontal { height: 4px; background: rgba(255,255,255,0.10); border-radius: 2px; }
QSlider::sub-page:horizontal { background: #E4E4E7; border-radius: 2px; }
QSlider::handle:horizontal { background: #F4F4F5; width: 16px; margin: -6px 0; border-radius: 8px; }

QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { width: 8px; background: transparent; margin: 2px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.18); border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(SURFACE))
    p.setPen(QPen(QColor(255, 255, 255, 70), 2))
    p.drawEllipse(QRectF(3, 3, 58, 58))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(TEXT))
    for x in (14, 37):
        p.drawRoundedRect(QRectF(x, 22, 13, 20), 5, 5)
    p.end()
    return QIcon(pm)
