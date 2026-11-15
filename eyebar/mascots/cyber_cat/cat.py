"""Оригинальный кибер-кот прежнего размера, теперь сидит.

Размер и форма головы, экрана, ушей и глаз взяты из исходного EyeBar.
Изменена только поза туловища; мини-форма сохранила исходный масштаб.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen

from ..base import FORM_FULL, Mascot, MascotState
from ..common import WeatherLayout, draw_brows, draw_clock_eye, draw_screen, eye_texts, paint_scene

BODY_TOP = QColor("#2E2E34")
BODY_BOTTOM = QColor("#17171A")
DARK = QColor("#1E1E22")
OUTLINE = QColor(255, 255, 255, 34)
SOFT = QColor(255, 255, 255, 22)
PAD = QColor("#4A4A52")
ACCENT = QColor("#38BDF8")

# опорные точки для зонта / дождя / ветра / эмоций
_FULL_LAYOUT = WeatherLayout(floor=152, canopy_cx=108, canopy_top=3, canopy_by=30, canopy_r=58,
                             pole_bottom=104, paw_y=106, wet_cx=100, wet_cy=56, wet_r=40,
                             fx_x=152, fx_y=40)
_MINI_LAYOUT = WeatherLayout(floor=148, canopy_cx=108, canopy_top=4, canopy_by=40, canopy_r=62,
                             pole_bottom=136, paw_y=138, wet_cx=100, wet_cy=84, wet_r=47,
                             fx_x=160, fx_y=52)


def _grad(top: float, bottom: float, a: QColor = BODY_TOP, b: QColor = BODY_BOTTOM) -> QLinearGradient:
    g = QLinearGradient(0, top, 0, bottom)
    g.setColorAt(0, a)
    g.setColorAt(1, b)
    return g


def _outlined(p: QPainter, path: QPainterPath, brush) -> None:
    p.setBrush(brush)
    p.setPen(QPen(OUTLINE, 1.2))
    p.drawPath(path)


class CyberCat(Mascot):
    id = "cyber_cat"
    name_key = "mascots.cyber_cat"
    desc_key = "mascots.cyber_cat.desc"

    # ---------- голова (общая для обеих форм), локальные координаты вокруг (0, 0) ----------
    def _ear(self, p: QPainter) -> None:
        outer = QPainterPath(QPointF(-47, -8))
        outer.quadTo(-50, -40, -37, -48)
        outer.quadTo(-22, -43, -10, -33)
        outer.closeSubpath()
        _outlined(p, outer, _grad(-48, -8, QColor("#34343A"), BODY_BOTTOM))
        inner = QPainterPath(QPointF(-41, -13))
        inner.quadTo(-43, -34, -36, -40)
        inner.quadTo(-27, -37, -21, -30)
        inner.closeSubpath()
        p.setBrush(DARK)
        p.setPen(QPen(SOFT, 1.0))
        p.drawPath(inner)

    def _head(self, p: QPainter, st: MascotState, cx: float, cy: float, s: float) -> None:
        p.save()
        p.translate(cx, cy)
        p.scale(s, s)

        for sign in (-1, 1):  # уши
            p.save()
            p.scale(sign, 1)
            self._ear(p)
            p.restore()

        head = QPainterPath()
        head.addEllipse(QPointF(0, 0), 52, 40)
        _outlined(p, head, _grad(-40, 40))

        draw_screen(p, QRectF(-44, -24, 88, 46), 16)
        left, right = eye_texts(st)
        draw_clock_eye(p, -23, -3, 34, 28, left, st)
        draw_clock_eye(p, 23, -3, 34, 28, right, st)

        # носик, ротик и усы чуть смещаются за взглядом — лёгкий параллакс
        nx, ny = st.eye_dx * 1.6, st.eye_dy * 1.0
        nose = QPainterPath(QPointF(-3.6 + nx, 8.5 + ny))
        nose.quadTo(nx, 7.8 + ny, 3.6 + nx, 8.5 + ny)
        nose.quadTo(2.6 + nx, 12.5 + ny, nx, 13.2 + ny)
        nose.quadTo(-2.6 + nx, 12.5 + ny, -3.6 + nx, 8.5 + ny)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(228, 228, 231, 210))
        p.drawPath(nose)

        draw_brows(p, -23, 23, -3, 34, 28, st)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(228, 228, 231, 120), 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        emo = st.emotion
        if emo == "sleepy":
            p.drawEllipse(QPointF(nx, 16.5 + ny), 1.8, 1.4)
        else:
            for sign in (-1, 1):
                mouth = QPainterPath(QPointF(nx, 13.4 + ny))
                if emo in ("happy", "love", "dancing"):
                    mouth.quadTo(sign * 2.0 + nx, 21 + ny, sign * 8 + nx, 16.5 + ny)
                elif emo == "sad":
                    mouth.quadTo(sign * 4 + nx, 12 + ny, sign * 8 + nx, 17 + ny)
                elif emo == "surprised":
                    p.drawEllipse(QPointF(nx, 17 + ny), 3, 4)
                    break
                elif emo == "angry":
                    mouth = QPainterPath(QPointF(nx, 14 + ny))
                    mouth.quadTo(sign * 3 + nx, 13 + ny, sign * 7 + nx, 18 + ny)
                else:
                    mouth.quadTo(sign * 0.8 + nx, 17.6 + ny, sign * 5.4 + nx, 17.2 + ny)
                p.drawPath(mouth)

        # усы: на ветру их сдувает в сторону и они трепещут
        wd = st.wind
        p.setPen(QPen(QColor(255, 255, 255, 62), 0.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, sign in enumerate((-1, 1)):
            for j, (y0, y1, x1) in enumerate(((7, 3, 63), (13, 14, 64))):
                k = i * 2 + j
                dx = wd * (9 + 3 * math.sin(st.t * 11 + k))
                dy = wd * 2.2 * math.sin(st.t * 13 + k * 1.7)
                p.drawLine(QPointF(sign * 44, y0), QPointF(sign * x1 + dx, y1 + dy))

        # шерсть на макушке развевается
        if wd > 0.05:
            p.setPen(QPen(QColor(91, 91, 101, int(200 * min(1.0, wd))), 1.5,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for x in (-11, -3, 5, 13):
                p.drawLine(QPointF(x, -39.5),
                           QPointF(x + wd * (5 + 2.5 * math.sin(st.t * 12 + x)), -44.5 - wd * 2))
        p.restore()

    # ---------- детали тела ----------
    def _tail(self, p: QPainter, start: QPointF, c1: QPointF, c2: QPointF, end: QPointF) -> None:
        path = QPainterPath(start)
        path.cubicTo(c1, c2, end)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(OUTLINE, 11, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)
        p.setPen(QPen(BODY_BOTTOM.lighter(120), 8.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)

    def _paw_details(self, p: QPainter, x: float, y: float, k: float = 1.0) -> None:
        """Мягкая подушечка и разделение пальцев на лапке (вид спереди)."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(PAD)
        p.drawEllipse(QPointF(x, y + 1.2 * k), 3.6 * k, 2.4 * k)
        for dx in (-4.4, 0, 4.4):
            p.drawEllipse(QPointF(x + dx * k, y - 2.8 * k), 1.25 * k, 1.5 * k)

    def _leg(self, p: QPainter, x: float, top: float, bottom: float, w: float, dark: bool) -> None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(x - w / 2, top, w, bottom - top - 4), w / 2.4, w / 2.4)
        paw = QPainterPath()
        paw.addEllipse(QPointF(x, bottom - 5.5), w * 0.66, 6.2)
        shape = path.united(paw)
        a, b = (DARK, QColor("#121214")) if dark else (QColor("#2A2A30"), QColor("#1B1B1F"))
        _outlined(p, shape, _grad(top, bottom, a, b))
        self._paw_details(p, x, bottom - 5.2, 0.9 if dark else 1.0)

    def _temperature_embroidery(self, p: QPainter, st: MascotState, x: float, y: float, mini: bool = False) -> None:
        """Небольшая надпись на животе, без отдельного значка погоды."""
        label = getattr(st, "temp_text", "")
        if not label:
            return
        # In the cube 200 logical pixels are reduced to 138 physical pixels.
        # A 32x13 patch became barely 22x9px: use a genuinely readable badge.
        w, h = (68, 26) if mini else (39, 16)
        rect = QRectF(x - w / 2, y - h / 2, w, h)
        p.setPen(QPen(QColor(125, 211, 252, 225 if mini else 62), 1.6 if mini else 0.8))
        p.setBrush(QColor(16, 36, 51, 238 if mini else 45))
        p.drawRoundedRect(rect, h / 2, h / 2)
        font = QFont("Segoe UI")
        font.setPixelSize(18 if mini else 11)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#E0F2FE" if mini else "#7DD3FC"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    # ---------- StandBy: прежний размер кота, новая сидячая поза ----------
    def _paint_full(self, p: QPainter, st: MascotState) -> None:
        dy = st.breath * 1.4
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 9))
        p.drawEllipse(QPointF(100, 153), 64, 5)

        wt = st.wind
        flutter = math.sin(st.t * 14) * 6 * wt
        self._tail(p, QPointF(148, 120 + dy), QPointF(176, 125),
                   QPointF(186 + 9 * st.tail + 8 * wt, 98),
                   QPointF(172 + 17 * st.tail2 + 14 * wt + flutter, 68 + 4 * wt))

        p.save()
        p.translate(0, dy)

        # Сидящий корпус: широкий живот, а не горизонтальное туловище на 4 лапах.
        body = QPainterPath()
        body.addEllipse(QPointF(100, 111), 54, 39)
        _outlined(p, body, _grad(75, 150))

        # По бокам видны округлые задние лапы, сложенные под котом.
        for x in (59, 141):
            haunch = QPainterPath()
            haunch.addEllipse(QPointF(x, 139), 18, 10)
            _outlined(p, haunch, _grad(129, 149, QColor("#2A2A30"), BODY_BOTTOM))

        # Передние лапы опущены вертикально и стоят рядом — это именно сидячая поза.
        for x in (83, 117):
            self._leg(p, x, 115, 151, 20, False)

        # Оригинальная голова 1:1, с теми же щеками, глазами и размером.
        self._head(p, st, 100, 56, 1.0)

        # Оригинальный ошейник и индикатор.
        collar = QPainterPath()
        collar.addRoundedRect(QRectF(74, 94, 52, 8), 4, 4)
        _outlined(p, collar, QColor("#1A1A1E"))
        p.setPen(QPen(QColor(255, 255, 255, 18), 1.0))
        p.setBrush(QColor("#0E0E10"))
        p.drawEllipse(QPointF(100, 98), 4.6, 4.6)
        glow = QColor(ACCENT)
        glow.setAlpha(int(30 + 60 * st.pulse))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(100, 98), 3.4 + 1.2 * st.pulse, 3.4 + 1.2 * st.pulse)
        dot = QColor(ACCENT)
        dot.setAlpha(int(120 + 135 * st.pulse))
        p.setBrush(dot)
        p.drawEllipse(QPointF(100, 98), 1.7, 1.7)

        self._temperature_embroidery(p, st, 100, 130)
        p.restore()

    # ---------- мини-куб: исходный размер головы, сидячий низ ----------
    def _paint_mini(self, p: QPainter, st: MascotState) -> None:
        dy = st.breath * 1.0
        wt = st.wind
        flutter = math.sin(st.t * 14) * 4 * wt
        self._tail(p, QPointF(146, 128), QPointF(184, 138),
                   QPointF(196 + 3 * wt, 104 + 4 * st.tail),
                   QPointF(172 + 8 * st.tail2 + 10 * wt + flutter, 90))
        p.save()
        p.translate(0, dy)

        # Небольшое круглое сидячее тело за исходной большой головой.
        body = QPainterPath()
        body.addEllipse(QPointF(100, 122), 51, 28)
        _outlined(p, body, _grad(94, 150))
        for x in (57, 143):
            haunch = QPainterPath()
            haunch.addEllipse(QPointF(x, 139), 14, 8)
            _outlined(p, haunch, _grad(130, 148))

        # Точные координаты и масштаб головы из старого EyeBar.
        # Same original 1.18 head scale; slightly higher to expose the belly badge.
        self._head(p, st, 100, 77, 1.18)
        for x in (72, 128):
            paw = QPainterPath()
            paw.addEllipse(QPointF(x, 139), 16, 8.5)
            _outlined(p, paw, _grad(130, 148, QColor("#2A2A30"), QColor("#1B1B1F")))
            self._paw_details(p, x, 139, 0.9)

        self._temperature_embroidery(p, st, 100, 134, mini=True)
        p.restore()

    def paint(self, p: QPainter, form: str, state: MascotState) -> None:
        if form == FORM_FULL:
            paint_scene(p, state, _FULL_LAYOUT, self._paint_full)
        else:
            paint_scene(p, state, _MINI_LAYOUT, self._paint_mini)
