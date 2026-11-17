"""Deterministic regression tests for new domain logic; no GUI installation needed."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from eyebar.config import Config
from eyebar.services.alarm_logic import sanitize_alarms, should_ring, next_alarm_time, valid_time
from eyebar.services.night_logic import in_night_window


class AlarmLogicTests(unittest.TestCase):
    def test_time_validation(self):
        for text in ("00:00", "07:15", "23:59"):
            self.assertTrue(valid_time(text))
        for text in ("24:00", "12:60", "7:15", "2026-01-02", None, 720):
            self.assertFalse(valid_time(text))

    def test_repeat_and_once(self):
        monday = datetime(2026, 11, 16, 7, 30)
        alarm = dict(id="once", time="07:30", days=[], enabled=True, last_date="")
        self.assertTrue(should_ring(alarm, monday))
        alarm["last_date"] = "2026-11-16"
        self.assertFalse(should_ring(alarm, monday))
        alarm.update(last_date="", days=[1, 4])
        self.assertFalse(should_ring(alarm, monday))
        alarm["days"] = [0, 2, 4]
        self.assertTrue(should_ring(alarm, monday))
        self.assertFalse(should_ring(alarm, datetime(2026, 11, 16, 7, 31)))

    def test_next_occurrence_excludes_past_and_days(self):
        now = datetime(2026, 11, 16, 9, 0)
        alarms = [dict(time="07:00", days=[0], enabled=True, last_date=""),
                  dict(time="09:10", days=[], enabled=True, last_date="")]
        self.assertEqual(next_alarm_time(alarms, now), datetime(2026, 11, 16, 9, 10))
        self.assertEqual(next_alarm_time(alarms[:1], now), datetime(2026, 11, 23, 7, 0))

    def test_invalid_alarm_data_is_sanitized(self):
        bad = [dict(id="legit", time="09:20", days=[1, 1, 8, "2"], enabled=True, last_date="2026-11-16"),
               dict(id="legit", time="20:00"), dict(id="evil", time="abc"), None]
        got = sanitize_alarms(bad)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["days"], [1])
        self.assertEqual(got[0]["last_date"], "2026-11-16")


class NightScheduleTests(unittest.TestCase):
    def test_cross_midnight(self):
        self.assertTrue(in_night_window(datetime(2026, 11, 16, 23, 45), "23:00", "07:00"))
        self.assertTrue(in_night_window(datetime(2026, 11, 17, 6, 59), "23:00", "07:00"))
        self.assertFalse(in_night_window(datetime(2026, 11, 17, 7, 0), "23:00", "07:00"))
        self.assertFalse(in_night_window(datetime(2026, 11, 17, 13, 0), "23:00", "07:00"))

    def test_day_schedule_and_invalid(self):
        t = datetime(2026, 11, 16, 13, 0)
        self.assertTrue(in_night_window(t, "12:00", "14:00"))
        self.assertFalse(in_night_window(t, "14:00", "18:00"))
        self.assertFalse(in_night_window(t, "11:00", "11:00"))
        self.assertFalse(in_night_window(t, "aa:xx", "11:00"))


class ConfigV11Tests(unittest.TestCase):
    def test_persists_alarm_and_night_preserves_existing_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            cfg = Config(path)
            cfg.data.update(mascot="neon_ghost", brightness=42, notes="preserve me",
                            alarms=[dict(id="wake", time="06:45", days=[0,1,2], enabled=True, last_date="")],
                            night_auto=True, night_start="22:30", night_end="08:00")
            self.assertTrue(cfg.save())
            c2 = Config(path)
            self.assertEqual(c2.get("mascot"), "neon_ghost")
            self.assertEqual(c2.get("notes"), "preserve me")
            self.assertEqual(c2.get("brightness"), 42)
            self.assertTrue(c2.get("night_auto"))
            self.assertEqual(c2.get("alarms")[0]["time"], "06:45")

    def test_corrupt_new_keys_safe(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "config.json"
            path.write_text(json.dumps({"alarms": "oops", "night_auto": "yes", "night_start":"37:70",
                                        "night_end": "bad", "night_previous_scheme": 5}))
            c = Config(path)
            self.assertEqual(c.get("alarms"), [])
            self.assertFalse(c.get("night_auto"))
            self.assertEqual(c.get("night_start"), "23:00")
            self.assertEqual(c.get("night_end"), "07:00")
            self.assertEqual(c.get("night_previous_scheme"), "")


if __name__ == "__main__":
    unittest.main()
