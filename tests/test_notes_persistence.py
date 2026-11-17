"""Notes remain dirty after disk failure and cannot be overwritten on focus."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HAS_QT = importlib.util.find_spec("PyQt6") is not None


@unittest.skipUnless(HAS_QT, "PyQt6 is not installed")
class NotesPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from eyebar.config import Config
        from eyebar.i18n import I18n
        from eyebar.ui.widgets import NotesEdit
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"
        self.config = Config(self.path)
        self.config.set("notes", "Старая заметка\nВторая строка")
        self.ctx = SimpleNamespace(config=self.config,
            i18n=I18n(Path(__file__).resolve().parents[1] / "locales"))
        self.widget = NotesEdit(self.ctx)
        self.widget.resize(320, 220)

    def tearDown(self):
        self.widget.close()
        self.widget.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_failed_write_remains_dirty_and_next_flush_retries(self):
        from eyebar.config import Config
        old = self.widget.toPlainText()
        fresh = "Новая заметка — ёжик 🐈\nНе терять после ошибки диска"
        self.widget.setPlainText(fresh)
        with patch.object(self.config, "save", return_value=False) as save:
            self.assertFalse(self.widget.flush())
            self.assertTrue(self.widget._dirty)
            self.assertEqual(self.widget._last_saved, old)
            self.assertFalse(self.widget._save.isActive())
            self.app.processEvents()
            save.assert_called_once()
        self.assertEqual(Config(self.path).get("notes"), old)
        self.assertTrue(self.widget.flush())
        self.assertFalse(self.widget._dirty)
        self.assertEqual(self.widget._last_saved, fresh)
        self.assertEqual(Config(self.path).get("notes"), fresh)

    def test_show_and_sync_cannot_replace_a_failed_local_edit(self):
        fresh = "Мой несохранённый текст"
        self.widget.setPlainText(fresh)
        with patch.object(self.config, "save", return_value=False):
            self.widget.flush()
        # A concurrent update cannot erase dirty local text. Flushing keeps
        # that text in a recovery file instead of overwriting the other edit.
        self.config.set("notes", "Из другого окна", save=False)
        self.widget._sync_from_config()
        self.widget.show()
        self.app.processEvents()
        self.assertEqual(self.widget.toPlainText(), fresh)
        self.assertTrue(self.widget._dirty)
        self.assertTrue(self.widget.flush())
        self.assertEqual(self.config.get("notes"), "Из другого окна")
        self.assertEqual(self.widget.recovery_path.read_text(encoding="utf-8"), fresh)

    def test_clean_stale_editor_does_not_overwrite_newer_shared_notes(self):
        from eyebar.config import Config
        fresh = "Заметка из другого окна"
        self.config.set("notes", fresh)
        self.assertFalse(self.widget._dirty)
        self.assertTrue(self.widget.flush())
        self.assertEqual(self.widget.toPlainText(), fresh)
        self.assertEqual(Config(self.path).get("notes"), fresh)

    def test_failed_edit_and_newer_other_editor_are_both_preserved_on_cleanup(self):
        from eyebar.config import Config
        from eyebar.ui.widgets import NotesEdit
        for reversed_order in (False, True):
            with self.subTest(reversed_order=reversed_order):
                self.config.set("notes", "Исходная заметка")
                a, b = NotesEdit(self.ctx), NotesEdit(self.ctx)
                older = "Несохранённая правка А — ёжик 🐈\nТочный текст"
                newest = "Новая сохранённая правка Б\nНе заменять старым текстом"
                try:
                    a.setPlainText(older)
                    with patch.object(self.config, "save", return_value=False):
                        self.assertFalse(a.flush())
                    b._sync_from_config()
                    b.setPlainText(newest)
                    self.assertTrue(b.flush())
                    for editor in ((b, a) if reversed_order else (a, b)):
                        self.assertTrue(editor.flush())
                    self.assertEqual(Config(self.path).get("notes"), newest)
                    self.assertEqual(self.config.get("notes"), newest)
                    self.assertEqual(a.recovery_path.read_text(encoding="utf-8"), older)
                    self.assertFalse(a._dirty)
                    self.assertIn(str(a.recovery_path), a.toolTip())
                    self.assertIn(str(a.recovery_path),
                        (self.path.parent / "eyebar.log").read_text(encoding="utf-8"))
                    self.assertFalse(list(self.path.parent.glob(".notes-recovery-*.tmp")))
                finally:
                    a.close()
                    b.close()
                    a.deleteLater()
                    b.deleteLater()
        self.assertEqual(len(list(self.path.parent.glob("notes-recovery-*.txt"))), 2)

    def test_two_failed_own_attempts_retry_without_becoming_a_conflict(self):
        fresh = "Повторяем запись только моей правки"
        self.widget.setPlainText(fresh)
        with patch.object(self.config, "save", return_value=False) as save:
            self.assertFalse(self.widget.flush())
            self.assertFalse(self.widget.flush())
            self.assertEqual(save.call_count, 2)
        self.assertTrue(self.widget._dirty)
        self.assertIsNone(self.widget.recovery_path)
        self.assertTrue(self.widget.flush())
        self.assertFalse(self.widget._dirty)
        self.assertFalse(list(self.path.parent.glob("notes-recovery-*.txt")))

    def test_failed_recovery_write_keeps_dirty_text_and_primary_for_next_retry(self):
        from eyebar.config import Config
        fresh = "Моя конфликтующая правка"
        self.widget.setPlainText(fresh)
        newest = "Сохранённая правка другого окна"
        self.config.set("notes", newest)
        with patch.object(self.config, "_atomic_write", side_effect=OSError("recovery disk full")):
            self.assertFalse(self.widget.flush())
        self.assertTrue(self.widget._dirty)
        self.assertEqual(self.widget.toPlainText(), fresh)
        self.assertIsNone(self.widget.recovery_path)
        self.assertEqual(Config(self.path).get("notes"), newest)
        self.assertFalse(self.widget._save.isActive())
        self.assertTrue(self.widget.flush())
        self.assertFalse(self.widget._dirty)
        self.assertEqual(self.widget.recovery_path.read_text(encoding="utf-8"), fresh)
        self.assertEqual(Config(self.path).get("notes"), newest)

    def test_reverting_text_after_a_failed_write_updates_in_memory_config(self):
        from eyebar.config import Config
        old = self.widget.toPlainText()
        self.widget.setPlainText("Неудачная промежуточная правка")
        with patch.object(self.config, "save", return_value=False):
            self.assertFalse(self.widget.flush())
        self.widget.setPlainText(old)
        self.assertTrue(self.widget.flush())
        self.assertFalse(self.widget._dirty)
        self.assertEqual(self.config.get("notes"), old)
        self.assertEqual(Config(self.path).get("notes"), old)


if __name__ == "__main__":
    unittest.main()
