"""Тонкие плоские векторные иконки, нарисованные через QPainter (никаких эмодзи и шрифтов).

Все иконки рисуются на сетке 24x24 и масштабируются под нужный размер.
Использование:
    pixmap("play", size=20)          -> QPixmap
    icon("gear", size=18)            -> QIcon (для QPushButton.setIcon)
"""
from __future__ import annotations

import math
from typing import Callable

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
    QTransform,
)

ICON = "#E4E4E7"    # тёплый светлый
ACCENT = "#38BDF8"  # индикатор активности
ALERT = "#FBBF24"   # мягкий янтарь для сигнала

Brushes = tuple[QBrush, QBrush]  # (сплошная заливка, мягкая заливка)


def _pen(color: QColor, width: float) -> QPen:
    return QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _line(p: QPainter, x1: float, y1: float, x2: float, y2: float) -> None:
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _tri(p: QPainter, pts: list[tuple[float, float]]) -> None:
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))


def _bar(p: QPainter, x: float, y: float, w: float, h: float) -> None:
    p.drawRoundedRect(QRectF(x, y, w, h), 1.0, 1.0)


# ---------------- медиа ----------------
def _play(p, b):
    p.setBrush(b[0])
    _tri(p, [(8, 5), (8, 19), (19, 12)])


def _playpause(p, b):
    p.setBrush(b[0])
    _tri(p, [(3, 5), (3, 19), (13, 12)])
    _bar(p, 15, 5, 2.6, 14)
    _bar(p, 18.8, 5, 2.6, 14)


def _next(p, b):
    p.setBrush(b[0])
    _tri(p, [(5, 5), (5, 19), (15, 12)])
    _bar(p, 17, 5, 2.6, 14)


def _prev(p, b):
    p.setBrush(b[0])
    _tri(p, [(19, 5), (19, 19), (9, 12)])
    _bar(p, 4.4, 5, 2.6, 14)


# ---------------- интерфейс ----------------
def _timer(p, b):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(12, 13.5), 7.5, 7.5)
    _line(p, 9.5, 3.5, 14.5, 3.5)
    _line(p, 12, 13.5, 12, 9.5)
    _line(p, 17.6, 6.4, 19.2, 4.8)


def _gear(p, b):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(12, 12), 5.6, 5.6)
    p.drawEllipse(QPointF(12, 12), 2.1, 2.1)
    for i in range(8):
        a = math.radians(i * 45)
        _line(p, 12 + 7.4 * math.cos(a), 12 + 7.4 * math.sin(a),
              12 + 10 * math.cos(a), 12 + 10 * math.sin(a))


def _moon(p, b):
    disc = QPainterPath()
    disc.addEllipse(QPointF(12, 12), 8, 8)
    cut = QPainterPath()
    cut.addEllipse(QPointF(16.6, 8.4), 7, 7)
    p.setBrush(b[1])
    p.drawPath(disc.subtracted(cut))


def _close(p, b):
    _line(p, 6.5, 6.5, 17.5, 17.5)
    _line(p, 17.5, 6.5, 6.5, 17.5)


def _notes(p, b):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(5, 3.5, 14, 17), 2.5, 2.5)
    _line(p, 8.5, 9, 15.5, 9)
    _line(p, 8.5, 12.5, 15.5, 12.5)
    _line(p, 8.5, 16, 12.5, 16)


def _apps(p, b):
    p.setBrush(b[1])
    for x, y in ((4.5, 4.5), (13.5, 4.5), (4.5, 13.5), (13.5, 13.5)):
        p.drawRoundedRect(QRectF(x, y, 6, 6), 1.6, 1.6)


def _bell(p, b):
    path = QPainterPath(QPointF(5.5, 17.5))
    path.cubicTo(7.5, 16, 7.5, 13, 7.5, 11)
    path.cubicTo(7.5, 7.5, 9.5, 5.5, 12, 5.5)
    path.cubicTo(14.5, 5.5, 16.5, 7.5, 16.5, 11)
    path.cubicTo(16.5, 13, 16.5, 16, 18.5, 17.5)
    path.closeSubpath()
    p.setBrush(b[1])
    p.drawPath(path)
    _line(p, 10, 20.5, 14, 20.5)
    _line(p, 12, 3.5, 12, 5)


# ---------------- погода ----------------
def _sun_at(p: QPainter, cx: float, cy: float, r: float, ray_in: float, ray_out: float,
            angles: range | list[int], soft: QBrush) -> None:
    p.setBrush(soft)
    p.drawEllipse(QPointF(cx, cy), r, r)
    for deg in angles:
        a = math.radians(deg)
        _line(p, cx + ray_in * math.cos(a), cy + ray_in * math.sin(a),
              cx + ray_out * math.cos(a), cy + ray_out * math.sin(a))


def _cloud_path(dx: float = 0, dy: float = 0, s: float = 1.0) -> QPainterPath:
    path = QPainterPath()
    path.addEllipse(QPointF(8, 14.5), 3.8, 3.8)
    path.addEllipse(QPointF(12.8, 11.5), 4.8, 4.8)
    path.addEllipse(QPointF(17.2, 14.8), 3.4, 3.4)
    path.addRoundedRect(QRectF(8, 14.5, 9.2, 3.8), 1.9, 1.9)
    t = QTransform()
    t.translate(dx, dy)
    t.scale(s, s)
    return t.map(path.simplified())


