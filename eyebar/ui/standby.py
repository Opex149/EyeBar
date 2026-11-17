"""Режим 2 — Always-On Display (StandBy).

Раскладка сохраняет четыре карточки и персонажа. Размеры заданы в логических
координатах Qt, без повторного умножения на системный DPI.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import (
    QDateTime, QEvent, QEasingCurve, QLocale, QParallelAnimationGroup, QPauseAnimation, QPoint,
    QPropertyAnimation, QRect, QSequentialAnimationGroup, QSize, QTimer, Qt, pyqtSignal,
)
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QInputDialog, QLabel,
    QLayout, QPushButton, QSizePolicy, QSlider, QSpacerItem, QVBoxLayout, QWidget,
)

from ..mascots.base import FORM_FULL
from .icons import icon
from .widgets import (
    IconText, MascotWidget, NotesEdit, NowPlayingView, timer_info, weather_info,
)

class StandbyWindow(QWidget):
    exitRequested = pyqtSignal()

    def __init__(self, ctx) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.ctx = ctx
        self._entered_at = 0.0
        self._night = False
        self._flying = False
        self._flight: QSequentialAnimationGroup | None = None
        self._fly_widget: MascotWidget | None = None
        self._titles: list[tuple[QLabel, str]] = []
        self._cards: list[QFrame] = []
        self._transition: QParallelAnimationGroup | None = None
        self._exiting = False
        self._animations_enabled = True
        self._position = "center"
        self._profile = "classic"
        self._content_brightness = 1.0
        self._controls_hidden = False
        self._controls_animation: QPropertyAnimation | None = None
        self._alarm_animation: QPropertyAnimation | None = None
        self._autohide = False
        self._controls_timer = QTimer(self)
        self._controls_timer.setSingleShot(True)
        self._controls_timer.setInterval(5000)
        self._controls_timer.timeout.connect(self._hide_controls)

        self.content = QWidget(self)
        self.content.setObjectName("standbyContent")
        self.clock = QLabel(self.content)
        self.clock.setObjectName("standbyClock")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.date = QLabel(self.content)
        self.date.setObjectName("standbyDate")
        self.date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._clock_timer = QTimer(self)
        self._clock_timer.setSingleShot(True)
        self._clock_timer.timeout.connect(self._refresh_clock)
        self.mascot = MascotWidget(ctx.current_mascot(), FORM_FULL, self.content)
        self.mascot.setMinimumSize(180, 140)

        # --- карточки ---
        weather_card, wl = self._card("standby.weather")
        self.weather_w = IconText(30, big=True)
        self.weather_city = QLabel()
        self.weather_city.setObjectName("muted")
        self.weather_city.setWordWrap(True)
        self.weather_updated = QLabel()
        self.weather_updated.setObjectName("muted")
        self.weather_updated.setWordWrap(True)
        wl.addStretch(1)
        wl.addWidget(self.weather_w)
        wl.addWidget(self.weather_city)
        wl.addWidget(self.weather_updated)
        wl.addStretch(1)

        timer_card, tl = self._card("standby.timer")
        self.timer_w = IconText(30, big=True)
        tl.addWidget(self.timer_w)
        presets = QHBoxLayout()
        presets.setSpacing(6)
        self._preset_buttons = []
        for n in (5, 15, 25, 45):
            b = QPushButton(str(n))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _checked=False, n=n: ctx.start_timer(n * 60))
            presets.addWidget(b)
            self._preset_buttons.append((b, n))
        self.btn_custom = QPushButton("…")
        self.btn_custom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_custom.clicked.connect(self._custom_timer)
        presets.addWidget(self.btn_custom)
        self.btn_pause = QPushButton()
        self.btn_pause.setIcon(icon("pause", 16))
        self.btn_pause.setIconSize(QSize(16, 16))
        self.btn_pause.clicked.connect(self._toggle_timer_pause)
        self.btn_reset = QPushButton("↺")
        self.btn_reset.clicked.connect(lambda _checked=False: ctx.reset_timer())
        self.btn_stop = QPushButton()
        self.btn_stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_stop.clicked.connect(lambda _checked=False: ctx.stop_timer())
        timer_actions = QHBoxLayout()
        timer_actions.setSpacing(6)
        timer_actions.addWidget(self.btn_pause)
        timer_actions.addWidget(self.btn_reset)
        timer_actions.addWidget(self.btn_stop, 1)
        tl.addLayout(presets)
        tl.addLayout(timer_actions)

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

        self._card_map = {"weather": weather_card, "timer": timer_card,
                          "music": media_card, "notes": notes_card}
        self.left_column = self._column(weather_card, timer_card)
        self.right_column = self._column(media_card, notes_card)
        self.body = QHBoxLayout()
        self.body.addWidget(self.left_column)
        self.body.addWidget(self.mascot, 1)
        self.body.addWidget(self.right_column)
        self.header = QWidget(self.content)
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(3)
        header_layout.addWidget(self.clock)
        header_layout.addWidget(self.date)
        self.dashboard_status = QFrame(self.content)
        self.dashboard_status.setObjectName("dashboardStatus")
        status_layout = QHBoxLayout(self.dashboard_status)
        status_layout.setContentsMargins(14, 8, 14, 8)
        self.next_alarm = QLabel()
        self.next_alarm.setWordWrap(True)
        self.weather_stamp = QLabel()
        self.weather_stamp.setAlignment(Qt.AlignmentFlag.AlignRight |
                                        Qt.AlignmentFlag.AlignVCenter)
        self.weather_stamp.setWordWrap(True)
        status_layout.addWidget(self.next_alarm, 1)
        status_layout.addWidget(self.weather_stamp, 1)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._top_space = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._bottom_space = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.content_layout.addItem(self._top_space)
        self.content_layout.addWidget(self.header)
        self.content_layout.addWidget(self.dashboard_status)
        self.content_layout.addLayout(self.body, 1)
        self.content_layout.addItem(self._bottom_space)
        self.dashboard_status.hide()
        self._content_opacity = QGraphicsOpacityEffect(self.content)
        self._content_opacity.setOpacity(1.0)
        self.content.setGraphicsEffect(self._content_opacity)

        # --- нижняя панель: яркость, подсказка, настройки ---
        self.bottom = QWidget(self)
        bl = QHBoxLayout(self.bottom)
        self.bottom_layout = bl
        bl.setContentsMargins(28, 6, 28, 18)
        self.bright_w = IconText(18)
        self.bright_w.setFixedWidth(100)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(10, 100)
        self.slider.setFixedWidth(180)
        self.slider.setValue(int(ctx.config.get("brightness")))
        self._brightness_save = QTimer(self)
        self._brightness_save.setSingleShot(True)
        self._brightness_save.setInterval(350)
        self._brightness_save.timeout.connect(ctx.config.save)
        self.slider.valueChanged.connect(self._on_brightness)
        self.slider.sliderReleased.connect(self._flush_brightness)
        self.btn_alarm = QPushButton()
        self.btn_alarm.setObjectName("standbyAlarm")
        self.btn_alarm.setStyleSheet("padding: 6px 10px; min-width: 30px;")
        self.btn_alarm.setIcon(icon("bell", 18))
        self.btn_alarm.setIconSize(QSize(18, 18))
        self.btn_alarm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_alarm.clicked.connect(lambda _checked=False: ctx.open_alarms())
        self.btn_night = QPushButton()
        self.btn_night.setObjectName("icon")
        self.btn_night.setIcon(icon("moon", 18))
        self.btn_night.setIconSize(QSize(18, 18))
        self.btn_night.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_night.clicked.connect(lambda _checked=False: ctx.toggle_night())
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
        bl.addWidget(self.btn_alarm)
        bl.addWidget(self.btn_night)
        bl.addSpacing(8)
        bl.addWidget(self.btn_settings)

        root = QVBoxLayout(self)
        # A large previous profile must not prevent shrinking on a DPI change.
        root.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.content, 1)
        root.addWidget(self.bottom)

        self._bottom_opacity = QGraphicsOpacityEffect(self.bottom)
        self._bottom_opacity.setOpacity(1.0)
        self._bottom_opacity.setEnabled(False)
        self.bottom.setGraphicsEffect(self._bottom_opacity)

        # Alarm ringing panel: buttons remain clickable above the dim layer.
        self.alarm_panel = QFrame(self)
        self.alarm_panel.setObjectName("alarmPanel")
        self.alarm_panel.setStyleSheet("""
            QFrame#alarmPanel { background: #181A21; border: 2px solid #7DD3FC;
                                border-radius: 24px; }
            QFrame#alarmPanel QLabel { color: #FAFAFA; border: 0px; }
            QFrame#alarmPanel QPushButton { padding: 12px 18px; font-size: 15px; }
        """)
        al = QVBoxLayout(self.alarm_panel)
        al.setContentsMargins(28, 28, 28, 28)
        al.setSpacing(18)
        self.alarm_title = QLabel()
        self.alarm_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alarm_title.setStyleSheet("font-size: 19px; font-weight: 650;")
        self.alarm_time = QLabel()
        self.alarm_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alarm_time.setStyleSheet("font-size: 55px; font-weight: 700;")
        al.addWidget(self.alarm_title)
        al.addWidget(self.alarm_time)
        alarm_actions = QHBoxLayout()
        self.btn_snooze = QPushButton()
        self.btn_snooze.clicked.connect(lambda _checked=False: ctx.alarms.snooze(5))
        self.btn_alarm_stop = QPushButton()
        self.btn_alarm_stop.clicked.connect(lambda _checked=False: ctx.alarms.stop_ringing())
        alarm_actions.addWidget(self.btn_snooze)
        alarm_actions.addWidget(self.btn_alarm_stop)
        al.addLayout(alarm_actions)
        self.alarm_panel.setFixedSize(430, 250)
        self._alarm_opacity = QGraphicsOpacityEffect(self.alarm_panel)
        self._alarm_opacity.setOpacity(1.0)
        self._alarm_opacity.setEnabled(False)
        self.alarm_panel.setGraphicsEffect(self._alarm_opacity)
        self.alarm_panel.hide()

        self._on_brightness(self.slider.value(), save=False)

        QShortcut(QKeySequence("Esc"), self, activated=self.request_exit)

        ctx.i18n.changed.connect(self.retranslate)
        ctx.weather.updated.connect(lambda _d: self.refresh_labels())
        ctx.timer.tick.connect(lambda _s: self.refresh_labels())
        ctx.alarms.changed.connect(self.refresh_labels)
        ctx.alertChanged.connect(self._on_alert)
        # StandBy consumes media only while visible; reopening refreshes it once.
        ctx.media.updated.disconnect(self.now.set_info)
        ctx.media.updated.connect(self._on_media)
        QApplication.instance().installEventFilter(self)
        self.setMouseTracking(True)
        for child in self.findChildren(QWidget):
            child.setMouseTracking(True)
        self.retranslate()
        self._update_layout()

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
        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._cards.append(frame)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(18, 14, 18, 14)
        title = QLabel()
        title.setObjectName("cardTitle")
        lay.addWidget(title)
        self._titles.append((title, title_key))
        return frame, lay

    @staticmethod
    def _column(top: QFrame, bottom: QFrame) -> QWidget:
        column = QWidget()
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(20)
        col.addStretch(1)
        col.addWidget(top)
        col.addWidget(bottom)
        col.addStretch(1)
        return column

    # ---------- жизненный цикл ----------
    def _custom_timer(self) -> None:
        t = self.ctx.i18n.t
        minutes, accepted = QInputDialog.getInt(
            self, t("timer.custom.title"), t("timer.custom.label"), 15, 1, 1440,
        )
        if accepted:
            self.ctx.start_timer(minutes * 60)
        self._wake_controls()

    def _toggle_timer_pause(self) -> None:
        if self.ctx.timer.active:
            self.ctx.pause_timer()
        elif self.ctx.timer.state in ("paused", "ready"):
            self.ctx.resume_timer()
        elif self.ctx.timer.initial_duration:
            self.ctx.start_timer(self.ctx.timer.initial_duration)

    def _stop_controls_animation(self) -> None:
        if self._controls_animation is not None:
            animation, self._controls_animation = self._controls_animation, None
            animation.stop()
            animation.deleteLater()

    def _set_controls_visible(self, visible: bool) -> None:
        self._stop_controls_animation()
        self._controls_hidden = not visible
        self.bottom.setEnabled(visible)
        self.bottom.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not visible)
        target = 1.0 if visible else 0.0
        if not self._animations_enabled or not self.isVisible() or self._exiting:
            self._bottom_opacity.setOpacity(target)
            self._bottom_opacity.setEnabled(not visible)
            return
        self._bottom_opacity.setEnabled(True)
        animation = QPropertyAnimation(self._bottom_opacity, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(self._bottom_opacity.opacity())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def finished() -> None:
            if self._controls_animation is animation:
                self._controls_animation = None
                animation.deleteLater()
                # Opaque navigation must render directly. A persistent Qt
                # effect can retain a blank source after hide/profile changes.
                self._bottom_opacity.setEnabled(not visible)

        animation.finished.connect(finished)
        self._controls_animation = animation
        animation.start()

    def _hide_controls(self) -> None:
        if (not self.isVisible() or not self._autohide or self._exiting or
                self.ctx.alert_active or self.ctx.alarms.ringing is not None or
                self.alarm_panel.isVisible()):
            return
        focused = QApplication.focusWidget()
        if (QApplication.mouseButtons() != Qt.MouseButton.NoButton or
                (focused is not None and
                 (focused is self.notes or self.notes.isAncestorOf(focused)))):
            self._controls_timer.start()
            return
        self._set_controls_visible(False)

    def _wake_controls(self) -> None:
        if self._exiting:
            return
        if self._controls_hidden:
            self._set_controls_visible(True)
        self._controls_timer.stop()
        if (self._autohide and self.isVisible() and not self.ctx.alert_active and
                self.ctx.alarms.ringing is None and not self.alarm_panel.isVisible()):
            self._controls_timer.start()

    def eventFilter(self, watched, event) -> bool:
        if (self.isVisible() and isinstance(watched, QWidget) and
                (watched is self or self.isAncestorOf(watched)) and
                event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
                                 QEvent.Type.Wheel, QEvent.Type.KeyPress, QEvent.Type.TouchBegin)):
            self._wake_controls()
        return super().eventFilter(watched, event)

    def _refresh_clock(self) -> None:
        now = QDateTime.currentDateTime()
        self.clock.setText(now.toString("HH:mm"))
        language = self.ctx.i18n.language
        locale = QLocale("ru_RU" if language == "ru" else language)
        self.date.setText(locale.toString(now.date(), "dddd, d MMMM"))
        if self.isVisible():
            # The clock has minute precision: there is no idle frame loop.
            remaining = 60000 - now.time().second() * 1000 - now.time().msec()
            self._clock_timer.start(max(1, remaining))

    def _update_layout(self) -> None:
        """Scale within Qt logical pixels, including fractional Windows scaling."""
        width, height = self.width(), self.height()
        scale = max(0.72, min(1.55, width / 1440, height / 900))
        margin = max(20, round(40 * scale))
        gap = max(12, round(26 * scale))
        card_width = max(216, min(520, round(width * 0.225)))
        card_height = max(148, min(310, round(height * 0.21)))
        clock_size = max(56, min(180, round(height * 0.12)))
        if self._profile == "minimal":
            clock_size = max(100, min(360, round(height * 0.28)))
        elif self._profile == "dashboard":
            clock_size = max(52, min(150, round(height * 0.10)))
        date_size = max(15, min(30, round(20 * scale)))
        self.content_layout.setContentsMargins(margin, max(8, round(20 * scale)),
                                               margin, max(4, round(10 * scale)))
        self.content_layout.setSpacing(max(3, round(5 * scale)))
        self.body.setSpacing(gap)
        for column in (self.left_column, self.right_column):
            column.layout().setSpacing(gap)
        for card in self._cards:
            card.setFixedSize(card_width, card_height)
            padding = max(12, round(18 * scale))
            card.layout().setContentsMargins(padding, max(10, round(14 * scale)),
                                            padding, max(10, round(14 * scale)))
            card.layout().setSpacing(max(5, round(8 * scale)))
        self.clock.setStyleSheet(
            f"font-family: 'Segoe UI', 'Noto Sans', sans-serif; font-size: {clock_size}px;"
            "font-weight: 600; color: #F4F4F5; background: transparent;"
        )
        self.date.setStyleSheet(f"font-size: {date_size}px; color: #A1A1AA;")
        self.content.setStyleSheet(
            "QFrame#card { background: rgba(255,255,255,0.045);"
            "border: 1px solid rgba(255,255,255,0.10); border-radius: 20px; }"
            f"QLabel#cardTitle {{ font-size: {max(11, round(13 * scale))}px;"
            "color: #A1A1AA; }"
            f"QLabel#trackTitle {{ font-size: {max(12, round(16 * scale))}px; }}"
            f"QLabel#muted {{ font-size: {max(11, round(13 * scale))}px; }}"
            "QFrame#dashboardStatus { background: rgba(255,255,255,0.035);"
            "border: 1px solid rgba(255,255,255,0.08); border-radius: 14px; }"
            f"QFrame#dashboardStatus QLabel {{ font-size: {max(11, round(14 * scale))}px; }}"
        )
        for field in (self.weather_w, self.timer_w):
            field.text_lbl.setStyleSheet(f"font-size: {max(20, round(30 * scale))}px;")
        self.notes.setStyleSheet(f"font-size: {max(12, round(15 * scale))}px;")
        for button, _minutes in self._preset_buttons:
            button.setStyleSheet(
                f"font-size: {max(11, round(13 * scale))}px; padding: 6px 8px;"
            )
        for button in (self.btn_custom, self.btn_stop, self.btn_pause, self.btn_reset):
            button.setStyleSheet(
                f"font-size: {max(11, round(13 * scale))}px; padding: 4px 7px;"
            )
        self.btn_pause.setFixedWidth(max(30, round(34 * scale)))
        self.btn_reset.setFixedWidth(max(30, round(34 * scale)))
        # Compact layouts still fit a 1080p screen at 200% Windows scaling.
        cover_size = max(40, min(92, round(60 * scale)))
        if self.now.cover._size != cover_size:
            self.now.cover._size = cover_size
            self.now.cover.setFixedSize(cover_size, cover_size)
            if self.isVisible():
                self.now.cover.set_cover(self.now._thumb)
        self.slider.setFixedWidth(max(105, min(300, round(width * 0.13))))
        self.bright_w.setFixedWidth(max(85, round(100 * scale)))
        self.hint_lbl.setVisible(width >= 1100)
        self.bottom_layout.setContentsMargins(margin, 6, margin, max(8, round(14 * scale)))

    def _stop_transition(self) -> None:
        if self._transition is not None:
            transition, self._transition = self._transition, None
            transition.stop()
            transition.deleteLater()

    def _animate_visibility(self, entering: bool) -> None:
        self._stop_transition()
        if not self._animations_enabled:
            self._content_opacity.setOpacity(self._content_brightness)
            self._content_opacity.setEnabled(self._content_brightness < 0.999)
            self._bottom_opacity.setOpacity(1.0)
            self._bottom_opacity.setEnabled(False)
            if not entering:
                self.exitRequested.emit()
            return
        self._content_opacity.setEnabled(True)
        self._bottom_opacity.setEnabled(True)
        group = QParallelAnimationGroup(self)
        for effect, target in (
            (self._content_opacity, self._content_brightness if entering else 0.0),
            (self._bottom_opacity, 1.0 if entering else 0.0),
        ):
            animation = QPropertyAnimation(effect, b"opacity", group)
            animation.setDuration(240 if entering else 180)
            animation.setStartValue(effect.opacity())
            animation.setEndValue(target)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic if entering
                                      else QEasingCurve.Type.InCubic)
            group.addAnimation(animation)

        def finished() -> None:
            if self._transition is not group:
                return
            self._transition = None
            group.deleteLater()
            if entering:
                self._content_opacity.setOpacity(self._content_brightness)
                # Avoid a full-screen opacity buffer for later mascot updates.
                self._content_opacity.setEnabled(self._content_brightness < 0.999)
                self._bottom_opacity.setOpacity(1.0)
                self._bottom_opacity.setEnabled(False)
            else:
                self.exitRequested.emit()

        group.finished.connect(finished)
        self._transition = group
        group.start()

    def request_exit(self) -> None:
        if self._exiting or not self.isVisible():
            return
        self._exiting = True
        self._controls_timer.stop()
        self._stop_controls_animation()
        self.notes.flush()
        self._animate_visibility(False)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._exiting = False
        self._controls_hidden = False
        self.bottom.setEnabled(True)
        self.bottom.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._refresh_clock()
        self.refresh_labels(force=True)
        self.now.cover.set_cover(self.now._thumb)
        self._on_media(self.ctx.media.info)
        self._content_opacity.setOpacity(0.0 if self._animations_enabled else self._content_brightness)
        self._bottom_opacity.setOpacity(0.0 if self._animations_enabled else
                                        1.0)
        self._animate_visibility(True)
        self._wake_controls()

    def enter(self) -> None:
        self._entered_at = time.monotonic()
        self.apply_settings()
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def apply_settings(self) -> None:
        self.mascot.set_mascot(self.ctx.current_mascot())
        self.mascot.set_cursor_tracking(bool(self.ctx.config.get("follow_cursor")))
        intensity = int(self.ctx.config.get("animation_intensity"))
        self._animations_enabled = (self.ctx.config.get("decorative_animations") is not False
                                    and intensity > 0)
        self.mascot.set_animations_enabled(self._animations_enabled)
        self.mascot.set_animation_intensity(intensity)
        self.mascot.set_appearance(int(self.ctx.config.get("mascot_scale")),
                                   str(self.ctx.config.get("outline_color")),
                                   int(self.ctx.config.get("backlight_brightness")))
        if not self._animations_enabled:
            self._stop_transition()
            self._stop_controls_animation()
            self._stop_alarm_animation()
            self._content_opacity.setOpacity(self._content_brightness)
            self._content_opacity.setEnabled(self._content_brightness < 0.999)
            self._bottom_opacity.setOpacity(1.0)
            self._bottom_opacity.setEnabled(False)
            if self._flight is not None:
                self._flight.stop()
                if self._fly_widget is not None:
                    self._end_blow(self._fly_widget)
        position = self.ctx.config.get("standby_mascot_position")
        self._position = position if position in ("left", "center", "right") else "center"
        order = {"left": (self.mascot, self.left_column, self.right_column),
                 "center": (self.left_column, self.mascot, self.right_column),
                 "right": (self.left_column, self.right_column, self.mascot)}[self._position]
        for widget in (self.left_column, self.mascot, self.right_column):
            self.body.removeWidget(widget)
        for widget in order:
            self.body.addWidget(widget, 1 if widget is self.mascot else 0)
        profile = self.ctx.config.get("standby_profile")
        self._profile = profile if profile in ("classic", "minimal", "dashboard") else "classic"
        enabled_cards = self.ctx.config.get("standby_cards")
        if not isinstance(enabled_cards, list):
            enabled_cards = list(self._card_map)
        for name, card in self._card_map.items():
            card.setVisible(self._profile != "minimal" and name in enabled_cards)
        self.left_column.setVisible(self._profile != "minimal" and
                                    bool(set(enabled_cards) & {"weather", "timer"}))
        self.right_column.setVisible(self._profile != "minimal" and
                                     bool(set(enabled_cards) & {"music", "notes"}))
        self.mascot.setVisible(self._profile != "minimal")
        self.dashboard_status.setVisible(self._profile == "dashboard")
        spacer_policy = QSizePolicy.Policy.Expanding if self._profile == "minimal" \
            else QSizePolicy.Policy.Fixed
        self._top_space.changeSize(0, 0, QSizePolicy.Policy.Minimum, spacer_policy)
        self._bottom_space.changeSize(0, 0, QSizePolicy.Policy.Minimum, spacer_policy)
        self.content_layout.setStretch(0, 1 if self._profile == "minimal" else 0)
        self.content_layout.setStretch(3, 0 if self._profile == "minimal" else 1)
        self.content_layout.setStretch(4, 1 if self._profile == "minimal" else 0)
        self.content_layout.invalidate()
        self._autohide = bool(self.ctx.config.get("standby_autohide"))
        self._wake_controls()
        self.weather_city.setText(str(self.ctx.config.get("city") or ""))
        brightness = int(self.ctx.config.get("brightness"))
        if self.slider.value() != brightness:
            self.slider.blockSignals(True)
            self.slider.setValue(brightness)
            self.slider.blockSignals(False)
        self._on_brightness(brightness, save=False)
        self._update_layout()
        if self._exiting and not self._animations_enabled and self.isVisible():
            self.exitRequested.emit()

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
        self.btn_custom.setToolTip(i18n.t("timer.custom"))
        self.btn_reset.setToolTip(i18n.t("timer.reset"))
        self.btn_settings.setToolTip(i18n.t("minibar.settings"))
        self.btn_alarm.setToolTip(i18n.t("alarm.title"))
        self.btn_night.setToolTip(i18n.t("night.turn_off") if self._night else i18n.t("night.turn_on"))
        self.alarm_title.setText(i18n.t("alarm.ringing"))
        self.btn_snooze.setText(i18n.t("alarm.snooze"))
        self.btn_alarm_stop.setText(i18n.t("alarm.stop"))
        self.btn_prev.setToolTip(i18n.t("minibar.prev"))
        self.btn_play.setToolTip(i18n.t("minibar.play"))
        self.btn_next.setToolTip(i18n.t("minibar.next"))
        for button, minutes in self._preset_buttons:
            button.setToolTip(i18n.t("timer.preset", n=minutes))
        self._refresh_clock()
        self.refresh_labels(force=True)

    def refresh_labels(self, *, force: bool = False) -> None:
        if not force and not self.isVisible():
            return
        i18n, ctx = self.ctx.i18n, self.ctx
        self.weather_w.set(*weather_info(i18n, ctx.weather.last, ctx.weather_failed))
        self.weather_city.setText(str(ctx.config.get("city") or ""))
        self.timer_w.set(*timer_info(i18n, ctx.timer, ctx.alert_active))
        paused = bool(getattr(ctx.timer, "paused", False))
        self.btn_pause.setIcon(icon("play" if paused or not ctx.timer.active else "pause", 16))
        self.btn_pause.setToolTip(i18n.t("timer.pause" if ctx.timer.active else
                                         "timer.resume" if paused else "timer.start"))
        self.btn_pause.setEnabled(ctx.timer.active or paused or
                                  bool(getattr(ctx.timer, "initial_duration", 0)))
        self.btn_reset.setEnabled(bool(getattr(ctx.timer, "initial_duration", 0)))
        self.bright_w.set("sun", i18n.t("standby.brightness"))
        data = ctx.weather.last
        temp = f"{float(data['temp']):+.0f}°" if isinstance(data, dict) and isinstance(data.get("temp"), (int, float)) else "--°"
        self.mascot.set_temperature_text(temp)
        upcoming = ctx.alarms.next_time()
        self.next_alarm.setText(i18n.t("standby.next_alarm") + " · " +
                                upcoming.strftime("%d.%m %H:%M") if upcoming else
                                i18n.t("standby.no_alarm"))
        updated = getattr(ctx.weather, "last_updated", None)
        self.weather_stamp.setText(i18n.t("weather.updated", time=updated.strftime("%H:%M"))
                                   if updated is not None else
                                   i18n.t(getattr(ctx.weather, "last_error", None) or
                                          ("weather.error" if ctx.weather_failed else "weather.loading")))
        self.weather_updated.setText(self.weather_stamp.text())
        self.btn_alarm.setText(upcoming.strftime("%H:%M") if upcoming else "")
        self.btn_alarm.setToolTip(i18n.t("alarm.title") +
                                  (" · " + upcoming.strftime("%H:%M") if upcoming else ""))

    def _on_media(self, info) -> None:
        if not self.isVisible():
            return
        self.now.set_info(info)
        self.btn_play.setIcon(icon("pause" if info.playing else "play", 20))

    def _on_alert(self, on: bool) -> None:
        self.mascot.set_alert(on or self.ctx.alarms.ringing is not None)
        self._wake_controls()
        self.refresh_labels()

    def _on_brightness(self, value: int, save: bool = True) -> None:
        # Brightness affects only EyeBar content. Navigation, alarms and the
        # desktop are never painted over by a full-screen dimming widget.
        brightness = 0.25 + 0.75 * (value - 10) / 90
        self._content_brightness = brightness * (0.55 if self._night else 1.0)
        if self._transition is None:
            self._content_opacity.setOpacity(self._content_brightness)
            self._content_opacity.setEnabled(self._content_brightness < 0.999)
        if save:
            self.ctx.config.set("brightness", value, save=False)
            self._brightness_save.start()

    def set_night_mode(self, enabled: bool) -> None:
        self._night = bool(enabled)
        self.mascot.set_night_mode(enabled)
        self._on_brightness(self.slider.value(), save=False)
        self.btn_night.setToolTip(self.ctx.i18n.t("night.turn_off") if enabled else self.ctx.i18n.t("night.turn_on"))

    def show_alarm(self, alarm: dict | None) -> None:
        if alarm is None:
            return
        self.alarm_time.setText(alarm["time"])
        self.alarm_panel.move((self.width() - self.alarm_panel.width()) // 2,
                              (self.height() - self.alarm_panel.height()) // 2)
        self.alarm_panel.show()
        self.alarm_panel.raise_()
        self._wake_controls()
        self._stop_alarm_animation()
        if self._animations_enabled:
            self._alarm_opacity.setEnabled(True)
            self._alarm_opacity.setOpacity(0.0)
            animation = QPropertyAnimation(self._alarm_opacity, b"opacity", self)
            animation.setDuration(150)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.Type.OutCubic)

            def finished() -> None:
                if self._alarm_animation is animation:
                    self._alarm_animation = None
                    animation.deleteLater()
                    self._alarm_opacity.setEnabled(False)

            animation.finished.connect(finished)
            self._alarm_animation = animation
            animation.start()

    def _stop_alarm_animation(self) -> None:
        if self._alarm_animation is not None:
            animation, self._alarm_animation = self._alarm_animation, None
            animation.stop()
            animation.deleteLater()
        self._alarm_opacity.setOpacity(1.0)
        self._alarm_opacity.setEnabled(False)

    def hide_alarm(self) -> None:
        self._stop_alarm_animation()
        self.alarm_panel.hide()
        self._wake_controls()

    def _flush_brightness(self) -> None:
        if self._brightness_save.isActive():
            self._brightness_save.stop()
            self.ctx.config.save()

    # ---------- пасхалка: кота сдувает ветром ----------
    def play_blow(self) -> None:
        """Кота уносит за правый край экрана, он прилетает обратно слева (с отскоком).
        Летит «двойник» с общим состоянием — раскладка карточек при этом не дёргается."""
        if (not self.isVisible() or self._flying or not self._animations_enabled
                or not self.mascot.isVisible()):
            return
        self._flying = True
        rect = QRect(self.mascot.mapTo(self, QPoint(0, 0)), self.mascot.size())
        fly = MascotWidget(self.mascot.mascot, FORM_FULL, self.content,
                           shared_state=self.mascot.state, passive=True)
        rect.moveTopLeft(self.content.mapFrom(self, rect.topLeft()))
        fly.setGeometry(rect)
        fly.set_mascot_scale(self.ctx.config.get("mascot_scale") or 100)
        fly.show()
        fly.raise_()
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
        if self._flight is not None:
            self._flight.deleteLater()
            self._flight = None

    def hideEvent(self, e) -> None:
        self._clock_timer.stop()
        self._controls_timer.stop()
        self._stop_controls_animation()
        self._stop_alarm_animation()
        self._stop_transition()
        self._exiting = False
        self.notes.flush()
        self._flush_brightness()
        # Escape while the mascot is flying must not leave it permanently hidden.
        if self._flight is not None:
            animation, self._flight = self._flight, None
            animation.stop()
            animation.deleteLater()
            if self._fly_widget is not None:
                self._end_blow(self._fly_widget)
        super().hideEvent(e)

    # ---------- события ----------
    def resizeEvent(self, e) -> None:
        self._update_layout()
        self.bottom.raise_()  # навигация остаётся читаемой при любой яркости
        if hasattr(self, "alarm_panel"):
            self.alarm_panel.move((self.width() - self.alarm_panel.width()) // 2,
                                  (self.height() - self.alarm_panel.height()) // 2)
            self.alarm_panel.raise_()
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
        if child in (None, self.content, self.header, self.clock, self.date, self.mascot):
            self.request_exit()
