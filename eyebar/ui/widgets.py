"""Общие виджеты: анимированный талисман, плеер, заметки, подписи с иконками."""
from __future__ import annotations

import math
import random
import time
from datetime import datetime

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from ..mascots.base import FORM_FULL, LOGICAL_H, LOGICAL_W, Mascot, MascotState
from ..services.timer import format_seconds
from ..services.weather import describe
from .icons import ACCENT, ALERT, ICON, pixmap


class MascotWidget(QWidget):
    """Рисует талисмана и анимирует его ~60 FPS: взгляд за курсором, моргание, хвост, дыхание,
    эмоции и погодные эффекты.

    passive=True — «двойник» с общим состоянием (используется для пролёта сквозь экран)."""

    def __init__(self, mascot: Mascot, form: str, parent=None, *,
                 shared_state: MascotState | None = None, passive: bool = False) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.mascot = mascot
        self.form = form
        self.passive = passive
        self.paint_enabled = True
        self.state = shared_state if shared_state is not None else MascotState()
        self._last = time.monotonic()
        self._next_blink = self._last + random.uniform(2.0, 4.5)
        self._blink_start: float | None = None
        self._tail_phase = 0.0
        self._follow_cursor = True
        self._umbrella_target = 0.0
        self._rain_target = 0.0
        self._wind_target = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    # ---------- управление ----------
    def set_mascot(self, mascot: Mascot) -> None:
        self.mascot = mascot
        self.update()

    def set_alert(self, on: bool) -> None:
        self.state.alert = on

    def set_emotion(self, name: str) -> None:
        self.state.emotion = name
        self.update()

    def set_cursor_tracking(self, enabled: bool) -> None:
        self._follow_cursor = enabled

    def set_music_accessory(self, accessory: str) -> None:
        self.state.music_accessory = accessory
        self.update()

    def set_temperature_text(self, text: str) -> None:
        self.state.temp_text = text
        self.update()

    def set_weather(self, rain_mode: str, windy: bool) -> None:
        """rain_mode: 'none' | 'umbrella' | 'wet'. Значения плавно подтягиваются в _tick."""
        self._umbrella_target = 1.0 if rain_mode == "umbrella" else 0.0
        self._rain_target = 1.0 if rain_mode in ("umbrella", "wet") else 0.0
        self._wind_target = 1.0 if windy else 0.0

    def showEvent(self, e) -> None:
        self._last = time.monotonic()
        self._timer.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:
        self._timer.stop()
        super().hideEvent(e)

    # ---------- анимация ----------
    def _tick(self) -> None:
        if self.passive:
            self.update()
            return
        now = time.monotonic()
        dt = min(0.1, now - self._last)
        self._last = now
        st = self.state
        st.t += dt

        ease = 1 - math.exp(-dt * 3.0)  # плавный выход на нужное значение
        st.umbrella += (self._umbrella_target - st.umbrella) * ease
        st.rain += (self._rain_target - st.rain) * ease
        st.wind += (self._wind_target - st.wind) * ease

        # взгляд плавно следует за курсором
        centre = self.mapToGlobal(self.rect().center())
        cur = QCursor.pos()
        dx, dy = cur.x() - centre.x(), cur.y() - centre.y()
        dist = math.hypot(dx, dy)
        strength = min(1.0, dist / 250.0)
        watching = self._follow_cursor and st.emotion not in ("angry", "sleepy", "sad")
        tx = dx / dist * strength if dist and watching else 0.0
        ty = dy / dist * strength if dist and watching else 0.0
        k = 1 - math.exp(-dt * 10)
        st.eye_dx += (tx - st.eye_dx) * k
        st.eye_dy += (ty - st.eye_dy) * k

        # моргание
        if self._blink_start is None and now >= self._next_blink:
            self._blink_start = now
        if self._blink_start is not None:
            t = (now - self._blink_start) / 0.18
            if t >= 1:
                self._blink_start = None
                self._next_blink = now + random.uniform(2.5, 5.5)
                st.blink = 1.0
            else:
                st.blink = abs(1 - 2 * t)

        # хвост (на ветру быстрее), дыхание (во сне медленнее и глубже), пульс, радость
        sleepy = st.emotion == "sleepy"
        speed = (8.0 if st.alert else (2.6 if self.form == FORM_FULL else 1.5)) * (1.0 + 1.6 * st.wind)
        self._tail_phase += dt * speed
        st.tail = math.sin(self._tail_phase)
        st.tail2 = math.sin(self._tail_phase - 0.9)  # кончик хвоста чуть запаздывает
        st.breath = math.sin(st.t * (0.8 if sleepy else 1.5)) * (1.6 if sleepy else 1.0)
        st.pulse = abs(math.sin(st.t * 1.3)) ** 3
        st.glow = 0.6 + 0.4 * abs(math.sin(now * 8)) if st.alert else 1.0
        target_bob = abs(math.sin(st.t * (8.0 if st.emotion == "dancing" else 5.5))) * (4.6 if st.emotion == "dancing" else 2.6) if st.emotion in ("happy", "dancing") else 0.0
        st.bob += (target_bob - st.bob) * (1 - math.exp(-dt * 12))

        d = datetime.now()
        st.hh, st.mm = f"{d.hour:02d}", f"{d.minute:02d}"
        self.update()

    def paintEvent(self, e) -> None:
        if not self.paint_enabled:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        scale = min(self.width() / LOGICAL_W, self.height() / LOGICAL_H)
        p.translate((self.width() - LOGICAL_W * scale) / 2, (self.height() - LOGICAL_H * scale) / 2)
        p.scale(scale, scale)
        self.mascot.paint(p, self.form, self.state)
        p.end()


