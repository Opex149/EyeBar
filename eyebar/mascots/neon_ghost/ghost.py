"""Неоновый призрак в спокойной графитовой палитре: приземистый в мини-баре, парящий в StandBy."""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from ..base import FORM_FULL, Mascot, MascotState
from ..common import WeatherLayout, draw_brows, draw_clock_eye, draw_screen, eye_texts, paint_scene

EDGE = QColor(255, 255, 255, 56)
HALO = QColor(255, 255, 255, 14)

_FULL_LAYOUT = WeatherLayout(floor=150, canopy_cx=108, canopy_top=3, canopy_by=30, canopy_r=58,
                             pole_bottom=100, paw_y=102, wet_cx=100, wet_cy=70, wet_r=36,
                             fx_x=150, fx_y=44, paw_fill=QColor("#2E2E34"))
_MINI_LAYOUT = WeatherLayout(floor=142, canopy_cx=108, canopy_top=4, canopy_by=38, canopy_r=60,
                             pole_bottom=104, paw_y=106, wet_cx=100, wet_cy=78, wet_r=38,
                             fx_x=158, fx_y=50, paw_fill=QColor("#2E2E34"))


class NeonGhost(Mascot):
    id = "neon_ghost"
    name_key = "mascots.neon_ghost"
    desc_key = "mascots.neon_ghost.desc"

    @staticmethod
    def _body(left: float, right: float, top: float, shoulder: float,
              bottom: float, waves: int, st: MascotState) -> QPainterPath:
        """Купол сверху, волнистый подол снизу (на ветру подол трепещет сильнее)."""
        k = (shoulder - top) / 0.75
        path = QPainterPath(QPointF(left, shoulder))
        path.cubicTo(QPointF(left, shoulder - k), QPointF(right, shoulder - k), QPointF(right, shoulder))
        path.lineTo(QPointF(right, bottom))
        seg = (right - left) / waves
        for i in range(waves):
            x0 = right - seg * i
            x1 = x0 - seg
            amp = 16 + 7 * st.wind * math.sin(st.t * 12 + i)
            ctrl_y = bottom + amp if i % 2 == 0 else bottom - amp
            path.quadTo(QPointF((x0 + x1) / 2, ctrl_y), QPointF(x1, bottom))
        path.closeSubpath()
        return path

    def _draw(self, p: QPainter, st: MascotState, full: bool) -> None:
        p.translate(0, st.breath * (3.0 if full else 1.5))  # парит вверх-вниз

        if full:
            path = self._body(52, 148, 24, 76, 138, 4, st)
            eye_y, eye_dx, top, bottom = 68.0, 23.0, 24.0, 150.0
        else:
            path = self._body(40, 160, 20, 84, 132, 4, st)
            eye_y, eye_dx, top, bottom = 76.0, 26.0, 20.0, 142.0

        if st.wind > 0.02:  # ветер кренит призрака
            p.translate(100, bottom)
            p.rotate(st.wind * (4 + 1.6 * math.sin(st.t * 9)))
            p.translate(-100, -bottom)

        grad = QLinearGradient(100, top, 100, bottom)
        grad.setColorAt(0, QColor("#3A3A42"))
        grad.setColorAt(1, QColor("#16161A"))

        if full:  # ручки позади тела, чуть качаются
            p.setPen(QPen(EDGE, 1.2))
            p.setBrush(grad)
            for sign, x in ((-1, 46.0), (1, 154.0)):
                p.drawEllipse(QPointF(x, 100 + sign * st.tail * 4), 8.5, 14)

        p.setBrush(QColor(0, 0, 0, 0))
        p.setPen(QPen(HALO, 9))
        p.drawPath(path)
        p.setBrush(grad)
        p.setPen(QPen(EDGE, 1.3))
        p.drawPath(path)

        screen_w = eye_dx * 2 + 46
        draw_screen(p, QRectF(100 - screen_w / 2, eye_y - 22, screen_w, 44), 15)
        left, right = eye_texts(st)
        draw_clock_eye(p, 100 - eye_dx, eye_y, 34, 28, left, st)
        draw_clock_eye(p, 100 + eye_dx, eye_y, 34, 28, right, st)
        draw_brows(p, 100 - eye_dx, 100 + eye_dx, eye_y, 34, 28, st)

        # ротик зависит от эмоции
        my = eye_y + 36
        p.setBrush(QColor(0, 0, 0, 0))
        p.setPen(QPen(QColor(228, 228, 231, 150), 1.4))
        if st.emotion in ("happy", "love", "dancing"):
            smile = QPainterPath(QPointF(93, my - 1))
            smile.quadTo(QPointF(100, my + 9), QPointF(107, my - 1))
            p.drawPath(smile)
        elif st.emotion == "angry":
            frown = QPainterPath(QPointF(93, my + 3))
            frown.quadTo(QPointF(100, my - 5), QPointF(107, my + 3))
            p.drawPath(frown)
        elif st.emotion == "sad":
            p.drawArc(QRectF(93, my - 2, 14, 11), 0, 180 * 16)
        elif st.emotion == "sleepy":
            p.drawEllipse(QPointF(100, my), 3.0, 2.2)
        else:
            p.drawEllipse(QPointF(100, my), 5.0, 3.6)

    def paint(self, p: QPainter, form: str, st: MascotState) -> None:
        full = form == FORM_FULL
        paint_scene(p, st, _FULL_LAYOUT if full else _MINI_LAYOUT,
                    lambda painter, state: self._draw(painter, state, full))
