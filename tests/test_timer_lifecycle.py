"""Countdown transitions use a monotonic deadline, never GUI callback counts."""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch


HAS_QT = importlib.util.find_spec("PyQt6") is not None


@unittest.skipUnless(HAS_QT, "PyQt6 is not installed")
class TimerLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from eyebar.services.timer import CountdownTimer
        from PyQt6.QtTest import QSignalSpy
        self.clock = patch("eyebar.services.timer.time.monotonic", return_value=100.0)
        self.monotonic = self.clock.start()
        self.timer = CountdownTimer()
        self.finished = QSignalSpy(self.timer.finished)
        self.ticks = QSignalSpy(self.timer.tick)
        self.states = QSignalSpy(self.timer.stateChanged)

    def tearDown(self):
        self.timer.stop()
        self.timer.deleteLater()
        self.app.processEvents()
        self.clock.stop()

    def advance_to(self, moment):
        self.monotonic.return_value = moment
        self.timer._on_timeout()

    def test_callback_frequency_never_accelerates_countdown(self):
        self.timer.start(90)
        for _ in range(50):
            self.timer._on_timeout()
        self.assertEqual(self.timer.remaining(), 90)
        self.assertEqual(len(self.ticks), 1)
        self.assertEqual(len(self.finished), 0)
        self.advance_to(130.2)
        self.assertEqual(self.timer.remaining(), 60)
        self.assertEqual(len(self.ticks), 2)
        self.assertTrue(self.timer.active)
        self.assertFalse(self.timer.paused)

    def test_pause_preserves_fraction_and_resume_ignores_paused_wall_time(self):
        self.timer.start(10)
        self.monotonic.return_value = 103.25
        self.timer.pause()
        self.assertEqual(self.timer.state, "paused")
        self.assertTrue(self.timer.paused)
        self.assertFalse(self.timer.active)
        self.assertFalse(self.timer._t.isActive())
        self.assertEqual(self.timer.remaining(), 7)
        self.advance_to(1000.0)
        self.assertEqual(self.timer.remaining(), 7)
        self.timer.resume()
        self.assertTrue(self.timer.active)
        self.assertFalse(self.timer.paused)
        self.advance_to(1006.74)
        self.assertEqual(self.timer.remaining(), 1)
        self.assertEqual(len(self.finished), 0)
        self.advance_to(1006.75)
        self.assertEqual(self.timer.state, "finished")
        self.assertEqual(self.timer.remaining(), 0)
        self.assertEqual(len(self.finished), 1)
        self.timer._on_timeout()
        self.assertEqual(len(self.finished), 1)

    def test_reset_restores_selected_duration_and_resume_starts_ready_timer(self):
        self.timer.start(45)
        self.advance_to(112.3)
        self.timer.reset()
        self.assertEqual(self.timer.state, "ready")
        self.assertEqual(self.timer.initial_duration, 45)
        self.assertEqual(self.timer.remaining(), 45)
        self.assertFalse(self.timer.active)
        self.assertFalse(self.timer._t.isActive())
        self.advance_to(800.0)
        self.assertEqual(self.timer.remaining(), 45)
        self.timer.resume()
        self.assertEqual(self.timer.remaining(), 45)
        self.advance_to(844.99)
        self.assertEqual(self.timer.remaining(), 1)
        self.advance_to(845.0)
        self.assertEqual(len(self.finished), 1)

    def test_start_replaces_existing_deadline_without_old_completion(self):
        self.timer.start(5)
        self.monotonic.return_value = 102.0
        self.timer.start(20)
        self.advance_to(105.0)
        self.assertEqual(self.timer.remaining(), 17)
        self.assertEqual(len(self.finished), 0)
        self.assertEqual(self.timer.initial_duration, 20)
        self.advance_to(122.0)
        self.assertEqual(len(self.finished), 1)
        self.assertFalse(self.timer._t.isActive())

    def test_pause_at_expired_deadline_finishes_instead_of_storing_zero_pause(self):
        self.timer.start(5)
        self.monotonic.return_value = 105.0
        self.timer.pause()
        self.assertEqual(self.timer.state, "finished")
        self.assertFalse(self.timer.paused)
        self.assertEqual(len(self.finished), 1)
        self.timer.resume()
        self.assertEqual(self.timer.state, "finished")

    def test_stop_preserves_legacy_zero_and_does_not_implicitly_resume(self):
        self.timer.start(15)
        self.advance_to(103.0)
        self.timer.pause()
        self.timer.stop()
        self.assertEqual(self.timer.state, "idle")
        self.assertEqual(self.timer.remaining(), 0)
        self.assertFalse(self.timer.paused)
        self.timer.resume()
        self.assertEqual(self.timer.state, "idle")
        self.timer.reset()
        self.assertEqual(self.timer.remaining(), 15)
        self.assertEqual(self.timer.state, "ready")
        self.assertEqual(len(self.finished), 0)

    def test_zero_duration_finishes_once_and_delayed_callbacks_do_not_duplicate(self):
        self.timer.start(0)
        self.assertEqual(self.timer.state, "finished")
        self.assertEqual(len(self.finished), 1)
        self.advance_to(100000.0)
        self.timer.pause()
        self.timer.resume()
        self.assertEqual(len(self.finished), 1)
        self.timer.start(5)
        self.advance_to(100500.0)
        self.assertEqual(len(self.finished), 2)
        self.timer._on_timeout()
        self.assertEqual(len(self.finished), 2)

    def test_repeated_transitions_reuse_one_qtimer(self):
        from PyQt6.QtCore import QTimer
        original = self.timer._t
        for _ in range(30):
            self.timer.start(30)
            self.timer.pause()
            self.timer.resume()
            self.timer.reset()
        self.assertIs(self.timer._t, original)
        self.assertEqual(self.timer.findChildren(QTimer), [original])

    def test_mode_visibility_cannot_reset_or_pause_service(self):
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QWidget
        mini, standby = QWidget(), QWidget()
        try:
            self.timer.start(25)
            mini.show()
            QTest.qWait(5)
            mini.hide()
            standby.show()
            self.advance_to(110.0)
            standby.hide()
            mini.show()
            QTest.qWait(5)
            self.assertEqual(self.timer.remaining(), 15)
            self.assertTrue(self.timer.active)
            self.assertEqual(self.timer.initial_duration, 25)
        finally:
            mini.close()
            standby.close()
            mini.deleteLater()
            standby.deleteLater()

    def test_state_signals_observe_consistent_flags_and_remaining(self):
        seen = []
        self.timer.changed.connect(lambda: seen.append((
            self.timer.state, self.timer.active, self.timer.paused,
            self.timer.remaining())))
        self.timer.start(5)
        self.timer.pause()
        self.timer.resume()
        self.timer.reset()
        self.assertEqual(seen, [("running", True, False, 5),
                                ("paused", False, True, 5),
                                ("running", True, False, 5),
                                ("ready", False, False, 5)])

    def test_restarting_from_completion_handler_keeps_new_timer_running(self):
        self.timer.finished.connect(lambda: self.timer.start(20))
        self.timer.start(5)
        self.advance_to(105.0)
        self.assertEqual(len(self.finished), 1)
        self.assertTrue(self.timer.active)
        self.assertTrue(self.timer._t.isActive())
        self.assertEqual(self.timer.remaining(), 20)

    def test_reset_from_zero_tick_prevents_stale_finished_alert(self):
        self.timer.tick.connect(lambda seconds: self.timer.reset() if seconds == 0 else None)
        self.timer.start(5)
        self.advance_to(105.0)
        self.assertEqual(self.timer.state, "ready")
        self.assertEqual(self.timer.remaining(), 5)
        self.assertEqual(len(self.finished), 0)


if __name__ == "__main__":
    unittest.main()
