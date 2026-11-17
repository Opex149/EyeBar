"""Alarm audio preferences and backend fallback without playing real sound."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from eyebar.services.alarm_logic import normalize_audio, sanitize_alarms


class AlarmAudioValidationTests(unittest.TestCase):
    def test_old_alarm_gets_defaults_and_invalid_audio_is_safe(self):
        old = dict(id="wake", time="07:15", days=[1, 2], enabled=True)
        normalized = sanitize_alarms([old])[0]
        self.assertEqual(normalized["sound"], "default")
        self.assertEqual(normalized["volume"], 80)
        self.assertEqual(normalized["sound_path"], "")
        self.assertEqual(normalize_audio([], True, "bad\x00path"),
                         dict(sound="default", volume=80, sound_path=""))
        self.assertEqual(normalize_audio("soft", 200, "/private/file.wav"),
                         dict(sound="soft", volume=100, sound_path=""))
        self.assertEqual(normalize_audio("custom", -1, "/tmp/chime.wav"),
                         dict(sound="custom", volume=0, sound_path="/tmp/chime.wav"))


class FakeSignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self):
        for callback in self.callbacks:
            callback()


class FakeEffect:
    Loop = SimpleNamespace(Infinite=SimpleNamespace(value=-2))
    Status = SimpleNamespace(Ready="ready", Loading="loading", Error="error")

    def __init__(self):
        self.statusChanged = FakeSignal()
        self.current_status = self.Status.Ready
        self.setLoopCount = Mock()
        self.setVolume = Mock()
        self.setSource = Mock()
        self.play = Mock()
        self.stop = Mock()
        self.deleteLater = Mock()

    def status(self):
        return self.current_status


@unittest.skipUnless(importlib.util.find_spec("PyQt6"), "PyQt6 is not installed")
class AlarmAudioBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from eyebar.config import Config
        from eyebar.services.alarms import AlarmEngine
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"
        self.config = Config(self.path)
        self.engine = AlarmEngine(self.config)
        self.data_dir_patch = patch("eyebar.services.alarms.user_data_dir", return_value=Path(self.tmp.name))
        self.data_dir_patch.start()

    def tearDown(self):
        self.engine.stop()
        self.engine.deleteLater()
        self.app.processEvents()
        self.data_dir_patch.stop()
        self.tmp.cleanup()

    def test_audio_options_persist_and_legacy_edits_preserve_them(self):
        from eyebar.config import Config
        self.assertTrue(self.engine.put(None, "06:45", [0, 2], sound="custom",
                                        sound_path="C:/Sounds/chime.wav", volume=31))
        identity = self.engine.alarms[0]["id"]
        self.assertTrue(self.engine.put(identity, "07:00", [1], enabled=False))
        alarm = Config(self.path).get("alarms")[0]
        self.assertEqual(alarm["sound"], "custom")
        self.assertEqual(alarm["sound_path"], "C:/Sounds/chime.wav")
        self.assertEqual(alarm["volume"], 31)
        self.assertEqual(alarm["time"], "07:00")
        self.assertFalse(alarm["enabled"])

    def test_qt_sound_receives_real_volume_and_stops_on_snooze(self):
        self.engine.ringing = dict(id="wake", time="07:00", volume=37, sound="soft")
        effect = FakeEffect()
        with patch.object(self.engine, "_selected_sound_path", return_value=Path(self.tmp.name)/"tone.wav"), \
             patch.object(self.engine, "_make_sound_effect", return_value=effect), \
             patch("eyebar.services.alarms.QApplication.beep") as beep:
            self.engine._start_sound()
            effect.setVolume.assert_called_once_with(0.37)
            effect.setLoopCount.assert_called_once_with(-2)
            effect.play.assert_called_once()
            self.assertEqual(self.engine.audio_mode, "qt")
            self.assertFalse(self.engine._audio_watchdog.isActive())
            self.assertFalse(beep.called)
            self.engine.snooze()
            effect.stop.assert_called_once()
            effect.deleteLater.assert_called_once()
            self.assertIsNone(self.engine.ringing)
            self.assertEqual(len(self.engine._snoozes), 1)
            self.assertFalse(self.engine._sound_timer.isActive())

    def test_zero_volume_mutes_even_without_multimedia(self):
        self.engine.ringing = dict(id="silent", time="07:00", volume=0)
        with patch.object(self.engine, "_make_sound_effect") as make_sound, \
             patch("eyebar.services.alarms.QApplication.beep") as beep:
            self.engine._start_sound()
            make_sound.assert_not_called()
            beep.assert_not_called()
            self.assertEqual(self.engine.audio_mode, "silent")
            self.assertFalse(self.engine._sound_timer.isActive())
            self.assertFalse(self.engine._audio_watchdog.isActive())

    def test_missing_custom_sound_falls_back_to_default_wav(self):
        fallback = Path(self.tmp.name) / "default.wav"
        with patch.object(self.engine, "_tone_path", return_value=fallback) as tone, \
             self.assertLogs("eyebar.alarms", level="WARNING"):
            selected = self.engine._selected_sound_path(
                dict(sound="custom", sound_path=str(Path(self.tmp.name)/"missing.wav")))
        self.assertEqual(selected, fallback)
        tone.assert_called_once_with("custom")
        self.assertIn("unavailable", self.engine.audio_warning)

    def test_valid_custom_wav_is_used(self):
        custom = Path(self.tmp.name) / "my-sound.wav"
        with wave.open(str(custom), "wb") as wav:
            wav.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x00\x00" * 100)
        selected = self.engine._selected_sound_path(dict(sound="custom", sound_path=str(custom)))
        self.assertEqual(selected, custom)

    def test_backend_failure_warns_once_and_uses_system_volume(self):
        self.engine.ringing = dict(id="wake", time="07:00", volume=20)
        with patch.object(self.engine, "_selected_sound_path", return_value=Path(self.tmp.name)/"tone.wav"), \
             patch.object(self.engine, "_make_sound_effect", side_effect=ImportError("missing multimedia")), \
             patch("eyebar.services.alarms.QApplication.beep") as beep, \
             self.assertLogs("eyebar.alarms", level="WARNING") as log:
            self.engine._start_sound()
            self.engine._fallback_sound("Repeated event")
            beep.assert_called_once()
            self.assertEqual(len(log.output), 1)
            self.assertEqual(self.engine.audio_mode, "system")
            self.assertIn("volume cannot be controlled", self.engine.audio_warning)
            self.assertTrue(self.engine._sound_timer.isActive())
            self.engine.stop_ringing()
            self.assertFalse(self.engine._sound_timer.isActive())

    def test_loading_failure_releases_effect_and_falls_back(self):
        self.engine.ringing = dict(id="wake", time="07:00", volume=50)
        effect = FakeEffect()
        effect.current_status = effect.Status.Loading
        with patch.object(self.engine, "_selected_sound_path", return_value=Path(self.tmp.name)/"tone.wav"), \
             patch.object(self.engine, "_make_sound_effect", return_value=effect), \
             patch("eyebar.services.alarms.QApplication.beep") as beep, \
             self.assertLogs("eyebar.alarms", level="WARNING"):
            self.engine._start_sound()
            self.assertTrue(self.engine._audio_watchdog.isActive())
            effect.current_status = effect.Status.Error
            effect.statusChanged.emit()
            self.assertEqual(self.engine.audio_mode, "system")
            self.assertFalse(self.engine._audio_watchdog.isActive())
            effect.stop.assert_called_once()
            effect.deleteLater.assert_called_once()
            beep.assert_called_once()
            effect.statusChanged.emit()  # stale signals must not start more audio
            beep.assert_called_once()

    def test_alarm_editor_roundtrip_keeps_audio_choice(self):
        from eyebar.i18n import I18n
        from eyebar.ui.alarms import AlarmDialog
        from eyebar.ui.theme import STYLE
        self.app.setStyleSheet(STYLE)
        context = SimpleNamespace(config=self.config, alarms=self.engine,
                                  i18n=I18n(Path(__file__).resolve().parents[1] / "locales"))
        dialog = AlarmDialog(context)
        try:
            dialog.resize(430, 480)
            dialog.show()
            self.app.processEvents()
            dialog.sound.setCurrentIndex(dialog.sound.findData("soft"))
            dialog.volume.setValue(24)
            dialog._save()
            self.assertEqual(self.engine.alarms[0]["sound"], "soft")
            self.assertEqual(self.engine.alarms[0]["volume"], 24)
            dialog._add()
            self.assertEqual(dialog.sound.currentData(), "default")
            self.assertEqual(dialog.volume.value(), 80)
            dialog.list.setCurrentRow(0)
            self.assertEqual(dialog.sound.currentData(), "soft")
            self.assertEqual(dialog.volume.value(), 24)
            self.assertFalse(dialog.sound_path.isEnabled())
            dialog.sound.setCurrentIndex(dialog.sound.findData("custom"))
            self.assertTrue(dialog.sound_path.isEnabled())
            self.assertLessEqual(dialog.height(), 480)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_next_alarm_includes_snoozed_one_shot_alarm(self):
        from datetime import datetime, timedelta
        now = datetime(2026, 11, 17, 7, 0)
        self.engine.ringing = dict(id="wake", time="07:00", volume=0)
        with patch("eyebar.services.alarms.datetime") as clock:
            clock.now.return_value = now
            self.engine.snooze(5)
            self.assertEqual(self.engine.next_time(), now + timedelta(minutes=5))


if __name__ == "__main__":
    unittest.main()