def _sun(p, b):
    _sun_at(p, 12, 12, 4.3, 7.0, 9.8, range(0, 360, 45), b[1])


def _cloud(p, b):
    p.setBrush(b[1])
    p.drawPath(_cloud_path())


def _partly(p, b):
    _sun_at(p, 8.5, 8.5, 2.9, 4.8, 6.4, [135, 180, 225, 270, 315], b[1])
    p.setBrush(b[1])
    p.drawPath(_cloud_path(3.2, 2.8, 0.82))


def _rain(p, b):
    p.setBrush(b[1])
    p.drawPath(_cloud_path(0, -3.2, 0.9))
    for x in (8.5, 12.5, 16.5):
        _line(p, x, 18.2, x - 1.3, 21.4)


def _snow(p, b):
    p.setBrush(b[1])
    p.drawPath(_cloud_path(0, -3.2, 0.9))
    p.setBrush(b[0])
    for x, y in ((8.5, 19.6), (12.5, 21.2), (16.5, 19.6)):
        p.drawEllipse(QPointF(x, y), 0.9, 0.9)


def _fog(p, b):
    _line(p, 4, 8.5, 20, 8.5)
    _line(p, 6.5, 12.5, 18.5, 12.5)
    _line(p, 4, 16.5, 15, 16.5)


def _thunder(p, b):
    p.setBrush(b[1])
    p.drawPath(_cloud_path(0, -4.6, 0.88))
    p.setBrush(b[0])
    _tri(p, [(13.2, 12.2), (9.8, 17.8), (12.3, 17.8), (11, 22)])


def _pause(p, b):
    p.setBrush(b[0])
    _bar(p, 6.5, 5, 3.6, 14)
    _bar(p, 13.9, 5, 3.6, 14)


def _collapse(p, b):  # стрелки внутрь: свернуть в кубик
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(13, 5), QPointF(13, 11), QPointF(19, 11)]))
    p.drawPolyline(QPolygonF([QPointF(11, 19), QPointF(11, 13), QPointF(5, 13)]))
    _line(p, 13, 11, 19.5, 4.5)
    _line(p, 11, 13, 4.5, 19.5)


def _expand(p, b):  # стрелки наружу: развернуть
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(14, 5), QPointF(19, 5), QPointF(19, 10)]))
    p.drawPolyline(QPolygonF([QPointF(10, 19), QPointF(5, 19), QPointF(5, 14)]))
    _line(p, 19, 5, 13.5, 10.5)
    _line(p, 5, 19, 10.5, 13.5)


def _note(p, b):
    p.setBrush(b[0])
    p.drawEllipse(QPointF(8.5, 17.5), 3.2, 2.6)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _line(p, 11.4, 17, 11.4, 5.5)
    path = QPainterPath(QPointF(11.4, 5.5))
    path.quadTo(QPointF(17.5, 6.5), QPointF(17, 11.5))
    p.drawPath(path)



def _camera(p, b):
    # Compact camera silhouette, recognisable at 18px.
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(3, 7, 18, 13), 2.2, 2.2)
    p.drawEllipse(QPointF(12, 13.5), 4, 4)
    p.setBrush(b[0])
    p.drawRoundedRect(QRectF(7, 4.5, 6, 3.5), 0.8, 0.8)
    p.drawEllipse(QPointF(18, 10), 0.8, 0.8)


def _more(p, b):
    p.setBrush(b[0])
    for x in (5.5, 12, 18.5):
        p.drawEllipse(QPointF(x, 12), 1.65, 1.65)


SHAPES: dict[str, Callable] = {
    "play": _play, "playpause": _playpause, "next": _next, "prev": _prev,
    "timer": _timer, "gear": _gear, "moon": _moon, "close": _close, "notes": _notes,
    "apps": _apps, "bell": _bell, "pause": _pause, "collapse": _collapse,
    "expand": _expand, "note": _note, "camera": _camera, "more": _more,
    "sun": _sun, "cloud": _cloud, "partly": _partly, "rain": _rain, "snow": _snow,
    "fog": _fog, "thunder": _thunder,
}

_cache: dict[tuple, QPixmap] = {}


def _alpha(color: str, a: int) -> QColor:
    c = QColor(color)
    c.setAlpha(a)
    return c


def _render(p: QPainter, name: str, color: str, glow: bool) -> None:
    shape = SHAPES.get(name, _cloud)
    if glow:  # мягкое неоновое свечение под основным рисунком
        p.setPen(_pen(_alpha(color, 46), 4.8))
        shape(p, (QBrush(_alpha(color, 40)), QBrush(_alpha(color, 20))))
    p.setPen(_pen(QColor(color), 1.7))
    shape(p, (QBrush(QColor(color)), QBrush(_alpha(color, 60))))


def pixmap(name: str, size: int = 20, color: str = ICON, glow: bool = False) -> QPixmap:
    key = (name, size, color, glow)
    if key in _cache:
        return _cache[key]
    screen = QGuiApplication.primaryScreen()
    dpr = max(2.0, screen.devicePixelRatio() if screen else 2.0)
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    _render(p, name, color, glow)
    p.end()
    _cache[key] = pm
    return pm


def icon(name: str, size: int = 20, color: str = ICON, glow: bool = False) -> QIcon:
    return QIcon(pixmap(name, size, color, glow))
