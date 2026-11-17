"""Общие детали для всех талисманов: экран-мордочка, часо-глаза, эмоции и погодные эффекты."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)

from .base import MascotState

WARM_WHITE = QColor("#F4F4F5")
ALERT = QColor("#FBBF24")  # мягкий янтарь вместо красного
RAIN_BLUE = QColor(186, 230, 253)

# насколько глаз может быть открыт при данной эмоции
EMOTION_EYE_CAP = {"normal": 1.0, "happy": 0.82, "angry": 0.72, "sleepy": 0.38,
                   "curious": 1.0, "surprised": 1.0, "love": 0.88, "sad": 0.56, "dancing": 0.8}


def _pen(color: QColor, width: float) -> QPen:
    return QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def ease(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def eye_texts(st: MascotState) -> tuple[str, str]:
    """Что показывать в левом и правом глазу: время или '!' при тревоге."""
    return ("!", "!") if st.alert else (st.hh, st.mm)


# ---------------------------------------------------------------- экран и глаза
def draw_screen(p: QPainter, rect: QRectF, radius: float = 16.0) -> None:
    """Тёмный экран мордочки: плавная виньетка, тонкая рамка и лёгкий блик сверху."""
    p.setPen(Qt.PenStyle.NoPen)
    vignette = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.62)
    vignette.setColorAt(0.0, QColor("#141417"))
    vignette.setColorAt(1.0, QColor("#050506"))
    p.setBrush(vignette)
    p.drawRoundedRect(rect, radius, radius)

    shine = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.center().y()))
    shine.setColorAt(0.0, QColor(255, 255, 255, 16))
    shine.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(shine)
    p.drawRoundedRect(rect.adjusted(1, 1, -1, 0), radius, radius)

    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 26), 1.0))
    p.drawRoundedRect(rect, radius, radius)


def draw_clock_eye(p: QPainter, cx: float, cy: float, w: float, h: float,
                   text: str, st: MascotState) -> None:
    """Глаз = мягкое свечение + чёткие цифры, без обводки.
    Цифры смещаются за курсором, при моргании и эмоциях глаз сплющивается по вертикали."""
    color = ALERT if st.alert else WARM_WHITE
    cap = 1.0 if st.alert else EMOTION_EYE_CAP.get(st.emotion, 1.0)
    openness = max(0.05, min(st.blink, cap))

    p.save()
    if not st.alert:
        p.setOpacity(p.opacity() * max(0.1, min(1.0, st.backlight)))
    p.translate(cx, cy)
    p.scale(1.0, openness)

    glow = QRadialGradient(QPointF(0, 0), w * 0.62)
    c1, c2 = QColor(color), QColor(color)
    c1.setAlpha(int(46 * st.glow))
    c2.setAlpha(0)
    glow.setColorAt(0.0, c1)
    glow.setColorAt(1.0, c2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(0, 0), w * 0.62, h * 0.78)

    if openness > 0.3:
        font = QFont("Consolas")
        font.setPixelSize(int(h * 0.80))
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        box = QRectF(-w / 2 + st.eye_dx * 3.0, -h / 2 + st.eye_dy * 2.5, w, h)
        halo = QColor(color)
        halo.setAlpha(int(34 * st.glow))
        p.setPen(halo)  # мягкое свечение цифр: несколько сдвинутых копий
        for ox, oy in ((-1.3, 0), (1.3, 0), (0, -1.3), (0, 1.3)):
            p.drawText(box.translated(ox, oy), Qt.AlignmentFlag.AlignCenter, text)
        p.setPen(color)
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
    p.restore()


def draw_brows(p: QPainter, lx: float, rx: float, ey: float, w: float, h: float,
               st: MascotState) -> None:
    """Нахмуренные брови над глазами (только при злости)."""
    if st.emotion != "angry" or st.alert:
        return
    p.setPen(_pen(QColor(244, 244, 245, 235), 2.4))
    top = ey - h / 2
    p.drawLine(QPointF(lx - w / 2 - 1, top - 5), QPointF(lx + w / 2 - 2, top + 1))
    p.drawLine(QPointF(rx + w / 2 + 1, top - 5), QPointF(rx - w / 2 + 2, top + 1))


# ---------------------------------------------------------------- эмоции
def _draw_notes(p: QPainter, x: float, y: float, st: MascotState) -> None:
    for i in range(2):
        ph = (st.t * 0.55 + i * 0.5) % 1.0
        nx = x + i * 12 + math.sin(ph * 6.0 + i) * 4
        ny = y - ph * 30
        col = QColor(WARM_WHITE)
        col.setAlpha(int(220 * math.sin(math.pi * ph)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.save()
        p.translate(nx, ny)
        p.rotate(-20)
        p.drawEllipse(QPointF(0, 0), 3.2, 2.3)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(col, 1.4))
        p.drawLine(QPointF(nx + 2.6, ny - 0.8), QPointF(nx + 2.6, ny - 11))
        flag = QPainterPath(QPointF(nx + 2.6, ny - 11))
        flag.quadTo(nx + 7, ny - 9, nx + 6, ny - 5)
        p.drawPath(flag)


def _draw_zzz(p: QPainter, x: float, y: float, st: MascotState) -> None:
    font = QFont("Segoe UI")
    font.setBold(True)
    font.setItalic(True)
    for i in range(3):
        ph = (st.t * 0.4 + i / 3.0) % 1.0
        font.setPixelSize(int(8 + 7 * ph))
        p.setFont(font)
        col = QColor(WARM_WHITE)
        col.setAlpha(int(200 * math.sin(math.pi * ph)))
        p.setPen(col)
        p.drawText(QPointF(x + ph * 16, y - ph * 26), "z")


def draw_emotion_fx(p: QPainter, st: MascotState, x: float, y: float) -> None:
    """Ноты при радости, «z-z-z» при сонливости."""
    if st.alert:
        return
    if st.emotion in ("happy", "dancing"):
        _draw_notes(p, x, y, st)
    elif st.emotion == "sleepy":
        _draw_zzz(p, x, y, st)
    elif st.emotion in ("love", "surprised", "curious", "sad"):
        p.save()
        p.setFont(QFont("Segoe UI Symbol", 17, QFont.Weight.Bold))
        p.setPen(QColor("#FBCFE8") if st.emotion == "love" else WARM_WHITE)
        glyph = {"love": "♥", "surprised": "!", "curious": "?", "sad": "·"}[st.emotion]
        p.drawText(QPointF(x + math.sin(st.t * 2) * 3, y - 8), glyph)
        p.restore()


# ---------------------------------------------------------------- погода
def draw_wind_streaks(p: QPainter, st: MascotState) -> None:
    if st.wind < 0.05:
        return
    for i in range(4):
        y = 24 + i * 34 + 6 * math.sin(i * 2.1)
        ph = (st.t * 0.9 + i * 0.37) % 1.0
        x0 = -40 + ph * 280
        col = QColor(WARM_WHITE)
        col.setAlpha(int(90 * st.wind * math.sin(math.pi * ph)))
        path = QPainterPath(QPointF(x0, y))
        path.quadTo(QPointF(x0 + 18, y - 3.5), QPointF(x0 + 36, y))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(col, 1.2))
        p.drawPath(path)


def draw_rain(p: QPainter, st: MascotState, dry: QRectF | None) -> None:
    """Падающие капли; `dry` — зона под зонтом, где капель нет."""
    if st.rain < 0.02:
        return
    col = QColor(RAIN_BLUE)
    col.setAlpha(int(150 * min(1.0, st.rain)))
    p.setPen(_pen(col, 1.2))
    for i in range(int(26 * st.rain)):
        x = (i * 47.3 + 11.0) % 200.0
        speed = 170.0 + (i % 5) * 25.0
        y = ((st.t * speed + i * 37.1) % 185.0) - 15.0
        if dry is not None and dry.contains(x, y):
            continue
        p.drawLine(QPointF(x, y), QPointF(x - 1.8, y + 7))


def draw_wet_drops(p: QPainter, st: MascotState, cx: float, cy: float, r: float) -> None:
    """Капли, стекающие по голове (когда кот мокнет без зонта)."""
    if st.rain < 0.3 or st.umbrella > 0.3:
        return
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(4):
        ph = (st.t * 0.3 + i * 0.26) % 1.0
        x = cx + (i - 1.5) * r * 0.42
        y = cy - r * 0.85 + ph * r * 1.25
        col = QColor(RAIN_BLUE)
        col.setAlpha(int(190 * math.sin(math.pi * ph) * min(1.0, st.rain)))
        drop = QPainterPath(QPointF(x, y - 4))
        drop.quadTo(x + 3.2, y + 1, x, y + 3.6)
        drop.quadTo(x - 3.2, y + 1, x, y - 4)
        p.setBrush(col)
        p.drawPath(drop)


def draw_umbrella_pole(p: QPainter, st: MascotState, x: float, top: float, bottom: float) -> None:
    u = ease(st.umbrella)
    if u < 0.02:
        return
    col = QColor("#8B8B94")
    col.setAlpha(int(255 * min(1.0, u * 2)))
    p.setPen(_pen(col, 2.4))
    p.drawLine(QPointF(x, top + (1 - u) * 20), QPointF(x, bottom))


def draw_umbrella_canopy(p: QPainter, st: MascotState, cx: float, top: float, by: float, r: float) -> None:
    """Минималистичный зонтик; раскрывается плавно вместе с st.umbrella."""
    u = ease(st.umbrella)
    if u < 0.02:
        return
    w = r * u
    rise = (1 - u) * 22
    t, b = top + rise, by + rise * 0.6
    path = QPainterPath(QPointF(cx - w, b))
    path.quadTo(QPointF(cx - w * 0.98, t), QPointF(cx, t))
    path.quadTo(QPointF(cx + w * 0.98, t), QPointF(cx + w, b))
    seg = 2 * w / 3
    for i in range(3):
        x0 = cx + w - seg * i
        x1 = x0 - seg
        path.quadTo(QPointF((x0 + x1) / 2, b + 7 * u), QPointF(x1, b))
    path.closeSubpath()

    grad = QLinearGradient(0, t, 0, b)
    grad.setColorAt(0, QColor("#52525B"))
    grad.setColorAt(1, QColor("#2B2B31"))
    p.save()
    p.setOpacity(min(1.0, u * 2))
    p.setBrush(grad)
    p.setPen(QPen(QColor(228, 228, 231, 110), 1.2))
    p.drawPath(path)
    p.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
    for jx in (cx - w + seg, cx + w - seg):
        p.drawLine(QPointF(cx, t), QPointF(jx, b))
    p.setPen(_pen(QColor(228, 228, 231, 150), 1.6))
    p.drawLine(QPointF(cx, t), QPointF(cx, t - 3))
    p.restore()


def draw_paw(p: QPainter, st: MascotState, x: float, y: float, fill: QColor) -> None:
    """Лапка, которой персонаж держит зонт."""
    u = ease(st.umbrella)
    if u < 0.3:
        return
    p.save()
    p.setOpacity(min(1.0, (u - 0.3) * 2))
    p.setBrush(fill)
    p.setPen(QPen(QColor(255, 255, 255, 46), 1.2))
    p.drawEllipse(QPointF(x, y), 8.0, 6.5)
    p.restore()


@dataclass(frozen=True)
class WeatherLayout:
    """Опорные точки персонажа для погодных эффектов (логические координаты 200x160)."""
    floor: float  # линия «пола»: относительно неё персонаж уменьшается под зонтом
    canopy_cx: float
    canopy_top: float
    canopy_by: float
    canopy_r: float
    pole_bottom: float
    paw_y: float
    wet_cx: float
    wet_cy: float
    wet_r: float
    fx_x: float  # где появляются ноты / «z»
    fx_y: float
    paw_fill: QColor = field(default_factory=lambda: QColor("#2A2A30"))


def paint_scene(p: QPainter, st: MascotState, lay: WeatherLayout,
                body_fn: Callable[[QPainter, MascotState], None]) -> None:
    """Единый порядок слоёв для любого персонажа:
    порывы ветра → ручка зонта → персонаж → лапка → купол → ноты/«z» → дождь → капли."""
    draw_wind_streaks(p, st)
    draw_umbrella_pole(p, st, lay.canopy_cx, lay.canopy_by, lay.pole_bottom)

    k = 1.0 - 0.2 * ease(st.umbrella)  # под зонтом персонаж чуть уменьшается
    p.save()
    p.translate(0, -st.bob)
    p.translate(100, lay.floor)
    p.scale(k, k)
    p.translate(-100, -lay.floor)
    body_fn(p, st)
    p.restore()

    # Music mode: deterministic accessory per playback session, 50/50 when random.
    if st.music_accessory in ("earbuds", "headphones"):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if st.music_accessory == "headphones":
            p.setPen(_pen(QColor("#94A3B8"), 4.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(38, 9 if lay.floor > 149 else 35, 124, 102), 0, 180 * 16)
            p.setPen(_pen(QColor("#38BDF8"), 7))
            for x in (41, 159):
                p.drawLine(QPointF(x, 61 if lay.floor > 149 else 80), QPointF(x, 79 if lay.floor > 149 else 99))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#E2E8F0"))
            for x in (48, 152):
                y = 65 if lay.floor > 149 else 90
                p.drawEllipse(QPointF(x, y), 4, 6)
                p.drawRoundedRect(QRectF(x - 1.5, y + 2, 3, 14), 1.5, 1.5)
        p.restore()

    draw_paw(p, st, lay.canopy_cx, lay.paw_y, lay.paw_fill)
    draw_umbrella_canopy(p, st, lay.canopy_cx, lay.canopy_top, lay.canopy_by, lay.canopy_r)
    draw_emotion_fx(p, st, lay.fx_x, lay.fx_y)
    dry = None
    if st.umbrella > 0.7:
        dry = QRectF(lay.canopy_cx - lay.canopy_r + 4, 0, 2 * (lay.canopy_r - 4), 160)
    draw_rain(p, st, dry)
    draw_wet_drops(p, st, lay.wet_cx, lay.wet_cy, lay.wet_r)
