"""Общие виджеты: анимированный талисман, плеер, заметки, подписи с иконками."""
from __future__ import annotations

import logging
import math
import random
import time
from datetime import datetime
from uuid import uuid4

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, Qt, QVariantAnimation
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from ..mascots.base import FORM_FULL, LOGICAL_H, LOGICAL_W, Mascot, MascotState
from ..services.timer import format_seconds
from ..services.weather import describe
from .icons import ACCENT, ALERT, ICON, pixmap


class MascotWidget(QWidget):
    """Paint a mascot, with finite gestures and no frame timer while resting.

    The minute clock is independent of decorations. A low-rate frame timer runs
    only for moving weather, music, alerts, or a visible passive flight copy.
    Hidden widgets stop every timer and animation; their state is refreshed on
    the next show. ``passive`` copies never mutate their owner's shared state.
    """

    def __init__(self, mascot: Mascot, form: str, parent=None, *,
                 shared_state: MascotState | None = None, passive: bool = False) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.mascot = mascot
        self.form = form
        self.passive = passive
        self.paint_enabled = True
        self.state = shared_state if shared_state is not None else MascotState()
        self._night = False
        self._animations_enabled = True
        self._animation_intensity = 100
        self._mascot_scale = 100
        self._mascot_opacity = 1.0
        self._previous_mascot: Mascot | None = None
        self._follow_cursor = True
        self._timer_reacting = False
        self._umbrella_target = self._rain_target = self._wind_target = 0.0
        self._last = time.monotonic()
        self._animations: dict[str, QVariantAnimation] = {}
        self._cursor_target: tuple[float, float] | None = None
        self._gesture_index = 0

        self._timer = QTimer(self)
        self._timer.setInterval(66)  # 15 FPS, only while a scene actually moves.
        self._timer.timeout.connect(self._tick)
        self._clock_timer = QTimer(self)
        self._clock_timer.setSingleShot(True)
        self._clock_timer.timeout.connect(self._update_clock)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(160)
        self._cursor_timer.timeout.connect(self._poll_cursor)
        self._blink_timer = QTimer(self)
        self._blink_timer.setSingleShot(True)
        self._blink_timer.timeout.connect(self._blink)
        self._gesture_timer = QTimer(self)
        self._gesture_timer.setSingleShot(True)
        self._gesture_timer.timeout.connect(self._idle_gesture)

    # ---------- public controls ----------
    def set_mascot(self, mascot: Mascot) -> None:
        if self.mascot.id == mascot.id:
            self.mascot = mascot
            self._repaint()
            return
        self._cancel_swap()
        self._previous_mascot, self.mascot = self.mascot, mascot
        self._mascot_opacity = 0.0

        def change(progress: float) -> None:
            self._mascot_opacity = progress

        def done() -> None:
            self._previous_mascot = None
            self._mascot_opacity = 1.0

        self._animate("swap", 180, change, finished=done)

    def set_animation_intensity(self, percent: int) -> None:
        """Scale decorative amplitude/frequency; zero stops all decoration."""
        percent = max(0, min(100, int(percent)))
        if self._animation_intensity == percent:
            return
        self._animation_intensity = percent
        self._stop_animations()
        self._settle_state()
        self._cursor_timer.setInterval(int(160 + 240 * (1 - percent / 100)))
        self._blink_timer.stop()
        self._gesture_timer.stop()
        self._sync_activity()
        self._repaint()

    def set_appearance(self, scale: int, outline_color: str, backlight: int) -> None:
        """Apply safe canvas scale and renderer appearance without moving windows.

        120% fills the canvas. The default 100% leaves room for growth, so the
        whole 80–120% range is useful without clipping ears, paws or the tail.
        """
        self._mascot_scale = max(80, min(120, int(scale)))
        color = QColor(outline_color)
        if color.isValid():
            self.state.outline_color = color.name()
        self.state.backlight = max(0, min(100, int(backlight))) / 100.0
        self._repaint()

    def set_mascot_scale(self, percent: int) -> None:
        self.set_appearance(percent, self.state.outline_color,
                            round(self.state.backlight * 100))

    def set_animations_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._animations_enabled == enabled:
            return
        self._animations_enabled = enabled
        self._stop_animations()
        self._settle_state()
        self._sync_activity()
        self._repaint()

    def set_night_mode(self, enabled: bool) -> None:
        self._night = bool(enabled)
        self._transition_sleep()
        self._sync_activity()

    def set_alert(self, on: bool) -> None:
        on = bool(on)
        if self.state.alert == on:
            return
        self.state.alert = on
        if on:
            self._timer_reacting = False
            for key in ("blink", "gesture", "reaction"):
                self._cancel_animation(key)
            self.state.blink = 1.0
            self.state.yawn = self.state.stretch = self.state.bob = 0.0
            self.state.glow = 1.0
        else:
            self.state.glow = 1.0 - 0.4 * self._sleep_target()
            self.state.pulse = 0.4
            if self.state.wind < 0.01:
                self.state.tail = self.state.tail2 = 0.0
        self._transition_sleep()
        self._sync_activity()
        self._repaint()

    def set_emotion(self, name: str) -> None:
        if self.state.emotion == name:
            return
        self.state.emotion = name
        self.state.bob = 0.0
        self._cursor_target = None
        self._transition_sleep()
        self._sync_activity()
        self._repaint()

    def set_cursor_tracking(self, enabled: bool) -> None:
        self._follow_cursor = bool(enabled)
        self._cursor_target = None
        self._sync_activity()
        if not enabled:
            self._move_eyes(0.0, 0.0)

    def set_music_accessory(self, accessory: str) -> None:
        if self.state.music_accessory != accessory:
            self.state.music_accessory = accessory
            self._repaint()

    def set_temperature_text(self, text: str) -> None:
        if self.state.temp_text != text:
            self.state.temp_text = text
            self._repaint()

    def set_weather(self, rain_mode: str, windy: bool) -> None:
        """Ease into a weather scene; a clear scene stops its frame timer."""
        targets = (1.0 if rain_mode == "umbrella" else 0.0,
                   1.0 if rain_mode in ("umbrella", "wet") else 0.0,
                   1.0 if windy else 0.0)
        old = (self._umbrella_target, self._rain_target, self._wind_target)
        if old == targets:
            return
        self._umbrella_target, self._rain_target, self._wind_target = targets
        starts = (self.state.umbrella, self.state.rain, self.state.wind)

        def change(progress: float) -> None:
            for attr, a, b in zip(("umbrella", "rain", "wind"), starts, targets):
                setattr(self.state, attr, a + (b - a) * progress)

        self._animate("weather", 650, change, finished=self._sync_dynamic_timer)
        self._sync_activity()

    def react_to_timer(self) -> None:
        """A short acknowledgement of a real countdown start, then rest."""
        if self.passive or self.state.alert or not self._can_animate():
            return
        self._timer_reacting = True
        self._cancel_animation("gesture")
        self._cancel_animation("blink")
        self.state.yawn = 0.0
        self.state.blink = 1.0
        self._transition_sleep()

        def change(progress: float) -> None:
            wave = math.sin(math.pi * progress) ** 2 * self._amplitude()
            self.state.bob = 3.8 * wave
            self.state.stretch = 0.22 * wave
            self.state.tail = 0.45 * math.sin(progress * 2 * math.pi) * self._amplitude()
            self.state.tail2 = 0.35 * math.sin(progress * 2 * math.pi - 0.5) * wave
            self.state.pulse = wave

        def done() -> None:
            self._timer_reacting = False
            self.state.bob = self.state.stretch = 0.0
            self.state.tail = self.state.tail2 = 0.0
            self._transition_sleep()
            self._sync_activity()

        self._animate("reaction", 1250, change, finished=done)

    # ---------- lifecycle and scheduling ----------
    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._last = time.monotonic()
        if not self.passive:
            self._settle_state()
        self._sync_activity()

    def hideEvent(self, e) -> None:
        for timer in self._all_timers():
            timer.stop()
        self._stop_animations()
        if not self.passive:
            self._settle_state()
        super().hideEvent(e)

    def _all_timers(self) -> tuple[QTimer, ...]:
        return (self._timer, self._clock_timer, self._cursor_timer,
                self._blink_timer, self._gesture_timer)

    def _decorations_enabled(self) -> bool:
        return self._animations_enabled and self._animation_intensity > 0

    def _can_animate(self) -> bool:
        return self.isVisible() and self._decorations_enabled() and not self.passive

    def _amplitude(self) -> float:
        return self._animation_intensity / 100.0

    def _idle_delay(self, minimum: int, maximum: int) -> int:
        # Lower intensity spaces gestures out as well as reducing their size.
        return round(random.randint(minimum, maximum) * (1 + 2.5 * (1 - self._amplitude())))

    def _sleep_target(self) -> float:
        return float((self._night or self.state.emotion == "sleepy")
                     and not self.state.alert and not self._timer_reacting)

    def _repaint(self) -> None:
        if self.isVisible() and self.paint_enabled:
            self.update()

    def _settle_state(self) -> None:
        if self.passive:
            return
        self._timer_reacting = False
        st = self.state
        st.sleep_phase = self._sleep_target()
        st.blink = 1.0 if st.alert else 1.0 - 0.83 * st.sleep_phase
        st.yawn = st.stretch = st.bob = st.breath = 0.0
        st.tail = st.tail2 = 0.0
        st.pulse = 0.4
        st.glow = 1.0 if st.alert else 1.0 - 0.4 * st.sleep_phase
        st.umbrella, st.rain, st.wind = (self._umbrella_target,
                                        self._rain_target, self._wind_target)
        self._cursor_target = None

    def _sync_activity(self) -> None:
        if not self.isVisible():
            return
        if self.passive:
            self._timer.setInterval(33)
            self._timer.start()
            return
        self._update_clock()
        active = self._decorations_enabled()
        watching = active and self._follow_cursor and not self._sleep_target() and \
            self.state.emotion not in ("angry", "sleepy", "sad")
        if watching:
            if not self._cursor_timer.isActive():
                self._cursor_timer.start()
                self._poll_cursor()
        else:
            self._cursor_timer.stop()
            self._move_eyes(0.0, 0.0)
        if active and not self.state.alert:
            if not self._blink_timer.isActive() and not self._sleep_target():
                self._blink_timer.start(self._idle_delay(2800, 6200))
            elif self._sleep_target():
                self._blink_timer.stop()
            if not self._gesture_timer.isActive():
                self._gesture_timer.start(self._idle_delay(8000, 15000))
        else:
            self._blink_timer.stop()
            self._gesture_timer.stop()
        self._sync_dynamic_timer()

    def _sync_dynamic_timer(self) -> None:
        moving = self.passive or (self._decorations_enabled() and
                 (self.state.alert or self.state.emotion in ("happy", "dancing") or
                  max(self.state.rain, self.state.wind, self._rain_target,
                      self._wind_target) > 0.001))
        if self.isVisible() and moving:
            interval = 33 if self.passive else (100 if self._night else 66)
            self._timer.setInterval(interval)
            if not self._timer.isActive():
                self._last = time.monotonic()
                self._timer.start()
        else:
            self._timer.stop()

    def _update_clock(self) -> None:
        if self.passive or not self.isVisible():
            return
        now = datetime.now()
        hh, mm = f"{now.hour:02d}", f"{now.minute:02d}"
        if (hh, mm) != (self.state.hh, self.state.mm):
            self.state.hh, self.state.mm = hh, mm
            self._repaint()
        # Wake just after the minute boundary, independent of animation settings.
        self._clock_timer.start(max(20, int((60 - now.second - now.microsecond / 1e6) * 1000) + 20))

    # ---------- finite Qt animations ----------
    def _cancel_animation(self, key: str) -> None:
        animation = self._animations.pop(key, None)
        if animation is not None:
            animation.stop()
            animation.deleteLater()

    def _cancel_swap(self) -> None:
        self._cancel_animation("swap")
        self._previous_mascot = None
        self._mascot_opacity = 1.0

    def _stop_animations(self) -> None:
        for key in tuple(self._animations):
            self._cancel_animation(key)
        self._previous_mascot = None
        self._mascot_opacity = 1.0

    def _animate(self, key: str, duration: int, change, *, finished=None,
                 curve=QEasingCurve.Type.InOutSine) -> None:
        self._cancel_animation(key)
        if not self._can_animate():
            if not self.passive:
                change(1.0)
                self._repaint()
                if finished is not None:
                    finished()
            return
        animation = QVariantAnimation(self)
        animation.setDuration(duration)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(curve)
        self._animations[key] = animation

        def advance(value) -> None:
            change(float(value))
            self._repaint()

        def done() -> None:
            if self._animations.get(key) is animation:
                self._animations.pop(key)
            animation.deleteLater()
            if finished is not None:
                finished()
            self._repaint()

        animation.valueChanged.connect(advance)
        animation.finished.connect(done)
        animation.start()

    def _transition_sleep(self) -> None:
        start, end = self.state.sleep_phase, self._sleep_target()
        self._cancel_animation("sleep")
        if start == end:
            self._repaint()
            return
        self._cancel_animation("blink")
        self.state.yawn = 0.0

        def change(progress: float) -> None:
            self.state.sleep_phase = start + (end - start) * progress
            self.state.blink = 1.0 if self.state.alert else 1.0 - 0.83 * self.state.sleep_phase
            self.state.glow = 1.0 if self.state.alert else 1.0 - 0.4 * self.state.sleep_phase

        self._animate("sleep", 1300 if end else 850, change)

    def _blink(self) -> None:
        if not self._can_animate() or self.state.alert or self._sleep_target():
            return
        baseline = 1.0 - 0.83 * self.state.sleep_phase

        def change(progress: float) -> None:
            self.state.blink = baseline * (1.0 - self._amplitude() * (1.0 - abs(1.0 - 2.0 * progress)))

        self._animate("blink", 190, change, curve=QEasingCurve.Type.Linear)
        self._blink_timer.start(self._idle_delay(2800, 6200))

    def _idle_gesture(self) -> None:
        if not self._can_animate() or self.state.alert:
            return
        if "reaction" in self._animations:
            self._gesture_timer.start(9000)
            return
        # Alternate quiet gestures, with irregular spacing. Sleeping mascots
        # yawn or breathe; awake mascots stretch or move their tail.
        self._gesture_index = (self._gesture_index + 1) % 3
        kind = ("yawn", "breath", "tail")[self._gesture_index] if self._sleep_target() \
            else ("stretch", "tail", "breath")[self._gesture_index]

        def change(progress: float) -> None:
            wave = math.sin(math.pi * progress) ** 2 * self._amplitude()
            if kind == "tail":
                self.state.tail = 0.5 * math.sin(2 * math.pi * progress) * wave
                self.state.tail2 = 0.45 * math.sin(2 * math.pi * progress - 0.7) * wave
            else:
                setattr(self.state, kind, wave)

        def done() -> None:
            self.state.yawn = self.state.stretch = self.state.breath = 0.0
            if not self.state.alert and self.state.wind < 0.01:
                self.state.tail = self.state.tail2 = 0.0

        self._animate("gesture", 2400 if kind == "yawn" else 2100, change, finished=done)
        self._gesture_timer.start(self._idle_delay(12000, 24000))

    def _poll_cursor(self) -> None:
        centre = self.mapToGlobal(self.rect().center())
        cur = QCursor.pos()
        dx, dy = cur.x() - centre.x(), cur.y() - centre.y()
        dist = math.hypot(dx, dy)
        strength = min(1.0, dist / 250.0) * self._amplitude()
        target = (round(dx / dist * strength, 3), round(dy / dist * strength, 3)) \
            if dist else (0.0, 0.0)
        if target != self._cursor_target:
            self._cursor_target = target
            self._move_eyes(*target)

    def _move_eyes(self, dx: float, dy: float) -> None:
        starts = self.state.eye_dx, self.state.eye_dy
        if abs(starts[0] - dx) + abs(starts[1] - dy) < 0.002:
            return

        def change(progress: float) -> None:
            self.state.eye_dx = starts[0] + (dx - starts[0]) * progress
            self.state.eye_dy = starts[1] + (dy - starts[1]) * progress

        self._animate("eyes", 180, change)

    def _tick(self) -> None:
        if not self.isVisible() or (not self.passive and not self._decorations_enabled()):
            return
        if self.passive:
            self._repaint()
            return
        now = time.monotonic()
        dt = min(0.2, max(0.0, now - self._last))
        self._last = now
        st = self.state
        st.t += dt * (1.0 if st.alert else 0.5 + 0.5 * self._amplitude())
        if st.alert or st.wind > 0.01:
            phase = st.t * (7.0 if st.alert else 5.0)
            amount = 1.0 if st.alert else self._amplitude()
            st.tail = math.sin(phase) * (0.6 if st.alert else 0.45) * amount
            st.tail2 = math.sin(phase - 0.9) * 0.5 * amount
        if st.alert:
            st.glow = 0.7 + 0.3 * abs(math.sin(st.t * 6))
            st.pulse = abs(math.sin(st.t * 3))
            st.blink = 1.0
        if st.emotion in ("happy", "dancing") and not st.alert and not self._timer_reacting:
            st.bob = abs(math.sin(st.t * (7 if st.emotion == "dancing" else 4))) * \
                (4.0 if st.emotion == "dancing" else 1.7) * self._amplitude()
        self._repaint()

    def paintEvent(self, e) -> None:
        if not self.paint_enabled:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        scale = min(self.width() / LOGICAL_W, self.height() / LOGICAL_H) * self._mascot_scale / 120.0
        p.translate((self.width() - LOGICAL_W * scale) / 2, (self.height() - LOGICAL_H * scale) / 2)
        p.scale(scale, scale)
        opacity = 1.0 if self.state.alert else 1.0 - 0.23 * self.state.sleep_phase

        def draw(mascot: Mascot, alpha: float) -> None:
            p.save()
            p.setOpacity(opacity * alpha)
            if mascot.id not in ("cyber_cat", "classic_blue"):
                # Existing renderers keep their shapes and gain a subtle,
                # grounded stretch from the shared gesture state.
                amount = 0.025 * self.state.stretch + 0.012 * self.state.yawn
                if amount:
                    p.translate(LOGICAL_W / 2, LOGICAL_H - 9)
                    p.scale(1.0 + amount * 0.45, 1.0 - amount)
                    p.translate(-LOGICAL_W / 2, -(LOGICAL_H - 9))
            mascot.paint(p, self.form, self.state)
            p.restore()

        if self._previous_mascot is not None and self._mascot_opacity < 1.0:
            draw(self._previous_mascot, 1.0 - self._mascot_opacity)
        draw(self.mascot, self._mascot_opacity)
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
        self._last_attempted: str | None = None
        self.recovery_path = None
        self._dirty = False
        self.setPlainText(self._last_saved)
        self._save = QTimer(self)
        self._save.setSingleShot(True)
        self._save.setInterval(600)
        self._save.timeout.connect(self.flush)
        self.textChanged.connect(self._on_text_changed)
        ctx.i18n.changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self) -> None:
        self.setPlaceholderText(self.ctx.i18n.t("notes.placeholder"))

    def _on_text_changed(self) -> None:
        self._dirty = True
        self._save.start()

    def _sync_from_config(self) -> None:
        if self._dirty or self._save.isActive():
            return  # unsaved local edit, including a failed write, takes precedence
        saved = str(self.ctx.config.get("notes"))
        if saved != self._last_saved:
            if saved != self.toPlainText():
                self.blockSignals(True)
                try:
                    self.setPlainText(saved)
                finally:
                    self.blockSignals(False)
            self._last_saved = saved
            self._last_attempted = None

    def _save_conflict(self, value: str) -> bool:
        """Keep both edits without replacing a newer canonical note.

        The main notes format stays a string. Conflicting text is a separate
        UTF-8 file next to config.json, committed with the existing atomic
        writer. Failed recovery writes leave this document dirty for retry.
        """
        cfg = self.ctx.config
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = cfg.path.with_name(f"notes-recovery-{stamp}-{uuid4().hex[:12]}.txt")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            cfg._atomic_write(path, value.encode("utf-8"))
        except (OSError, UnicodeError) as exc:
            cfg._log(logging.ERROR, "EyeBar: could not preserve conflicting notes", exc)
            self.setToolTip(self.ctx.i18n.t("notes.recovery_failed"))
            return False
        self.recovery_path = path
        self._last_saved = value
        self._last_attempted = None
        self._dirty = False
        message = self.ctx.i18n.t("notes.conflict_saved", path=str(path))
        if str(path) not in message:
            message += "\n" + str(path)
        self.setToolTip(message)
        self.setAccessibleDescription(message)
        cfg._log(logging.WARNING, f"EyeBar: conflicting notes preserved in {path}")
        return True

    def flush(self) -> bool:
        self._save.stop()
        if not self._dirty:
            # A clean editor must not overwrite a newer edit made in the other
            # notes window when both windows are flushed during shutdown.
            self._sync_from_config()
            return True
        value = self.toPlainText()
        current = str(self.ctx.config.get("notes"))
        # A failed write already changes Config's in-memory value. Recognise
        # that editor's own attempt on retry, but never overwrite a distinct
        # text saved by the other window in the meantime.
        if current not in (self._last_saved, self._last_attempted, value):
            return self._save_conflict(value)
        self.ctx.config.set("notes", value, save=False)
        self._last_attempted = value
        if not self.ctx.config.save():
            # Config records the failure in the local log. Keep the document
            # dirty and retry on the next edit, focus loss, or shutdown flush;
            # no recurring retry timer or repeated error dialogs are created.
            return False
        self._last_saved = value
        self._last_attempted = None
        self._dirty = False
        self.recovery_path = None
        self.setToolTip("")
        self.setAccessibleDescription("")
        return True

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
        self.status = ElidedLabel()
        self.status.setObjectName("muted")
        self.status.setStyleSheet("font-size: 10px;")
        for label in (self.title, self.artist, self.status):
            label.setTextFormat(Qt.TextFormat.PlainText)
        col = QVBoxLayout()
        col.setSpacing(1)
        col.addStretch(1)
        col.addWidget(self.title)
        col.addWidget(self.artist)
        col.addWidget(self.status)
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
        available = bool(self.ctx.media.backend_ok and info.available)
        if available:
            title = str(info.title or "").strip()
            artist = str(info.artist or info.album or "").strip()
            if not title and not artist:
                title = t("media.no_metadata")
            elif not title:
                title = t("media.unknown_track")
            status = t("media.playing" if info.playing else "media.paused")
        else:
            title = t("media.nothing" if self.ctx.media.backend_ok else "media.unavailable")
            artist = status = ""
        self.title.setText(title)
        self.artist.setText(artist)
        self.artist.setVisible(bool(artist))
        self.status.setText(status)
        self.status.setVisible(bool(status))
        for label, full in ((self.title, title), (self.artist, artist), (self.status, status)):
            label.setAccessibleName(full)
        summary = "\n".join(part for part in (title, artist, status) if part)
        self.setToolTip(summary)
        self.setAccessibleName(summary)
        thumb = info.thumb if available else None
        if thumb != self._thumb:
            self._thumb = thumb
            self.cover.set_cover(thumb)


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
    if timer.active or getattr(timer, "paused", False) or getattr(timer, "state", "") == "ready":
        text = format_seconds(timer.remaining())
        if getattr(timer, "paused", False):
            text += " · " + i18n.t("timer.paused")
        return "timer", text, ACCENT
    return "timer", "--:--", ICON
