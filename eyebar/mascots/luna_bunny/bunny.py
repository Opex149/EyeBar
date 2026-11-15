"""Лунный кролик — спокойный новый персонаж для EyeBar."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from ..base import FORM_FULL, Mascot, MascotState
from ..common import WeatherLayout, draw_brows, draw_clock_eye, draw_screen, eye_texts, paint_scene

EDGE = QColor(255, 255, 255, 46)
_BODY_A = QColor("#5A5A69")
_BODY_B = QColor("#242430")

_FULL_LAYOUT = WeatherLayout(floor=150, canopy_cx=108, canopy_top=3, canopy_by=30, canopy_r=58,
                             pole_bottom=108, paw_y=112, wet_cx=100, wet_cy=56, wet_r=40,
                             fx_x=152, fx_y=42)
_MINI_LAYOUT = WeatherLayout(floor=146, canopy_cx=108, canopy_top=4, canopy_by=39, canopy_r=60,
                             pole_bottom=124, paw_y=126, wet_cx=100, wet_cy=62, wet_r=42,
                             fx_x=154, fx_y=48)


def _grad(top: float, bottom: float):
    g = QLinearGradient(0, top, 0, bottom)
    g.setColorAt(0, _BODY_A)
    g.setColorAt(1, _BODY_B)
    return g


class LunaBunny(Mascot):
    id = "luna_bunny"
    name_key = "mascots.luna_bunny"
    desc_key = "mascots.luna_bunny.desc"

    def _draw(self, p: QPainter, st: MascotState, full: bool) -> None:
        p.save()
        p.translate(0, st.breath * (1.6 if full else 1.0))
        # ears
        for sign in (-1, 1):
            ear = QPainterPath()
            ear.addRoundedRect(QRectF(100 + sign * 18 - 8, 8, 16, 58), 8, 8)
            p.setPen(QPen(EDGE, 1.2))
            p.setBrush(_grad(8, 66))
            p.drawPath(ear)
            p.setBrush(QColor(255, 255, 255, 14))
            p.drawRoundedRect(QRectF(100 + sign * 18 - 4, 14, 8, 43), 4, 4)
        body = QPainterPath()
        body.addEllipse(QPointF(100, 106 if full else 112), 38, 34 if full else 31)
        p.setBrush(_grad(70, 144))
        p.setPen(QPen(EDGE, 1.2))
        p.drawPath(body)
        head = QPainterPath()
        head.addEllipse(QPointF(100, 58 if full else 62), 46, 39)
        p.drawPath(head)
        draw_screen(p, QRectF(62, 42 if full else 46, 76, 42), 15)
        left, right = eye_texts(st)
        draw_clock_eye(p, 81, 63 if full else 67, 28, 23, left, st)
        draw_clock_eye(p, 119, 63 if full else 67, 28, 23, right, st)
        draw_brows(p, 81, 119, 63 if full else 67, 28, 23, st)
        # nose
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(235, 235, 239, 210))
        p.drawEllipse(QPointF(100, 83 if full else 87), 3.5, 2.5)
        # paws
        for x in (84, 116):
            p.setPen(QPen(EDGE, 1.0))
            p.setBrush(_grad(105, 148))
            p.drawRoundedRect(QRectF(x - 8, 116 if full else 122, 16, 24), 7, 7)
            p.drawEllipse(QPointF(x, 141 if full else 145), 9.8, 6.0)
        # tail puff
        p.setPen(QPen(QColor(255,255,255,18), 1.0))
        p.setBrush(_grad(94, 144))
        p.drawEllipse(QPointF(136, 122 if full else 128), 10, 10)
        p.restore()

    def paint(self, p: QPainter, form: str, st: MascotState) -> None:
        full = form == FORM_FULL
        paint_scene(p, st, _FULL_LAYOUT if full else _MINI_LAYOUT,
                    lambda painter, state: self._draw(painter, state, full))
