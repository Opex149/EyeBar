"""Режим 2 — Always-On Display (StandBy).

Раскладка: две одинаковые колонки по две карточки одного размера по бокам от кота,
колонки центрируются по вертикали — получается симметричная сетка.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import (
    QEasingCurve, QPauseAnimation, QPoint, QPropertyAnimation, QRect, QSequentialAnimationGroup,
    QSize, QTimer, Qt, pyqtSignal,
)
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from ..mascots.base import FORM_FULL
from .icons import icon
from .widgets import (
    IconText, MascotWidget, NotesEdit, NowPlayingView, timer_info, weather_info,
)

CARD_W, CARD_H = 320, 188


class DimOverlay(QWidget):
    """Чёрная плёнка поверх контента — плавное затемнение. Мышь пропускает."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.level = 0.0  # 0 — без затемнения, 0.95 — максимум

    def paintEvent(self, e) -> None:
        if self.level > 0:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * self.level)))
            p.end()


class StandbyWindow(QWidget):
    exitRequested = pyqtSignal()

    def __init__(self, ctx) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.ctx = ctx
        self._entered_at = 0.0
        self._flying = False
        self._flight: QSequentialAnimationGroup | None = None
        self._fly_widget: MascotWidget | None = None
        self._titles: list[tuple[QLabel, str]] = []

        self.content = QWidget(self)
        self.mascot = MascotWidget(ctx.current_mascot(), FORM_FULL, self.content)
        self.mascot.setMinimumSize(380, 300)

        # --- карточки ---
        weather_card, wl = self._card("standby.weather")
        self.weather_w = IconText(30, big=True)
        wl.addStretch(1)
        wl.addWidget(self.weather_w)
        wl.addStretch(1)

        timer_card, tl = self._card("standby.timer")
        self.timer_w = IconText(30, big=True)
        tl.addWidget(self.timer_w)
        presets = QHBoxLayout()
        for n in (5, 10, 25):
            b = QPushButton(str(n))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _checked=False, n=n: ctx.start_timer(n * 60))
            presets.addWidget(b)
        self.btn_stop = QPushButton()
        self.btn_stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stop.clicked.connect(lambda _checked=False: ctx.stop_timer())
        presets.addWidget(self.btn_stop)
        tl.addStretch(1)
        tl.addLayout(presets)

        media_card, ml = self._card("standby.media")
        self.now = NowPlayingView(ctx, 64)
        ml.addWidget(self.now)
        ml.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addStretch(1)
        self.btn_prev = self._media_btn("prev", "prev", "iconMid", 20)
        self.btn_play = self._media_btn("play", "play", "iconMid", 20)
        self.btn_next = self._media_btn("next", "next", "iconMid", 20)
        for b in (self.btn_prev, self.btn_play, self.btn_next):
            row.addWidget(b)
        row.addStretch(1)
        ml.addLayout(row)

        notes_card, nl = self._card("notes.title")
        self.notes = NotesEdit(ctx)
        nl.addWidget(self.notes, 1)

        body = QHBoxLayout(self.content)
        body.setContentsMargins(48, 30, 48, 10)
        body.setSpacing(36)
        body.addLayout(self._column(weather_card, timer_card))
        body.addWidget(self.mascot, 1)
        body.addLayout(self._column(media_card, notes_card))

        # --- нижняя панель: яркость, подсказка, настройки ---
        self.bottom = QWidget(self)
        bl = QHBoxLayout(self.bottom)
        bl.setContentsMargins(48, 6, 48, 18)
        self.bright_w = IconText(18)
        self.bright_w.setFixedWidth(170)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 100)
        self.slider.setFixedWidth(260)
        self.slider.setValue(int(ctx.config.get("brightness")))
        self._brightness_save = QTimer(self)
        self._brightness_save.setSingleShot(True)
        self._brightness_save.setInterval(350)
        self._brightness_save.timeout.connect(ctx.config.save)
        self.slider.valueChanged.connect(self._on_brightness)
        self.slider.sliderReleased.connect(self._flush_brightness)
        self.hint_lbl = QLabel()
        self.hint_lbl.setObjectName("hint")
        self.btn_settings = QPushButton()
        self.btn_settings.setObjectName("icon")
        self.btn_settings.setIcon(icon("gear", 18))
        self.btn_settings.setIconSize(QSize(18, 18))
        self.btn_settings.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.clicked.connect(lambda _checked=False: ctx.open_settings())
        bl.addWidget(self.bright_w)
        bl.addWidget(self.slider)
        bl.addStretch(1)
        bl.addWidget(self.hint_lbl)
        bl.addSpacing(8)
        bl.addWidget(self.btn_settings)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.content, 1)
        root.addWidget(self.bottom)

        self.overlay = DimOverlay(self)
        self._on_brightness(self.slider.value(), save=False)

        QShortcut(QKeySequence("Esc"), self, activated=self.exitRequested.emit)

        ctx.i18n.changed.connect(self.retranslate)
        ctx.weather.updated.connect(lambda _d: self.refresh_labels())
        ctx.timer.tick.connect(lambda _s: self.refresh_labels())
        ctx.alertChanged.connect(self._on_alert)
        ctx.media.updated.connect(self._on_media)
        self.retranslate()

    def _media_btn(self, icon_name: str, action: str, name: str, size: int) -> QPushButton:
        b = QPushButton()
        b.setObjectName(name)
        b.setIcon(icon(icon_name, size))
        b.setIconSize(QSize(size, size))
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _checked=False, a=action: self.ctx.media.command(a))
        return b

    def _card(self, title_key: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setFixedSize(CARD_W, CARD_H)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(18, 14, 18, 14)
        title = QLabel()
        title.setObjectName("cardTitle")
        lay.addWidget(title)
        self._titles.append((title, title_key))
        return frame, lay

    @staticmethod
    def _column(top: QFrame, bottom: QFrame) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(20)
        col.addStretch(1)
        col.addWidget(top)
        col.addWidget(bottom)
        col.addStretch(1)
        return col

    # ---------- жизненный цикл ----------
    def enter(self) -> None:
        self._entered_at = time.monotonic()
        self.apply_settings()
        self.refresh_labels()
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def apply_settings(self) -> None:
        self.mascot.set_mascot(self.ctx.current_mascot())
        self.mascot.set_cursor_tracking(bool(self.ctx.config.get("follow_cursor")))

    def set_emotion(self, name: str) -> None:
        self.mascot.set_emotion(name)

    def set_music_accessory(self, accessory: str) -> None:
        self.mascot.set_music_accessory(accessory)

    def set_temperature_text(self, text: str) -> None:
        self.mascot.set_temperature_text(text)

    def set_weather_state(self, rain_mode: str, windy: bool) -> None:
        self.mascot.set_weather(rain_mode, windy)

    def retranslate(self) -> None:
        i18n = self.ctx.i18n
        for lbl, key in self._titles:
            lbl.setText(i18n.t(key))
        self.hint_lbl.setText(i18n.t("standby.hint"))
        self.btn_stop.setText(i18n.t("timer.stop"))
        self.btn_settings.setToolTip(i18n.t("minibar.settings"))
        self.btn_prev.setToolTip(i18n.t("minibar.prev"))
        self.btn_play.setToolTip(i18n.t("minibar.play"))
        self.btn_next.setToolTip(i18n.t("minibar.next"))
        self.refresh_labels()

    def refresh_labels(self) -> None:
        i18n, ctx = self.ctx.i18n, self.ctx
        self.weather_w.set(*weather_info(i18n, ctx.weather.last, ctx.weather_failed))
        self.timer_w.set(*timer_info(i18n, ctx.timer, ctx.alert_active))
        self.bright_w.set("sun", i18n.t("standby.brightness"))
        data = ctx.weather.last
        temp = f"{float(data['temp']):+.0f}°" if isinstance(data, dict) and isinstance(data.get("temp"), (int, float)) else "--°"
        self.mascot.set_temperature_text(temp)

    def _on_media(self, info) -> None:
        self.btn_play.setIcon(icon("pause" if info.playing else "play", 20))

    def _on_alert(self, on: bool) -> None:
        self.mascot.set_alert(on)
        self.refresh_labels()

    def _on_brightness(self, value: int, save: bool = True) -> None:
        self.overlay.level = (100 - value) / 100.0 * 0.95
        self.overlay.update()
        if save:
            self.ctx.config.set("brightness", value, save=False)
            self._brightness_save.start()

    def _flush_brightness(self) -> None:
        if self._brightness_save.isActive():
            self._brightness_save.stop()
            self.ctx.config.save()

    # ---------- пасхалка: кота сдувает ветром ----------
    def play_blow(self) -> None:
        """Кота уносит за правый край экрана, он прилетает обратно слева (с отскоком).
        Летит «двойник» с общим состоянием — раскладка карточек при этом не дёргается."""
        if not self.isVisible() or self._flying:
            return
        self._flying = True
        rect = QRect(self.mascot.mapTo(self, QPoint(0, 0)), self.mascot.size())
        fly = MascotWidget(self.mascot.mascot, FORM_FULL, self,
                           shared_state=self.mascot.state, passive=True)
        fly.setGeometry(rect)
        fly.show()
        fly.stackUnder(self.overlay)  # затемнение яркости действует и на пролёт
        self._fly_widget = fly
        self.mascot.paint_enabled = False
        self.mascot.update()

        home = rect.topLeft()
        out_right = QPoint(self.width() + 30, home.y())
        in_left = QPoint(-rect.width() - 30, home.y())
        fly_out = QPropertyAnimation(fly, b"pos")
        fly_out.setDuration(900)
        fly_out.setStartValue(home)
        fly_out.setEndValue(out_right)
        fly_out.setEasingCurve(QEasingCurve.Type.InCubic)
        fly_in = QPropertyAnimation(fly, b"pos")
        fly_in.setDuration(1700)
        fly_in.setStartValue(in_left)
        fly_in.setEndValue(home)
        fly_in.setEasingCurve(QEasingCurve.Type.OutBack)

        group = QSequentialAnimationGroup(self)
        group.addAnimation(fly_out)
        group.addAnimation(QPauseAnimation(600))
        group.addAnimation(fly_in)
        group.finished.connect(lambda: self._end_blow(fly))
        self._flight = group
        group.start()

    def _end_blow(self, fly: MascotWidget) -> None:
        if self._fly_widget is not fly:
            return
        fly.hide()
        fly.deleteLater()
        self._fly_widget = None
        self.mascot.paint_enabled = True
        self.mascot.update()
        self._flying = False
        self._flight = None

    def hideEvent(self, e) -> None:
        self._flush_brightness()
        # Escape while the mascot is flying must not leave it permanently hidden.
        if self._flight is not None:
            animation, self._flight = self._flight, None
            animation.stop()
            if self._fly_widget is not None:
                self._end_blow(self._fly_widget)
        super().hideEvent(e)

    # ---------- события ----------
    def resizeEvent(self, e) -> None:
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.bottom.raise_()  # слайдер и подсказка не затемняются
        super().resizeEvent(e)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0A0A0C"))
        p.end()

    def mousePressEvent(self, e) -> None:
        # одиночный клик по коту выключает сигнал таймера
        if self.ctx.alert_active and self.childAt(e.position().toPoint()) is self.mascot:
            self.ctx.dismiss_alert()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e) -> None:
        """Выход ТОЛЬКО по двойному клику на пустом фоне (урок прототипа v1).
        Движение мыши не обрабатывается вообще."""
        if time.monotonic() - self._entered_at < 0.6:
            return
        child = self.childAt(e.position().toPoint())
        if child in (None, self.content, self.mascot, self.overlay):
            self.exitRequested.emit()
