"""Classic EyeBar: a compact blue terminal cat, drawn in the mascot's 200×160 canvas.

The square enclosure is the head and body together. Both display forms keep
its proportions; emotions animate its display, ears and tail, not a new face.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen

from ..base import FORM_FULL, Mascot, MascotState
from ..common import WeatherLayout, paint_scene

BLUE = QColor("#38BDF8")
DARK = QColor("#081C38")

_LAYOUT = WeatherLayout(
    floor=151, canopy_cx=108, canopy_top=3, canopy_by=30, canopy_r=58,
    pole_bottom=117, paw_y=116, wet_cx=100, wet_cy=77, wet_r=48,
    fx_x=159, fx_y=43, paw_fill=QColor("#123557"),
)


def _pen(color: QColor, width: float) -> QPen:
    return QPen(color, width, Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _alpha(color: QColor, opacity: float) -> QColor:
    result = QColor(color)
    result.setAlphaF(max(0.0, min(1.0, opacity)))
    return result


def _appearance(st: MascotState) -> tuple[QColor, QColor, float]:
    blue = QColor(getattr(st, "outline_color", "#38BDF8"))
    if not blue.isValid():
        blue = QColor(BLUE)
    backlight = max(0.0, min(1.0, float(getattr(st, "backlight", 1.0))))
    return blue, blue.lighter(115), backlight


def _outline(p: QPainter, path: QPainterPath, fill, st: MascotState,
             brightness: float = 1.0) -> None:
    blue, edge, backlight = _appearance(st)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for width, opacity in ((7.0, 0.055), (4.0, 0.12)):
        p.setPen(_pen(_alpha(blue, opacity * brightness * backlight), width))
        p.drawPath(path)
    p.setBrush(fill)
    p.setPen(_pen(_alpha(edge, (0.25 + 0.65 * backlight) * brightness), 1.65))
    p.drawPath(path)


class ClassicBlue(Mascot):
    id = "classic_blue"
    name_key = "mascots.classic_blue"
    desc_key = "mascots.classic_blue.desc"

    @staticmethod
    def _tail(p: QPainter, st: MascotState) -> None:
        blue, edge, backlight = _appearance(st)
        # The curl stays inside the common canvas, even in strong wind.
        dx = 4.0 * st.tail2 + 3.0 * st.wind * math.sin(st.t * 8)
        dy = 3.5 * st.tail
        path = QPainterPath(QPointF(149, 117))
        path.cubicTo(178, 130, 186 + dx, 107 + dy, 181 + dx, 88 + dy)
        path.cubicTo(178 + dx, 77 + dy, 165 + dx, 77 + dy, 166 + dx, 89 + dy)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_alpha(blue, 0.12 * backlight), 13))
        p.drawPath(path)
        p.setPen(_pen(_alpha(edge, 0.25 + 0.60 * backlight), 8))
        p.drawPath(path)
        p.setPen(_pen(DARK, 5.3))
        p.drawPath(path)
        tip = QPainterPath(QPointF(181 + dx, 88 + dy))
        tip.cubicTo(178 + dx, 77 + dy, 165 + dx, 77 + dy, 166 + dx, 89 + dy)
        p.setPen(_pen(_alpha(blue, 0.3 + 0.7 * backlight), 5.3))
        p.drawPath(tip)

    @staticmethod
    def _ear(p: QPainter, x: float, sign: int, st: MascotState) -> None:
        blue, _edge, backlight = _appearance(st)
        p.save()
        p.translate(x, 41)
        # Sleep folds the tips slightly; yawns lift them without stretching.
        p.rotate(sign * (7 * st.sleep_phase - 6 * st.yawn + 2 * st.tail))
        p.scale(-sign, 1)
        shape = QPainterPath(QPointF(-12, 0))
        shape.lineTo(-10, -23)
        shape.quadTo(-9, -26, -6, -23)
        shape.lineTo(13, 0)
        shape.closeSubpath()
        _outline(p, shape, QColor("#102D50"), st)
        inner = QPainterPath(QPointF(-6, -7))
        inner.lineTo(-6, -17)
        inner.lineTo(4, -7)
        inner.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(blue, 0.1 + 0.18 * backlight))
        p.drawPath(inner)
        p.restore()

    @staticmethod
    def _screen(p: QPainter, st: MascotState) -> None:
        blue, edge, backlight = _appearance(st)
        rect = QRectF(55, 54, 90, 58)
        shade = QLinearGradient(0, rect.top(), 0, rect.bottom())
        shade.setColorAt(0, QColor("#071528"))
        shade.setColorAt(1, QColor("#020A15"))
        p.setPen(_pen(_alpha(blue, 0.3 + 0.35 * backlight), 1.0))
        p.setBrush(shade)
        p.drawRoundedRect(rect, 7, 7)

        # Blink dims the digits instead of squashing the original digital clock.
        # An alarm always overrides sleep so that its time remains legible.
        sleep = 0.0 if st.alert else max(0.0, min(1.0, st.sleep_phase))
        blink = 1.0 if st.alert else 0.24 + 0.76 * max(0.0, min(1.0, st.blink))
        yawn = 1.0 - 0.22 * st.yawn
        brightness = (1.0 - 0.67 * sleep) * blink * yawn
        brightness *= max(0.3, min(1.25, st.glow))
        brightness *= max(0.65 if st.alert else 0.22, backlight)
        font = QFont("Consolas")
        font.setPixelSize(25)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        clock_rect = QRectF(56, 64, 88, 32)
        clock = f"{st.hh}:{st.mm}"
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.setPen(_alpha(blue, 0.17 * brightness * backlight))
            p.drawText(clock_rect.translated(ox, oy), Qt.AlignmentFlag.AlignCenter, clock)
        p.setPen(_alpha(edge, brightness))
        p.drawText(clock_rect, Qt.AlignmentFlag.AlignCenter, clock)

        # Small status marks retain a useful clock during timer/alarm reactions.
        if st.alert:
            font.setPixelSize(9)
            font.setBold(True)
            p.setFont(font)
            p.setPen(_alpha(edge, max(0.65, backlight)))
            p.drawText(QRectF(60, 96, 80, 12), Qt.AlignmentFlag.AlignCenter, "!  !")
        else:
            p.setPen(_pen(_alpha(blue, 0.28 * brightness), 1.0))
            p.drawLine(QPointF(88, 103), QPointF(112, 103))
        p.setPen(_pen(_alpha(QColor("#C8EEFF"), 0.10), 0.8))
        p.drawLine(QPointF(62, 58), QPointF(135, 58))

    def _body(self, p: QPainter, st: MascotState, full: bool) -> None:
        blue, edge, backlight = _appearance(st)
        self._tail(p, st)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(blue, 0.05 * backlight))
        p.drawEllipse(QPointF(100, 151), 61, 4)

        p.save()
        p.translate(0, 0.8 * st.breath + 1.2 * st.sleep_phase - 1.5 * st.stretch)
        self._ear(p, 63, -1, st)
        self._ear(p, 137, 1, st)

        for x, sign in ((60, -1), (118, 1)):
            paw = QPainterPath()
            paw.addRoundedRect(QRectF(x + sign * st.stretch * 3, 130, 22,
                                      18 + st.stretch * 2), 4, 4)
            _outline(p, paw, QColor("#0D2948"), st, 0.8)
            p.setPen(_pen(_alpha(blue, 0.1 + 0.3 * backlight), 0.7))
            px = x + sign * st.stretch * 3
            p.drawLine(QPointF(px + 8, 142), QPointF(px + 8, 146))
            p.drawLine(QPointF(px + 14, 142), QPointF(px + 14, 146))

        enclosure = QPainterPath()
        enclosure.addRoundedRect(QRectF(44, 34, 112, 103), 14, 14)
        fill = QLinearGradient(0, 34, 0, 137)
        fill.setColorAt(0, QColor("#15385E"))
        fill.setColorAt(0.55, QColor("#0D2748"))
        fill.setColorAt(1, QColor("#081B35"))
        _outline(p, enclosure, fill, st)
        self._screen(p, st)

        # Temperature remains available in the cube without replacing the clock.
        font = QFont("Consolas")
        font.setPixelSize(11 if full else 13)
        font.setBold(True)
        p.setFont(font)
        p.setPen(_alpha(edge, (0.63 if full else 0.9) * (0.3 + 0.7 * backlight)))
        p.drawText(QRectF(69, 116, 62, 16), Qt.AlignmentFlag.AlignCenter, st.temp_text)
        p.restore()

    def paint(self, p: QPainter, form: str, state: MascotState) -> None:
        p.save()
        p.setClipRect(QRectF(0, 0, 200, 160), Qt.ClipOperation.IntersectClip)
        paint_scene(p, state, _LAYOUT,
                    lambda painter, st: self._body(painter, st, form == FORM_FULL))
        p.restore()
