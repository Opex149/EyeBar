"""StandBy geometry and lifecycle checks in Qt logical coordinates."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PyQt6") is not None


@unittest.skipUnless(HAS_QT, "PyQt6 is not installed")
class StandbyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from eyebar.ui.theme import STYLE
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from eyebar.app import Controller
        from eyebar.config import Config
        self.tmp = tempfile.TemporaryDirectory()
        config = Config(Path(self.tmp.name) / "config.json")
        config.set("decorative_animations", False, save=False)
        with patch("eyebar.app.Config", return_value=config):
            self.ctx = Controller(self.app)
        self.window = self.ctx.standby
        self.window.apply_settings()

    def tearDown(self):
        self.ctx._cleanup()
        self.ctx.minibar.close()
        self.window.close()
        self.app.processEvents()
        self.tmp.cleanup()

    def _assert_inside(self, widget):
        from PyQt6.QtCore import QPoint, QRect
        rect = QRect(widget.mapTo(self.window, QPoint()), widget.size())
        self.assertTrue(self.window.rect().contains(rect),
                        f"{widget.objectName()} {rect} outside {self.window.rect()}")

    def test_cards_and_controls_fit_logical_resolutions(self):
        # 960x540 represents Full HD at 200%; the other sizes include QHD/4K.
        sizes = ((960, 540), (1280, 720), (1536, 864),
                 (1920, 1080), (2560, 1440), (3840, 2160))
        for profile in ("classic", "dashboard", "minimal"):
            self.ctx.config.set("standby_profile", profile, save=False)
            self.window.apply_settings()
            for width, height in sizes:
                with self.subTest(profile=profile, width=width, height=height):
                    self.window.resize(width, height)
                    self.window.show()
                    self.app.processEvents()
                    self.assertEqual(self.window.width(), width)
                    self.assertEqual(self.window.height(), height)
                    for widget in (*self.window._cards, self.window.clock,
                                   self.window.date, self.window.mascot,
                                   self.window.btn_stop, self.window.btn_play,
                                   self.window.btn_settings, self.window.dashboard_status):
                        if widget.isVisible():
                            self._assert_inside(widget)
                    self.assertGreater(self.window.clock.fontMetrics().height(), 50)
                    self.assertLessEqual(self.window.clock.fontMetrics().horizontalAdvance(
                        self.window.clock.text()), self.window.clock.width())
                    cards = self.window._cards
                    self.assertEqual(len({card.size().width() for card in cards}), 1)
                    self.assertEqual(len({card.size().height() for card in cards}), 1)
                    from PyQt6.QtCore import QPoint, QRect
                    for field in (self.window.weather_w, self.window.timer_w,
                                  self.window.btn_stop, self.window.btn_play,
                                  self.window.now, self.window.notes,
                                  self.window.btn_custom, self.window.btn_pause,
                                  self.window.btn_reset):
                        if not field.isVisible():
                            continue
                        parent = field.parentWidget()
                        rect = QRect(field.mapTo(parent, QPoint()), field.size())
                        self.assertTrue(parent.rect().contains(rect),
                                        f"{field} {rect} outside its card {parent.rect()}")
                    self.window.hide()

    def test_profile_switches_preserve_customization_notes_and_running_timer(self):
        from eyebar.config import Config
        self.ctx.config.data.update(standby_cards=["weather", "timer"],
                                    mascot_scale=120, notes="Кириллица сохранена")
        self.ctx.timer.start(300)
        self.window.resize(960, 540)
        self.window.show()
        for profile in ("minimal", "dashboard", "classic"):
            self.ctx.config.set("standby_profile", profile, save=False)
            self.window.apply_settings()
            self.app.processEvents()
            self.assertEqual(self.window.mascot.isVisible(), profile != "minimal")
            self.assertEqual(self.window._card_map["weather"].isVisible(), profile != "minimal")
            self.assertFalse(self.window._card_map["music"].isVisible())
            self.assertFalse(self.window._card_map["notes"].isVisible())
            self.assertEqual(self.window.dashboard_status.isVisible(), profile == "dashboard")
            self.assertTrue(self.ctx.timer.active)
            self.assertGreater(self.ctx.timer.remaining(), 298)
            self.assertEqual(self.ctx.config.get("standby_cards"), ["weather", "timer"])
        self.assertTrue(self.ctx.config.save())
        restored = Config(self.ctx.config.path)
        self.assertEqual(restored.get("standby_cards"), ["weather", "timer"])
        self.assertEqual(restored.get("mascot_scale"), 120)
        self.assertEqual(restored.get("notes"), "Кириллица сохранена")

    def test_autohide_restores_controls_on_mouse_keyboard_and_alarm(self):
        from PyQt6.QtCore import QPoint, Qt
        from PyQt6.QtTest import QTest
        self.ctx.config.set("standby_autohide", True, save=False)
        self.window.apply_settings()
        self.window.resize(960, 540)
        self.window.show()
        self.app.processEvents()
        self.window.setFocus()
        self.window._controls_timer.start(25)
        QTest.qWait(60)
        self.assertTrue(self.window._controls_hidden)
        self.assertFalse(self.window.bottom.isEnabled())
        QTest.mouseMove(self.window, QPoint(4, 4))
        self.app.processEvents()
        self.assertFalse(self.window._controls_hidden)
        self.assertTrue(self.window.bottom.isEnabled())
        self.window._hide_controls()
        self.assertTrue(self.window._controls_hidden)
        QTest.keyClick(self.window, Qt.Key.Key_Tab)
        self.assertFalse(self.window._controls_hidden)
        self.window._hide_controls()
        self.window.show_alarm({"time": "07:00"})
        self.assertFalse(self.window._controls_hidden)
        self.assertTrue(self.window.bottom.isEnabled())
        self.assertFalse(self.window._controls_timer.isActive())
        self.window._hide_controls()
        self.assertFalse(self.window._controls_hidden)
        self.window.hide_alarm()
        self.assertTrue(self.window._controls_timer.isActive())

    def test_brightness_affects_content_without_dimming_alarm_or_navigation(self):
        self.window.resize(960, 540)
        self.window.show()
        self.window.slider.setValue(10)
        self.assertLess(self.window._content_opacity.opacity(), 0.5)
        self.assertEqual(self.window._bottom_opacity.opacity(), 1.0)
        self.assertEqual(self.window.alarm_panel.graphicsEffect().opacity(), 1.0)
        self.assertFalse(hasattr(self.window, "overlay"))
        self.window.set_night_mode(True)
        self.assertLess(self.window._content_opacity.opacity(), 0.25)
        self.assertEqual(self.window._bottom_opacity.opacity(), 1.0)
        self.window.set_night_mode(False)
        self.window.slider.setValue(100)
        self.assertEqual(self.window._content_opacity.opacity(), 1.0)

    def test_disabling_decorations_cancels_controls_fade_and_keeps_buttons_visible(self):
        from PyQt6.QtTest import QTest
        self.ctx.config.data.update(decorative_animations=True, animation_intensity=100,
                                    standby_autohide=False)
        self.window.apply_settings()
        self.window.resize(960, 540)
        self.window.show()
        QTest.qWait(280)
        for key, value in (("animation_intensity", 0), ("decorative_animations", False)):
            with self.subTest(disabled_by=key):
                self.ctx.config.data.update(decorative_animations=True, animation_intensity=100)
                self.window.apply_settings()
                self.window._set_controls_visible(False)
                self.window._controls_animation.setCurrentTime(180)
                self.window._set_controls_visible(True)
                self.window._controls_animation.setCurrentTime(90)
                self.assertGreater(self.window._bottom_opacity.opacity(), 0.0)
                self.assertLess(self.window._bottom_opacity.opacity(), 1.0)
                self.ctx.config.set(key, value, save=False)
                self.window.apply_settings()
                self.assertIsNone(self.window._controls_animation)
                self.assertFalse(self.window._controls_hidden)
                self.assertTrue(self.window.bottom.isEnabled())
                self.assertEqual(self.window._bottom_opacity.opacity(), 1.0)
                QTest.qWait(220)
                self.assertEqual(self.window._bottom_opacity.opacity(), 1.0)
                self.assertIsNone(self.window._controls_animation)

    def test_navigation_pixels_survive_profile_theme_changes_and_reopening(self):
        from PyQt6.QtCore import QPoint, QRect
        self.ctx.config.data.update(decorative_animations=False, animation_intensity=0,
                                    standby_autohide=False)
        for material in ("classic", "frosted", "liquid"):
            self.ctx.config.set("glass_mode", material, save=False)
            for profile in ("classic", "minimal", "dashboard"):
                with self.subTest(material=material, profile=profile):
                    self.ctx.config.set("standby_profile", profile, save=False)
                    self.window.apply_settings()
                    self.window.resize(960, 540)
                    for _repeat in range(2):
                        self.window.show()
                        self.app.processEvents()
                        self.app.processEvents()
                        image = self.window.grab().toImage()
                        ratio = image.width() / self.window.width()
                        for control in (self.window.slider, self.window.btn_settings):
                            top_left = control.mapTo(self.window, QPoint())
                            rect = QRect(round(top_left.x() * ratio), round(top_left.y() * ratio),
                                         round(control.width() * ratio), round(control.height() * ratio))
                            bright_pixels = sum(
                                max(image.pixelColor(x, y).getRgb()[:3]) > 100
                                for y in range(rect.top(), rect.bottom() + 1)
                                for x in range(rect.left(), rect.right() + 1)
                            )
                            self.assertGreater(bright_pixels, 10,
                                               f"Navigation rendered blank: {profile}/{material}/{control}")
                        self.window.hide()

    def test_timer_buttons_pause_resume_reset_and_custom_duration(self):
        from eyebar.ui.standby import QInputDialog
        self.window.resize(960, 540)
        self.window.show()
        self.app.processEvents()
        self.assertEqual([minutes for _button, minutes in self.window._preset_buttons],
                         [5, 15, 25, 45])
        self.window._preset_buttons[0][0].click()
        self.assertTrue(self.ctx.timer.active)
        self.assertEqual(self.ctx.timer.initial_duration, 300)
        self.window.btn_pause.click()
        self.assertTrue(self.ctx.timer.paused)
        self.assertTrue(self.window.timer_w.text_lbl.text().startswith("05:00"))
        self.window.btn_pause.click()
        self.assertTrue(self.ctx.timer.active)
        self.window.btn_reset.click()
        self.assertEqual(self.ctx.timer.state, "ready")
        self.assertEqual(self.ctx.timer.remaining(), 300)
        self.window.btn_pause.click()
        self.assertTrue(self.ctx.timer.active)
        self.window.btn_stop.click()
        self.assertEqual(self.ctx.timer.state, "idle")
        self.window.btn_pause.click()
        self.assertTrue(self.ctx.timer.active)
        with patch.object(QInputDialog, "getInt", return_value=(7, True)):
            self.window.btn_custom.click()
        self.assertEqual(self.ctx.timer.initial_duration, 420)

    def test_alarm_fade_finishes_and_cancels_without_retaining_animation(self):
        from PyQt6.QtTest import QTest
        self.ctx.config.set("decorative_animations", True, save=False)
        self.window.apply_settings()
        self.window.resize(960, 540)
        self.window.show()
        self.window.show_alarm({"time": "07:00"})
        self.assertIsNotNone(self.window._alarm_animation)
        QTest.qWait(220)
        self.assertIsNone(self.window._alarm_animation)
        self.assertEqual(self.window._alarm_opacity.opacity(), 1.0)
        self.window.show_alarm({"time": "07:00"})
        self.window.hide_alarm()
        self.assertIsNone(self.window._alarm_animation)
        self.assertFalse(self.window.alarm_panel.isVisible())
        self.window.show_alarm({"time": "07:00"})
        self.window.hide()
        self.assertIsNone(self.window._alarm_animation)

    def test_character_can_move_to_each_saved_position(self):
        self.window.resize(1280, 720)
        self.window.show()
        for position in ("left", "center", "right"):
            with self.subTest(position=position):
                self.ctx.config.set("standby_mascot_position", position, save=False)
                self.window.apply_settings()
                self.app.processEvents()
                order = [self.window.body.itemAt(i).widget() for i in range(3)]
                index = {"left": 0, "center": 1, "right": 2}[position]
                self.assertIs(order[index], self.window.mascot)
                for widget in order:
                    self._assert_inside(widget)

    def test_hidden_standby_stops_clock_and_skips_service_redraws(self):
        from eyebar.services.media import TrackInfo
        self.window.resize(1280, 720)
        self.window.show()
        self.app.processEvents()
        self.assertTrue(self.window._clock_timer.isActive())
        self.window.hide()
        self.assertFalse(self.window._clock_timer.isActive())
        with patch.object(self.window.weather_w, "set") as weather_update, \
             patch.object(self.window.now, "set_info") as media_update:
            self.ctx.timer.tick.emit(10)
            self.ctx.media.updated.emit(TrackInfo(title="Hidden update"))
            self.assertFalse(weather_update.called)
            self.assertFalse(media_update.called)
        self.window.show()
        self.app.processEvents()
        self.assertTrue(self.window._clock_timer.isActive())
        self.assertTrue(self.window.clock.text())

    def test_fade_finishes_before_exit_and_can_be_cancelled_by_hide(self):
        from PyQt6.QtTest import QSignalSpy, QTest
        self.ctx.config.set("decorative_animations", True, save=False)
        self.window.apply_settings()
        self.window.resize(1280, 720)
        self.window.show()
        self.app.processEvents()
        self.window.exitRequested.disconnect(self.ctx.exit_standby)
        spy = QSignalSpy(self.window.exitRequested)
        self.window.request_exit()
        self.assertEqual(len(spy), 0)
        QTest.qWait(250)
        self.assertEqual(len(spy), 1)
        self.assertIsNone(self.window._transition)
        self.window.hide()
        self.window.show()
        self.window.request_exit()
        self.window.hide()
        QTest.qWait(250)
        self.assertEqual(len(spy), 1)
        self.assertFalse(self.window._clock_timer.isActive())
        self.assertIsNone(self.window._transition)


if __name__ == "__main__":
    unittest.main()
