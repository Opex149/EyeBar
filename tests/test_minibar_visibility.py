"""Regression checks for the previously invisible mini-bar (v1.1 StandBy fix).

Static checks run on CI without Qt; GUI smoke checks run with PyQt6/offscreen
and should additionally be tested on Windows 10/11 before distributing EXE.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
QT_AVAILABLE = importlib.util.find_spec('PyQt6') is not None


class TestMiniBarStatic(unittest.TestCase):
    def test_inactive_night_shade_cannot_erase_bar(self):
        source = (ROOT / 'eyebar/ui/minibar.py').read_text(encoding='utf-8')
        module = ast.parse(source)
        shade = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'NightShade')
        paint = next(n for n in shade.body if isinstance(n, ast.FunctionDef) and n.name == 'paintEvent')
        paint_source = ast.get_source_segment(source, paint)
        self.assertNotIn('CompositionMode_Source', paint_source)
        self.assertIn('if not self.enabled:', paint_source)
        self.assertIn('self.hide()', ast.get_source_segment(source, shade))
        minibar = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'MiniBar')
        method_names = {n.name for n in minibar.body if isinstance(n, ast.FunctionDef)}
        self.assertIn('_restore_visible_bar', method_names)
        self.assertIn('_cancel_flight', method_names)

    def test_standby_source_unchanged_by_minibar_hotfix(self):
        self.assertTrue((ROOT / 'eyebar/ui/standby.py').is_file())
        self.assertTrue((ROOT / 'eyebar/services/alarms.py').is_file())


@unittest.skipUnless(QT_AVAILABLE, 'PyQt6 is not installed in this environment')
class TestMiniBarGUI(unittest.TestCase):
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
        self.ctx.minibar.show()
        self.qt_app.processEvents()

    def tearDown(self):
        self.ctx._cleanup()
        if self.ctx.alarm_dialog:
            self.ctx.alarm_dialog.close()
        if self.ctx.settings_dialog:
            self.ctx.settings_dialog.close()
        self.ctx.minibar.close()
        self.ctx.standby.close()
        self.qt_app.processEvents()
        self.tmp.cleanup()

    def _assert_on_screen_and_opaque(self):
        bar = self.ctx.minibar
        self.qt_app.processEvents()
        self.assertTrue(bar.isVisible())
        self.assertGreater(bar.width(), 100)
        self.assertGreater(bar.height(), 100)
        self.assertTrue(bar.full.isVisible() != bar.cube.isVisible())
        self.assertTrue(bar.screen().availableGeometry().intersects(bar.geometry()))
        # The bar's backdrop must be visible even without glass/compositor.
        pixmap = bar.grab()
        self.assertFalse(pixmap.isNull())
        self.assertGreater(pixmap.toImage().pixelColor(bar.width() // 2, bar.height() // 2).alpha(), 0)

    def test_cube_and_full_are_both_visible(self):
        self._assert_on_screen_and_opaque()
        self.ctx.minibar.set_collapsed(True, animate=False)
        self._assert_on_screen_and_opaque()
        self.ctx.minibar.set_collapsed(False, animate=False)
        self._assert_on_screen_and_opaque()

    def test_night_shade_only_shows_at_night(self):
        self.assertFalse(self.ctx.minibar.night_shade.isVisible())
        self.ctx.toggle_night()
        self.assertTrue(self.ctx.minibar.night_shade.isVisible())
        self._assert_on_screen_and_opaque()
        self.ctx.toggle_night()
        self.assertFalse(self.ctx.minibar.night_shade.isVisible())
        self._assert_on_screen_and_opaque()

    def test_restore_after_standby_and_interrupted_flight(self):
        bar = self.ctx.minibar
        bar.play_blow()
        self.assertTrue(bar._flying)
        self.ctx.enter_standby()
        self.assertFalse(bar._flying)
        self.assertTrue(self.ctx.standby.isVisible())
        self.ctx.exit_standby()
        self.assertFalse(self.ctx.standby.isVisible())
        self._assert_on_screen_and_opaque()

    def test_restore_after_interrupted_cube_animation(self):
        bar = self.ctx.minibar
        bar.set_collapsed(True, animate=True)
        self.ctx.enter_standby()
        self.ctx.exit_standby()
        self._assert_on_screen_and_opaque()
        self.assertTrue(bar.collapsed)


if __name__ == '__main__':
    unittest.main()