def mascot_preview(mascot: Mascot, form: str, width: int, height: int) -> QPixmap:
    """Статичная картинка персонажа для карточек в настройках."""
    dpr = 2.0
    pm = QPixmap(int(width * dpr), int(height * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    scale = min(width / LOGICAL_W, height / LOGICAL_H)
    p.translate((width - LOGICAL_W * scale) / 2, (height - LOGICAL_H * scale) / 2)
    p.scale(scale, scale)
    d = datetime.now()
    st = MascotState(tail=0.35, tail2=0.1, pulse=0.8, hh=f"{d.hour:02d}", mm=f"{d.minute:02d}", temp_text="+21°")
    mascot.paint(p, form, st)
    p.end()
    return pm


class NotesEdit(QPlainTextEdit):
    """Notes are shared by the mini-bar dialog and StandBy without stale overwrites."""

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._last_saved = str(ctx.config.get("notes"))
        self.setPlainText(self._last_saved)
        self._save = QTimer(self)
        self._save.setSingleShot(True)
        self._save.setInterval(600)
        self._save.timeout.connect(self.flush)
        self.textChanged.connect(self._save.start)
        ctx.i18n.changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self) -> None:
        self.setPlaceholderText(self.ctx.i18n.t("notes.placeholder"))

    def _sync_from_config(self) -> None:
        if self._save.isActive():
            return  # unsaved local edit takes precedence
        saved = str(self.ctx.config.get("notes"))
        if saved != self._last_saved:
            if saved != self.toPlainText():
                self.blockSignals(True)
                try:
                    self.setPlainText(saved)
                finally:
                    self.blockSignals(False)
            self._last_saved = saved

    def flush(self) -> None:
        self._save.stop()
        value = self.toPlainText()
        if value != self._last_saved:
            self.ctx.config.set("notes", value)
            self._last_saved = value

    def showEvent(self, e) -> None:
        self._sync_from_config()
        super().showEvent(e)

    def focusInEvent(self, e) -> None:
        self._sync_from_config()
        super().focusInEvent(e)

    def focusOutEvent(self, e) -> None:
        self.flush()
        super().focusOutEvent(e)


class ElidedLabel(QLabel):
    """Подпись, которая сама обрезает длинный текст многоточием и не растягивает окно."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(10)

    def setText(self, text: str) -> None:  # noqa: N802 (имя Qt)
        self._full = text
        self.setToolTip(text)
        self._apply()

    def _apply(self) -> None:
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(10, self.width()))
        QLabel.setText(self, shown)

    def resizeEvent(self, e) -> None:
        self._apply()
        super().resizeEvent(e)


class IconText(QWidget):
    """Векторная иконка + текст в одну строку."""

    def __init__(self, icon_size: int = 18, big: bool = False, name: str | None = None,
                 stretch: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._size = icon_size
        self._key: tuple | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(icon_size, icon_size)
        self.text_lbl = ElidedLabel() if stretch else QLabel()
        if big:
            self.text_lbl.setObjectName("big")
        elif name:
            self.text_lbl.setObjectName(name)
        lay.addWidget(self.icon_lbl)
        lay.addWidget(self.text_lbl, 1 if stretch else 0)

    def set(self, name: str, text: str, color: str = ICON) -> None:
        if self._key != (name, color):
            self._key = (name, color)
            self.icon_lbl.setPixmap(pixmap(name, self._size, color))
        self.text_lbl.setText(text)


class CoverLabel(QLabel):
    """Обложка трека со скруглёнными углами; без обложки — аккуратная заглушка с нотой."""

    def __init__(self, size: int, radius: int = 10, parent=None) -> None:
        super().__init__(parent)
        self._size = size
        self._radius = radius
        self.setFixedSize(size, size)
        self.set_cover(None)

    def set_cover(self, data: bytes | None) -> None:
        dpr = 2.0
        s = self._size
        out = QPixmap(int(s * dpr), int(s * dpr))
        out.setDevicePixelRatio(dpr)
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, s, s), self._radius, self._radius)
        p.setClipPath(path)
        src = QPixmap()
        if data and src.loadFromData(data) and src.width() > 0 and src.height() > 0:
            side = min(src.width(), src.height())  # центральный квадрат
            crop = QRectF((src.width() - side) / 2, (src.height() - side) / 2, side, side)
            p.drawPixmap(QRectF(0, 0, s, s), src, crop)
        else:
            p.fillPath(path, QColor(255, 255, 255, 15))
            note = pixmap("note", int(s * 0.5), "#71717A", glow=False)
            p.drawPixmap(QPointF(s * 0.25, s * 0.25), note)
        p.end()
        self.setPixmap(out)


class NowPlayingView(QWidget):
    """Обложка + название + исполнитель из системного плеера Windows."""

    def __init__(self, ctx, cover_size: int = 44, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._thumb: bytes | None = None
        self.cover = CoverLabel(cover_size)
        self.title = ElidedLabel()
        self.title.setObjectName("trackTitle")
        self.artist = ElidedLabel()
        self.artist.setObjectName("muted")
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addStretch(1)
        col.addWidget(self.title)
        col.addWidget(self.artist)
        col.addStretch(1)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self.cover)
        row.addLayout(col, 1)
        ctx.media.updated.connect(self.set_info)
        ctx.i18n.changed.connect(lambda: self.set_info(ctx.media.info))
        self.set_info(ctx.media.info)

    def set_info(self, info) -> None:
        t = self.ctx.i18n.t
        if info.available and (info.title or info.artist):
            self.title.setText(info.title or t("media.unknown_track"))
            self.artist.setText(info.artist or info.album)
        else:
            self.title.setText(t("media.nothing" if self.ctx.media.backend_ok else "media.unavailable"))
            self.artist.setText("")
        if info.thumb != self._thumb:
            self._thumb = info.thumb
            self.cover.set_cover(info.thumb)


def weather_info(i18n, data, failed: bool) -> tuple[str, str]:
    """(имя иконки, текст) для текущей погоды."""
    if data is None:
        return "cloud", i18n.t("weather.error" if failed else "weather.loading")
    key, icon_name = describe(int(data["code"]))
    return icon_name, f"{data['temp']:+.0f}°C · {i18n.t(key)}"


def weather_short(data) -> tuple[str, str]:
    """(иконка, температура) — для свёрнутого кубика."""
    if data is None:
        return "cloud", "--"
    _key, icon_name = describe(int(data["code"]))
    return icon_name, f"{data['temp']:+.0f}°C"


def timer_info(i18n, timer, alert: bool) -> tuple[str, str, str]:
    """(имя иконки, текст, цвет) для таймера."""
    if alert:
        return "bell", i18n.t("timer.finished"), ALERT
    if timer.active:
        return "timer", format_seconds(timer.remaining()), ACCENT
    return "timer", "--:--", ICON
