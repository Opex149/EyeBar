"""Qt lifecycle regressions: resting/hidden mascots do not run a frame loop."""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PyQt6") is not None


@unittest.skipUnless(HAS_QT, "PyQt6 is not installed")
class AnimationLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from eyebar.mascots.cyber_cat import create
        from eyebar.mascots.base import FORM_FULL
        from eyebar.ui.widgets import MascotWidget
        self.widget = MascotWidget(create(), FORM_FULL)
        self.widget.set_cursor_tracking(False)
        self.widget.resize(400, 320)
        self.widget.show()
        self.app.processEvents()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def finish(self, key):
        animation = self.widget._animations.get(key)
        self.assertIsNotNone(animation, key)
        animation.setCurrentTime(animation.duration())

    def test_idle_has_no_frame_loop_and_clock_is_independent(self):
        self.assertFalse(self.widget._timer.isActive())
        self.assertTrue(self.widget._clock_timer.isActive())
        self.assertTrue(self.widget._blink_timer.isActive())
        self.assertGreaterEqual(self.widget._blink_timer.interval(), 2800)
        self.assertTrue(self.widget._gesture_timer.isActive())
        self.assertRegex(self.widget.state.hh, r"^\d\d$")
        self.assertEqual(self.widget._animations, {})

    def test_blink_is_finite_and_does_not_start_a_frame_loop(self):
        self.widget._blink()
        animation = self.widget._animations["blink"]
        animation.setCurrentTime(animation.duration() // 2)
        self.assertLess(self.widget.state.blink, 0.1)
        self.finish("blink")
        self.assertEqual(self.widget.state.blink, 1.0)
        self.assertNotIn("blink", self.widget._animations)
        self.assertFalse(self.widget._timer.isActive())

    def test_hidden_widgets_stop_every_timer_and_animation(self):
        self.widget.set_weather("wet", True)
        self.widget.react_to_timer()
        self.assertTrue(self.widget._timer.isActive())
        self.assertTrue(self.widget._animations)
        self.widget.hide()
        self.assertFalse(any(t.isActive() for t in self.widget._all_timers()))
        self.assertFalse(self.widget._animations)
        self.widget.show()
        self.assertTrue(self.widget._clock_timer.isActive())
        self.assertTrue(self.widget._timer.isActive())  # moving weather resumes

    def test_disabled_decorations_leave_static_weather_and_a_readable_alert(self):
        self.widget.set_night_mode(True)
        self.widget.set_weather("umbrella", True)
        self.widget.set_animations_enabled(False)
        self.assertFalse(self.widget._animations)
        self.assertTrue(self.widget._clock_timer.isActive())
        self.assertFalse(self.widget._timer.isActive())
        self.assertFalse(self.widget._cursor_timer.isActive())
        self.assertFalse(self.widget._blink_timer.isActive())
        self.assertFalse(self.widget._gesture_timer.isActive())
        self.assertEqual(self.widget.state.umbrella, 1.0)
        self.widget.set_alert(True)
        self.assertTrue(self.widget.state.alert)
        self.assertEqual(self.widget.state.sleep_phase, 0.0)
        self.assertEqual(self.widget.state.blink, 1.0)
        self.assertEqual(self.widget.state.glow, 1.0)
        self.assertFalse(self.widget._timer.isActive())
        self.widget.react_to_timer()
        self.assertFalse(self.widget._animations)

    def test_weather_clearing_stops_its_frame_timer(self):
        self.widget.set_weather("wet", True)
        self.finish("weather")
        self.assertTrue(self.widget._timer.isActive())
        self.widget.set_weather("none", False)
        self.finish("weather")
        self.assertEqual(self.widget.state.rain, 0.0)
        self.assertEqual(self.widget.state.wind, 0.0)
        self.assertFalse(self.widget._timer.isActive())
        self.assertNotIn("weather", self.widget._animations)

    def test_clock_keeps_updating_with_decorations_disabled(self):
        from datetime import datetime
        self.widget.set_animations_enabled(False)
        self.widget.state.hh, self.widget.state.mm = "--", "--"
        with patch("eyebar.ui.widgets.datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 17, 12, 34, 20)
            self.widget._update_clock()
        self.assertEqual((self.widget.state.hh, self.widget.state.mm), ("12", "34"))
        self.assertTrue(self.widget._clock_timer.isActive())
        self.assertEqual(self.widget._clock_timer.interval(), 40020)
        self.assertFalse(self.widget._timer.isActive())

    def test_sleep_wake_and_interrupted_sleep_restore_state(self):
        self.widget.set_night_mode(True)
        self.finish("sleep")
        self.assertEqual(self.widget.state.sleep_phase, 1.0)
        self.assertLess(self.widget.state.glow, 1.0)
        self.widget.set_night_mode(False)
        self.finish("sleep")
        self.assertEqual(self.widget.state.sleep_phase, 0.0)
        self.assertEqual(self.widget.state.blink, 1.0)
        self.widget.set_night_mode(True)
        self.widget.set_night_mode(False)  # reverse before Qt advances a frame
        self.assertNotIn("sleep", self.widget._animations)
        self.assertEqual(self.widget.state.sleep_phase, 0.0)

    def test_timer_acknowledgement_finishes_and_returns_to_rest(self):
        self.widget.react_to_timer()
        animation = self.widget._animations["reaction"]
        animation.setCurrentTime(animation.duration() // 2)
        self.assertGreater(self.widget.state.bob, 3)
        self.assertGreater(self.widget.state.stretch, 0)
        self.finish("reaction")
        self.assertFalse(self.widget._timer_reacting)
        self.assertEqual(self.widget.state.bob, 0)
        self.assertEqual(self.widget.state.stretch, 0)
        self.assertFalse(self.widget._timer.isActive())

    def test_static_cursor_does_not_restart_finished_eye_animation(self):
        from PyQt6.QtCore import QPoint
        self.widget.set_cursor_tracking(True)
        centre = self.widget.mapToGlobal(self.widget.rect().center())
        with patch("eyebar.ui.widgets.QCursor.pos", return_value=centre + QPoint(30, 10)):
            self.widget._poll_cursor()
            self.finish("eyes")
            self.widget._poll_cursor()
            self.assertNotIn("eyes", self.widget._animations)
        self.assertFalse(self.widget._timer.isActive())

    def test_intensity_reduces_amplitude_and_gesture_frequency(self):
        self.widget.set_animation_intensity(25)
        self.widget._blink()
        blink = self.widget._animations["blink"]
        blink.setCurrentTime(blink.duration() // 2)
        self.assertAlmostEqual(self.widget.state.blink, 0.75, places=2)
        self.assertGreater(self.widget._blink_timer.interval(), 6200)
        self.finish("blink")
        self.widget.react_to_timer()
        reaction = self.widget._animations["reaction"]
        reaction.setCurrentTime(reaction.duration() // 2)
        self.assertAlmostEqual(self.widget.state.bob, 0.95, places=2)
        self.widget.set_animation_intensity(0)
        self.assertFalse(self.widget._animations)
        self.assertFalse(self.widget._timer.isActive())
        self.assertFalse(self.widget._blink_timer.isActive())
        self.assertFalse(self.widget._gesture_timer.isActive())
        self.assertTrue(self.widget._clock_timer.isActive())
        self.widget.set_alert(True)
        self.assertTrue(self.widget.state.alert)
        self.assertEqual(self.widget.state.blink, 1.0)
        self.assertFalse(self.widget._timer.isActive())

    def test_character_crossfade_can_be_interrupted_hidden_or_disabled(self):
        from eyebar.mascots.neon_ghost import create as ghost
        from eyebar.mascots.luna_bunny import create as bunny
        self.widget.set_mascot(ghost())
        self.assertIn("swap", self.widget._animations)
        swap = self.widget._animations["swap"]
        self.assertEqual(swap.duration(), 180)
        swap.setCurrentTime(90)
        self.assertAlmostEqual(self.widget._mascot_opacity, 0.5)
        self.widget.set_mascot(bunny())
        self.assertEqual(self.widget._previous_mascot.id, "neon_ghost")
        self.assertEqual(list(self.widget._animations).count("swap"), 1)
        self.widget.set_animation_intensity(0)
        self.assertIsNone(self.widget._previous_mascot)
        self.assertEqual(self.widget._mascot_opacity, 1.0)
        self.assertFalse(self.widget._animations)
        self.widget.set_mascot(ghost())
        self.assertIsNone(self.widget._previous_mascot)
        self.assertEqual(self.widget._mascot_opacity, 1.0)
        self.widget.set_animation_intensity(100)
        self.widget.set_mascot(bunny())
        self.widget.hide()
        self.assertFalse(self.widget._animations)
        self.assertIsNone(self.widget._previous_mascot)
        self.assertEqual(self.widget._mascot_opacity, 1.0)
        self.widget.show()
        self.assertEqual(self.widget.mascot.id, "luna_bunny")
        self.assertEqual(self.widget._mascot_opacity, 1.0)

    def test_repeated_swap_does_not_accumulate_animation_objects(self):
        from PyQt6.QtCore import QCoreApplication, QEvent, QVariantAnimation
        from eyebar.mascots.neon_ghost import create as ghost
        from eyebar.mascots.luna_bunny import create as bunny
        for index in range(40):
            self.widget.set_mascot(ghost() if index % 2 else bunny())
        self.finish("swap")
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(self.widget.findChildren(QVariantAnimation))
        self.assertFalse(self.widget._animations)
        self.assertIsNone(self.widget._previous_mascot)

    def test_safe_scale_fits_canvas_and_appearance_preserves_other_fields(self):
        from PyQt6.QtCore import QRectF
        from eyebar.mascots.base import Mascot

        class RecordingMascot(Mascot):
            id = "recording"

            def paint(self, painter, form, state):
                self.bounds = painter.transform().mapRect(QRectF(0, 0, 200, 160))

        recording = RecordingMascot()
        self.widget.set_animations_enabled(False)
        self.widget.set_mascot(recording)
        widths = []
        for size in (80, 100, 120):
            self.widget.set_appearance(size, "#ff9900", 45)
            self.widget.grab()
            self.assertTrue(QRectF(self.widget.rect()).contains(recording.bounds))
            self.assertAlmostEqual(recording.bounds.center().x(), self.widget.width() / 2)
            widths.append(recording.bounds.width())
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])
        self.assertEqual(self.widget.state.outline_color, "#ff9900")
        self.assertEqual(self.widget.state.backlight, 0.45)
        self.widget.set_mascot_scale(80)
        self.assertEqual(self.widget.state.outline_color, "#ff9900")
        self.assertEqual(self.widget.state.backlight, 0.45)
        self.widget.set_appearance(999, "invalid color", -2)
        self.assertEqual(self.widget._mascot_scale, 120)
        self.assertEqual(self.widget.state.outline_color, "#ff9900")
        self.assertEqual(self.widget.state.backlight, 0.0)

    def test_passive_flight_copy_does_not_mutate_shared_state(self):
        from eyebar.ui.widgets import MascotWidget
        from eyebar.mascots.base import FORM_FULL
        self.widget.state.tail = 0.73
        self.widget.state.blink = 0.61
        flight = MascotWidget(self.widget.mascot, FORM_FULL,
                              shared_state=self.widget.state, passive=True)
        try:
            flight.show()
            self.assertTrue(flight._timer.isActive())
            flight._tick()
            self.assertEqual(self.widget.state.tail, 0.73)
            self.assertEqual(self.widget.state.blink, 0.61)
            self.assertFalse(flight._clock_timer.isActive())
            flight.hide()
            self.assertFalse(any(t.isActive() for t in flight._all_timers()))
            self.assertEqual(self.widget.state.tail, 0.73)
        finally:
            flight.close()
            flight.deleteLater()


@unittest.skipUnless(HAS_QT, "PyQt6 is not installed")
class MediaViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from pathlib import Path
        from types import SimpleNamespace
        from eyebar.i18n import I18n
        from eyebar.services.media import MediaService
        from eyebar.ui.widgets import NowPlayingView
        self.media = MediaService()
        self.media.backend_ok = True
        self.ctx = SimpleNamespace(media=self.media,
            i18n=I18n(Path(__file__).resolve().parents[1] / "locales"))
        self.widget = NowPlayingView(self.ctx)
        self.widget.resize(230, 90)
        self.widget.show()
        self.app.processEvents()

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()

    def test_long_metadata_is_elided_but_full_text_remains_accessible(self):
        from eyebar.services.media import TrackInfo
        title = "Очень длинное название трека " * 15
        artist = "Исполнитель и соавторы " * 15
        self.widget.set_info(TrackInfo(available=True, title=title, artist=artist, playing=True))
        self.app.processEvents()
        self.assertEqual(self.widget.title.toolTip(), title.strip())
        self.assertEqual(self.widget.artist.toolTip(), artist.strip())
        self.assertEqual(self.widget.title.accessibleName(), title.strip())
        self.assertLess(len(self.widget.title.text()), len(title))
        self.assertLess(self.widget.width(), 300)
        self.assertEqual(self.widget.status._full, self.ctx.i18n.t("media.playing"))

    def test_paused_empty_and_unavailable_are_distinct(self):
        from eyebar.services.media import TrackInfo
        self.widget.set_info(TrackInfo(available=True, title="Real track", playing=False))
        self.assertEqual(self.widget.title._full, "Real track")
        self.assertEqual(self.widget.status._full, self.ctx.i18n.t("media.paused"))
        self.widget.set_info(TrackInfo(available=True, playing=True))
        self.assertEqual(self.widget.title._full, self.ctx.i18n.t("media.no_metadata"))
        self.widget.set_info(TrackInfo())
        self.assertEqual(self.widget.title._full, self.ctx.i18n.t("media.nothing"))
        self.assertTrue(self.widget.status.isHidden())
        self.media.backend_ok = False
        self.widget.set_info(TrackInfo(available=True, title="Stale track", playing=True))
        self.assertEqual(self.widget.title._full, self.ctx.i18n.t("media.unavailable"))
        self.assertTrue(self.widget.status.isHidden())


if __name__ == "__main__":
    unittest.main()
