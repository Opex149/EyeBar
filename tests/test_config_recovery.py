"""Durable config migration, recovery and validation; no Qt required."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eyebar.config import BACKUP_COUNT, CONFIG_VERSION, Config, DEFAULTS


class ConfigRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "config.json"

    def write(self, value):
        self.path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def test_migration_copies_original_before_the_first_primary_replacement(self):
        original = '{"notes": "Не потерять эти заметки", "mascot": "byte_fox", "extra": {"keep": 1}}\n'
        self.path.write_text(original, encoding="utf-8")
        config = Config(self.path)
        config.set("standby_profile", "minimal", save=False)
        replace = os.replace

        def check_before_replace(source, target):
            if Path(target) == self.path:
                self.assertEqual(config.migration_backup_path.read_text(encoding="utf-8"), original)
            return replace(source, target)

        with patch("eyebar.config.os.replace", side_effect=check_before_replace):
            self.assertTrue(config.save())
        reopened = Config(self.path)
        self.assertEqual(reopened.get("notes"), "Не потерять эти заметки")
        self.assertEqual(reopened.get("extra"), {"keep": 1})
        self.assertEqual(reopened.get("config_version"), CONFIG_VERSION)
        config.set("city", "Казань")
        self.assertEqual(config.migration_backup_path.read_text(encoding="utf-8"), original)

    def test_latest_saved_notes_recover_even_after_first_save(self):
        config = Config(self.path)
        config.data.update(notes="Первая заметка 🐈", future_key={"unchanged": [1, 2]})
        self.assertTrue(config.save())
        broken = b'{"notes": "interrupted'
        self.path.write_bytes(broken)
        recovered = Config(self.path)
        self.assertEqual(recovered.recovered_from, config.backup_path)
        self.assertEqual(recovered.get("notes"), "Первая заметка 🐈")
        self.assertEqual(recovered.get("future_key"), {"unchanged": [1, 2]})
        recovered.set("city", "Тула", save=False)
        self.assertTrue(recovered.save())
        self.assertEqual(Config(self.path).get("notes"), "Первая заметка 🐈")
        archives = list(self.path.parent.glob("config.json.corrupt.*"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_bytes(), broken)
        for backup in recovered._backup_paths():
            if backup.exists():
                self.assertIsInstance(json.loads(backup.read_text(encoding="utf-8")), dict)

    def test_rotating_copies_recover_when_primary_and_latest_copy_are_bad(self):
        config = Config(self.path)
        for note in ("one", "two", "three", "four"):
            config.set("notes", note)
        paths = config._backup_paths()
        self.assertEqual(len(paths), BACKUP_COUNT)
        self.assertTrue(all(path.is_file() for path in paths))
        self.assertEqual([json.loads(path.read_text())["notes"] for path in paths],
                         ["four", "three", "two"])
        self.path.write_bytes(b"\xff\xfe damaged primary")
        paths[0].write_text("[]", encoding="utf-8")
        recovered = Config(self.path)
        self.assertEqual(recovered.recovered_from, paths[1])
        self.assertEqual(recovered.get("notes"), "three")

    def test_missing_primary_uses_backup_and_valid_primary_has_priority(self):
        config = Config(self.path)
        config.set("notes", "backup note")
        self.path.unlink()
        self.assertEqual(Config(self.path).get("notes"), "backup note")
        self.write({"notes": "primary note"})
        reopened = Config(self.path)
        self.assertIsNone(reopened.recovered_from)
        self.assertEqual(reopened.get("notes"), "primary note")

    def test_migration_copy_is_a_last_resort_if_rotating_copies_are_damaged(self):
        self.write({"notes": "original pre-upgrade note", "extra": {"keep": True}})
        config = Config(self.path)
        config.set("notes", "new note")
        self.path.write_text("broken", encoding="utf-8")
        for backup in config._backup_paths():
            backup.write_text("broken", encoding="utf-8")
        recovered = Config(self.path)
        self.assertEqual(recovered.recovered_from, config.migration_backup_path)
        self.assertEqual(recovered.get("notes"), "original pre-upgrade note")
        self.assertEqual(recovered.get("extra"), {"keep": True})

    def test_corrupt_without_any_backup_keeps_original_for_manual_recovery(self):
        original = b'{"notes": "unfinished but potentially recoverable'
        self.path.write_bytes(original)
        config = Config(self.path)
        self.assertEqual(config.get("notes"), "")
        self.assertTrue(config.save())
        archives = list(self.path.parent.glob("config.json.corrupt.*"))
        self.assertEqual(archives[0].read_bytes(), original)

    def test_failed_primary_replace_preserves_old_data_and_cleans_temporary_files(self):
        self.write({"notes": "old note", "extra": "preserve"})
        original = self.path.read_bytes()
        config = Config(self.path)
        config.set("notes", "new unsaved note", save=False)
        replace = os.replace

        def fail_primary(source, target):
            if Path(target) == self.path:
                raise OSError("primary replacement blocked")
            return replace(source, target)

        with patch("eyebar.config.os.replace", side_effect=fail_primary):
            self.assertFalse(config.save())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIn("blocked", str(config.last_save_error))
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        self.assertEqual(Config(self.path).get("notes"), "old note")
        self.assertEqual(config.migration_backup_path.read_bytes(), original)

    def test_failed_file_sync_never_replaces_the_primary(self):
        config = Config(self.path)
        config.set("notes", "last committed")
        original = self.path.read_bytes()
        config.set("notes", "not committed", save=False)
        with patch("eyebar.config.os.fsync", side_effect=OSError("disk sync failed")):
            self.assertFalse(config.save())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_failed_migration_backup_blocks_rewrite_of_original(self):
        self.write({"notes": "original must survive"})
        original = self.path.read_bytes()
        config = Config(self.path)
        config.set("notes", "unsaved change", save=False)
        replace = os.replace

        def fail_upgrade_copy(source, target):
            if Path(target) == config.migration_backup_path:
                raise OSError("upgrade backup blocked")
            return replace(source, target)

        with patch("eyebar.config.os.replace", side_effect=fail_upgrade_copy):
            self.assertFalse(config.save())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))

    def test_serialization_failure_does_not_touch_primary_or_backup(self):
        config = Config(self.path)
        config.set("notes", "keep me")
        primary = self.path.read_bytes()
        backup = config.backup_path.read_bytes()
        config.set("not_json", object(), save=False)
        self.assertFalse(config.save())
        self.assertEqual(self.path.read_bytes(), primary)
        self.assertEqual(config.backup_path.read_bytes(), backup)

    def test_backup_refresh_failure_does_not_report_a_committed_save_as_failed(self):
        config = Config(self.path)
        config.set("notes", "old")
        original = config._store_backup

        def fail_new_mirror(payload):
            if json.loads(payload)["notes"] == "new":
                raise OSError("backup blocked")
            return original(payload)

        config.set("notes", "new", save=False)
        with patch.object(config, "_store_backup", side_effect=fail_new_mirror):
            self.assertTrue(config.save())
        self.assertIsNone(config.last_save_error)
        self.assertIn("backup blocked", str(config.last_backup_error))
        self.assertEqual(Config(self.path).get("notes"), "new")

    def test_future_schema_marker_and_unknown_fields_are_preserved(self):
        self.write({"config_version": 99, "notes": "future note", "future": {"a": 1}})
        config = Config(self.path)
        self.assertTrue(config.save())
        self.assertEqual(Config(self.path).get("config_version"), 99)
        self.assertEqual(Config(self.path).get("future"), {"a": 1})
        self.assertFalse(config.migration_backup_path.exists())


class AppearanceConfigTests(unittest.TestCase):
    def load(self, values):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(values), encoding="utf-8")
            return Config(path)

    def test_full_update_defaults_and_lists_are_independent(self):
        first = self.load({})
        second = self.load({})
        self.assertEqual(first.get("animation_intensity"), 100)
        self.assertEqual(first.get("mascot_scale"), 100)
        self.assertEqual(first.get("outline_color"), "#38BDF8")
        self.assertEqual(first.get("backlight_brightness"), 100)
        self.assertEqual(first.get("standby_profile"), "classic")
        self.assertTrue(first.get("standby_autohide"))
        first.get("standby_cards").clear()
        self.assertEqual(second.get("standby_cards"), ["weather", "music", "timer", "notes"])
        self.assertEqual(DEFAULTS["standby_cards"], second.get("standby_cards"))

    def test_numeric_appearance_options_are_bounded_without_accepting_booleans(self):
        config = self.load({"animation_intensity": -20, "mascot_scale": 999,
                            "backlight_brightness": 0})
        self.assertEqual(config.get("animation_intensity"), 0)
        self.assertEqual(config.get("mascot_scale"), 120)
        self.assertEqual(config.get("backlight_brightness"), 10)
        config = self.load({"animation_intensity": True, "mascot_scale": "80",
                            "backlight_brightness": False, "standby_autohide": "yes"})
        for key in ("animation_intensity", "mascot_scale", "backlight_brightness", "standby_autohide"):
            self.assertEqual(config.get(key), DEFAULTS[key])

    def test_invalid_color_profile_and_cards_are_safe(self):
        config = self.load({"outline_color": "red; arbitrary style", "standby_profile": ["minimal"],
                            "standby_cards": ["notes", "notes", {}, 3, "unknown", "timer"]})
        self.assertEqual(config.get("outline_color"), DEFAULTS["outline_color"])
        self.assertEqual(config.get("standby_profile"), "classic")
        self.assertEqual(config.get("standby_cards"), ["notes", "timer"])
        self.assertEqual(self.load({"standby_cards": []}).get("standby_cards"), [])
        self.assertEqual(self.load({"standby_cards": None}).get("standby_cards"), DEFAULTS["standby_cards"])
        self.assertEqual(self.load({"outline_color": "#a1B2c3"}).get("outline_color"), "#a1B2c3")


if __name__ == "__main__":
    unittest.main()
