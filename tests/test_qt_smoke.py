"""GUI smoke checks. Run after installing requirements.txt (offscreen Qt)."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HAS_QT = importlib.util.find_spec('PyQt6') is not None


@unittest.skipUnless(HAS_QT, 'PyQt6 is not installed in this environment')
class TestQtGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from eyebar.app import Controller
        from eyebar.config import Config
        self.tmp = tempfile.TemporaryDirectory()
        with patch('eyebar.app.Config', return_value=Config(Path(self.tmp.name) / 'config.json')):
            self.ctx = Controller(self.qt_app)

    def tearDown(self):
        self.ctx._cleanup()
        if self.ctx.settings_dialog is not None:
            self.ctx.settings_dialog.reject()
        self.ctx.minibar.close()
        self.ctx.standby.close()
        self.qt_app.processEvents()
        self.tmp.cleanup()

    def test_settings_show_and_cancel_restores_mascot(self):
        self.ctx.minibar.show()
        self.ctx.open_settings()
        self.qt_app.processEvents()
        dlg = self.ctx.settings_dialog
        self.assertIsNotNone(dlg)
        self.assertTrue(dlg.isVisible())
        old_mascot = self.ctx.config.get('mascot')
        target = 'neon_ghost' if old_mascot == 'cyber_cat' else 'cyber_cat'
        dlg.picker.selected.emit(target)
        self.assertEqual(self.ctx.config.get('mascot'), target)
        dlg.reject()
        self.assertEqual(self.ctx.config.get('mascot'), old_mascot)

    def test_settings_save_and_reopen(self):
        self.ctx.open_settings()
        dlg = self.ctx.settings_dialog
        dlg.glass_mode.setCurrentIndex(dlg.glass_mode.findData('liquid'))
        dlg.glass_opacity.setValue(65)
        dlg._save()
        self.assertEqual(self.ctx.config.get('glass_mode'), 'liquid')
        self.assertEqual(self.ctx.config.get('glass_opacity'), 65)
        self.ctx.open_settings()
        self.qt_app.processEvents()
        self.assertEqual(self.ctx.settings_dialog.glass_mode.currentData(), 'liquid')
        self.assertTrue(self.ctx.settings_dialog.isVisible())

    def test_v11_night_dimming_is_reversible(self):
        self.assertFalse(self.ctx.night.active)
        self.ctx.toggle_night()
        self.assertTrue(self.ctx.night.active)
        self.assertTrue(self.ctx.minibar.night_shade.enabled)
        self.assertTrue(self.ctx.standby._night)
        self.ctx.toggle_night()
        self.assertFalse(self.ctx.night.active)
        self.assertFalse(self.ctx.minibar.night_shade.enabled)
        self.assertFalse(self.ctx.standby._night)

    def test_v11_alarm_editor_persists(self):
        self.ctx.open_alarms()
        self.qt_app.processEvents()
        dialog = self.ctx.alarm_dialog
        self.assertIsNotNone(dialog)
        self.assertTrue(dialog.isVisible())
        dialog.time_edit.setTime(__import__('PyQt6.QtCore', fromlist=['QTime']).QTime(7, 30))
        dialog._save()
        self.assertEqual(self.ctx.alarms.alarms[-1]['time'], '07:30')
        self.assertEqual(self.ctx.config.get('alarms')[-1]['time'], '07:30')
        dialog.close()

    def test_show_bar_exits_standby(self):
        self.ctx.enter_standby()
        self.assertTrue(self.ctx.standby.isVisible())
        self.ctx._show_bar()
        self.assertFalse(self.ctx.standby.isVisible())
        self.assertTrue(self.ctx.minibar.isVisible())


if __name__ == '__main__':
    unittest.main()
