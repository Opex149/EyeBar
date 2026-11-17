"""Source-level regressions for quick tools (also runnable without Qt)."""
import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestQuickAccess(unittest.TestCase):
    def test_actions_exist_and_screenshot_is_deferred(self):
        text = (ROOT / 'eyebar/ui/minibar.py').read_text(encoding='utf-8')
        tree = ast.parse(text)
        minibar = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MiniBar')
        names = {n.name for n in minibar.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({'_take_screenshot', '_finish_screenshot', '_show_quick_menu',
                         '_windows_shortcut', '_open_explorer', '_open_calculator'} <= names)
        self.assertIn('QTimer.singleShot(280, self._finish_screenshot)', text)
        self.assertIn('QApplication.clipboard().setPixmap(image)', text)
        self.assertIn('if not image.save(str(target), "PNG")', text)

    def test_cube_patch_bigger_and_head_original_scale(self):
        text = (ROOT / 'eyebar/mascots/cyber_cat/cat.py').read_text(encoding='utf-8')
        self.assertIn('(72, 27) if mini else (39, 16)', text)
        self.assertIn('self._head(p, st, 100, 77 + 2.4 * st.sleep_phase - 2.0 * st.stretch, 1.18)', text)
        self.assertIn('self._temperature_embroidery(p, st, 100, 134, mini=True)', text)

    def test_quick_labels_bilingual(self):
        keys = {'quick.menu', 'quick.screenshot', 'quick.region', 'quick.clipboard',
                'quick.explorer', 'quick.calculator', 'quick.desktop', 'quick.saved'}
        for lang in ('ru', 'en'):
            data = json.loads((ROOT / 'locales' / f'{lang}.json').read_text(encoding='utf-8'))
            self.assertTrue(keys <= data.keys())


if __name__ == '__main__':
    unittest.main()
