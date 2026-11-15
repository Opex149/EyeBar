"""Byte Fox — компактная лиса с мягкой неоновой графикой."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from ..base import FORM_FULL, Mascot, MascotState
from ..common import WeatherLayout, draw_brows, draw_clock_eye, draw_screen, eye_texts, paint_scene

EDGE = QColor(255, 255, 255, 50)
ORANGE = QColor("#A16207")
RUST = QColor("#5B3413")
DARK = QColor("#22160E")

_FULL_LAYOUT = WeatherLayout(floor=150, canopy_cx=108, canopy_top=3, canopy_by=30, canopy_r=58,
                             pole_bottom=106, paw_y=110, wet_cx=100, wet_cy=58, wet_r=40,
                             fx_x=152, fx_y=42)
_MINI_LAYOUT = WeatherLayout(floor=146, canopy_cx=108, canopy_top=4, canopy_by=39, canopy_r=60,
                             pole_bottom=122, paw_y=124, wet_cx=100, wet_cy=64, wet_r=42,
                             fx_x=154, fx_y=48)


def _grad(top: float, bottom: float):
    g = QLinearGradient(0, top, 0, bottom)
    g.setColorAt(0, ORANGE)
    g.setColorAt(1, RUST)
    return g


class ByteFox(Mascot):
    id = "byte_fox"
    name_key = "mascots.byte_fox"
    desc_key = "mascots.byte_fox.desc"

    def _draw(self, p: QPainter, st: MascotState, full: bool) -> None:
        p.save()
        p.translate(0, st.breath * (1.4 if full else 1.0))
        # curled tail
        tail = QPainterPath(QPointF(132, 116 if full else 121))
        tail.cubicTo(QPointF(171, 126), QPointF(175 + 10 * st.tail, 95), QPointF(142 + 8 * st.tail2, 74))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(EDGE, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(tail)
        p.setPen(QPen(QColor("#6B3E14"), 7.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(tail)
        # body
        body = QPainterPath()
        body.addEllipse(QPointF(100, 108 if full else 114), 37, 31)
        p.setBrush(_grad(76, 142))
        p.setPen(QPen(EDGE, 1.2))
        p.drawPath(body)
        # head and ears
        for sign in (-1, 1):
            ear = QPainterPath(QPointF(100 + sign * 17, 24))
            ear.lineTo(100 + sign * 42, 8)
            ear.lineTo(100 + sign * 31, 39)
            ear.closeSubpath()
            p.drawPath(ear)
        head = QPainterPath()
        head.moveTo(57, 44)
        head.quadTo(61, 18, 100, 18)
        head.quadTo(139, 18, 143, 44)
        head.quadTo(141, 79, 100, 88)
        head.quadTo(59, 79, 57, 44)
        head.closeSubpath()
        p.drawPath(head)
        muzzle = QPainterPath()
        muzzle.moveTo(73, 64)
        muzzle.quadTo(100, 87, 127, 64)
        muzzle.quadTo(118, 83, 100, 84)
        muzzle.quadTo(82, 83, 73, 64)
        muzzle.closeSubpath()
        p.setBrush(QColor(255,255,255,14))
        p.drawPath(muzzle)
        draw_screen(p, QRectF(66, 40, 68, 34), 13)
        left, right = eye_texts(st)
        draw_clock_eye(p, 83, 57, 25, 21, left, st)
        draw_clock_eye(p, 117, 57, 25, 21, right, st)
        draw_brows(p, 83, 117, 57, 25, 21, st)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(240, 240, 244, 210))
        p.drawEllipse(QPointF(100, 74), 3, 2.2)
        for x in (84, 116):
            p.setPen(QPen(EDGE, 1.0))
            p.setBrush(_grad(108, 148))
            p.drawRoundedRect(QRectF(x - 8, 116 if full else 122, 16, 23), 7, 7)
            p.drawEllipse(QPointF(x, 140 if full else 145), 9.5, 5.8)
        p.restore()

    def paint(self, p: QPainter, form: str, st: MascotState) -> None:
        full = form == FORM_FULL
        paint_scene(p, st, _FULL_LAYOUT if full else _MINI_LAYOUT,
                    lambda painter, state: self._draw(painter, state, full))
