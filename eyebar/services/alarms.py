"""Persistent alarm service. Runs only inside EyeBar's Qt event loop."""
from __future__ import annotations

import math
import logging
import struct
import uuid
import wave
from datetime import datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import QApplication

from .alarm_logic import next_alarm_time, normalize_audio, sanitize_alarms, should_ring, valid_time
from ..paths import user_data_dir


class AlarmEngine(QObject):
    ringingChanged = pyqtSignal(bool)
    changed = pyqtSignal()
    audioWarning = pyqtSignal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.alarms = sanitize_alarms(config.get("alarms"))
        self.ringing: dict | None = None
        self._queue: list[dict] = []
        self._snoozes: list[tuple[datetime, dict]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._sound_timer = QTimer(self)
        self._sound_timer.setInterval(1200)
        self._sound_timer.timeout.connect(QApplication.beep)
        self._sound_playing = False
        self._sound_effect = None
        self._audio_watchdog = QTimer(self)
        self._audio_watchdog.setSingleShot(True)
        self._audio_watchdog.setInterval(4000)
        self._audio_watchdog.timeout.connect(lambda: self._fallback_sound("WAV loading timed out"))
        self.audio_mode = "silent"
        self.audio_warning = ""

    def start(self) -> None:
        self._timer.start()
        self._tick()

    def stop(self) -> None:
        self._timer.stop()
        self._stop_sound()

    def save(self) -> bool:
        self.config.data["alarms"] = sanitize_alarms(self.alarms)
        ok = self.config.save()
        self.changed.emit()
        return ok

    def put(self, alarm_id: str | None, time_text: str, days: list[int], enabled: bool = True,
            *, sound: str | None = None, volume: int | None = None,
            sound_path: str | None = None) -> bool:
        if not valid_time(time_text):
            return False
        clean_days = sorted(set(d for d in days if type(d) is int and 0 <= d < 7))
        target = next((a for a in self.alarms if a["id"] == alarm_id), None)
        if target is None:
            if len(self.alarms) >= 40:
                return False
            target = {"id": uuid.uuid4().hex, "last_date": ""}
            self.alarms.append(target)
        # When changing the time, a new occurrence is eligible even on the same day.
        if target.get("time") != time_text:
            target["last_date"] = ""
        target.update(time=time_text, days=clean_days, enabled=bool(enabled))
        target.update(normalize_audio(
            target.get("sound", "default") if sound is None else sound,
            target.get("volume", 80) if volume is None else volume,
            target.get("sound_path", "") if sound_path is None else sound_path))
        return self.save()

    def remove(self, alarm_id: str) -> None:
        self.alarms = [a for a in self.alarms if a["id"] != alarm_id]
        self._queue = [a for a in self._queue if a["id"] != alarm_id]
        self._snoozes = [(when, a) for when, a in self._snoozes if a["id"] != alarm_id]
        if self.ringing is not None and self.ringing["id"] == alarm_id:
            self.stop_ringing()
        self.save()

    def set_enabled(self, alarm_id: str, enabled: bool) -> None:
        alarm = next((a for a in self.alarms if a["id"] == alarm_id), None)
        if alarm is not None:
            alarm["enabled"] = bool(enabled)
            self.save()

    def next_time(self) -> datetime | None:
        now = datetime.now()
        scheduled = next_alarm_time(self.alarms, now)
        candidates = [when for when, _alarm in self._snoozes if when > now]
        if scheduled is not None:
            candidates.append(scheduled)
        return min(candidates) if candidates else None

    def _tick(self) -> None:
        now = datetime.now()
        any_changed = False
        for alarm in self.alarms:
            if should_ring(alarm, now):
                alarm["last_date"] = now.date().isoformat()
                if not alarm["days"]:  # no weekdays = one-shot alarm
                    alarm["enabled"] = False
                self._queue.append(dict(alarm))
                any_changed = True
        if any_changed:
            self.save()
        pending = [(when, a) for when, a in self._snoozes if when <= now]
        self._snoozes = [(when, a) for when, a in self._snoozes if when > now]
        self._queue.extend(a for _, a in pending)
        if pending:
            self.changed.emit()
        self._start_next()

    def _start_next(self) -> None:
        if self.ringing is not None or not self._queue:
            return
        self.ringing = self._queue.pop(0)
        self._start_sound()
        self.ringingChanged.emit(True)

    def snooze(self, minutes: int = 5) -> None:
        if self.ringing is None:
            return
        alarm = self.ringing
        self._snoozes.append((datetime.now() + timedelta(minutes=max(1, minutes)), dict(alarm)))
        self.stop_ringing()
        self.changed.emit()

    def stop_ringing(self) -> None:
        if self.ringing is None:
            return
        self._stop_sound()
        self.ringing = None
        self.ringingChanged.emit(False)
        self._start_next()

    @staticmethod
    def _tone_path(sound: str = "default"):
        soft = sound == "soft"
        path = user_data_dir() / ("alarm_soft.wav" if soft else "alarm.wav")
        try:
            with wave.open(str(path), "rb") as existing:
                if existing.getnframes() > 8000:
                    return path
        except (OSError, wave.Error, EOFError):
            pass
        rate = 22050
        temporary = path.with_suffix(".tmp.wav")
        with wave.open(str(temporary), "wb") as wf:
            wf.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            chunk = bytearray()
            for i in range(int(1.4 * rate)):
                t = i / rate
                phase = t % 0.7
                frequency = (440 if t < 0.7 else 550) if soft else (720 if t < 0.7 else 960)
                amplitude = ((0.13 if soft else 0.21) * math.sin(2 * math.pi * frequency * t)
                             if phase < 0.4 else 0.0)
                ramp = min(1.0, phase / 0.018, max(0, (0.4 - phase) / 0.04))
                chunk.extend(struct.pack("<h", int(32767 * amplitude * ramp)))
            wf.writeframes(chunk)
        temporary.replace(path)
        return path

    def _warn_audio(self, message: str) -> None:
        self.audio_warning = message
        logging.getLogger("eyebar.alarms").warning(message)
        try:
            with (user_data_dir() / "eyebar.log").open("a", encoding="utf-8") as log:
                log.write(f"{datetime.now().isoformat(timespec='seconds')} [alarm audio] {message}\n")
        except OSError:
            pass
        self.audioWarning.emit(message)

    def _selected_sound_path(self, alarm: dict) -> Path:
        if alarm.get("sound") == "custom":
            try:
                candidate = Path(alarm.get("sound_path", ""))
                # Only local, explicitly chosen PCM WAV files are accepted.
                if candidate.is_absolute() and candidate.suffix.lower() == ".wav":
                    with wave.open(str(candidate), "rb") as custom:
                        if custom.getnframes() > 0 and 1 <= custom.getnchannels() <= 2:
                            return candidate
            except (OSError, ValueError, wave.Error, EOFError):
                pass
            self._warn_audio("Custom alarm WAV is unavailable or invalid; using the default sound")
        return self._tone_path(alarm.get("sound", "default"))

    def _make_sound_effect(self):
        # Optional at runtime: old PyQt installations may lack multimedia
        # libraries. The normal UI and alarm scheduling do not depend on them.
        from PyQt6.QtMultimedia import QMediaDevices, QSoundEffect
        if not QMediaDevices.audioOutputs():
            raise RuntimeError("No audio output device is available")
        return QSoundEffect(self)

    def _start_sound(self) -> None:
        self._stop_sound()
        self.audio_warning = ""
        alarm = self.ringing or {}
        volume = normalize_audio(volume=alarm.get("volume", 80))["volume"]
        if volume == 0:
            return
        try:
            path = self._selected_sound_path(alarm)
            effect = self._make_sound_effect()
            self._sound_effect = effect
            self.audio_mode = "qt"
            effect.setLoopCount(effect.Loop.Infinite.value)
            effect.setVolume(volume / 100.0)
            effect.statusChanged.connect(lambda: self._audio_status_changed(effect))
            self._audio_watchdog.start()
            effect.setSource(QUrl.fromLocalFile(str(path)))
            if self._sound_effect is not effect:
                return
            effect.play()
            self._sound_playing = True
            self._audio_status_changed(effect)
        except (ImportError, OSError, RuntimeError, ValueError, wave.Error) as exc:
            self._fallback_sound(str(exc))

    def _audio_status_changed(self, effect) -> None:
        if self._sound_effect is not effect or self.audio_mode != "qt":
            return
        if effect.status() == effect.Status.Error:
            self._fallback_sound("The audio backend could not load or play the alarm WAV")
        elif effect.status() == effect.Status.Ready:
            self._audio_watchdog.stop()

    def _fallback_sound(self, reason: str) -> None:
        if self.ringing is None or self.audio_mode == "system":
            return
        self._stop_sound()
        if self.ringing.get("volume", 80) == 0:
            return
        self.audio_mode = "system"
        self._warn_audio(f"Alarm uses the system beep; its volume cannot be controlled by EyeBar: {reason}")
        QApplication.beep()
        self._sound_timer.start()
        self._sound_playing = True

    def _stop_sound(self) -> None:
        self._sound_timer.stop()
        self._audio_watchdog.stop()
        effect, self._sound_effect = self._sound_effect, None
        if effect is not None:
            effect.stop()
            effect.deleteLater()
        self.audio_mode = "silent"
        self._sound_playing = False
