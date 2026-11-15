"""Regression checks for EyeBar's pure-Python components and packaging files."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eyebar.config import Config, DEFAULTS, LAUNCHER_SLOTS
from eyebar.paths import resource_dir, resource_path
from eyebar.services.reaction_logic import ReactionLogic, is_rain, is_windy

ROOT = Path(__file__).resolve().parents[1]


class TestConfig(unittest.TestCase):
    def test_defaults_are_independent(self):
        with tempfile.TemporaryDirectory() as td:
            a = Config(Path(td) / 'one.json')
            b = Config(Path(td) / 'two.json')
            a.data['launcher'][0] = 'app.exe'
            self.assertEqual(b.get('launcher'), ['', '', '', ''])
            self.assertEqual(DEFAULTS['launcher'], ['', '', '', ''])

    def test_corrupted_config_does_not_crash_settings(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'config.json'
            f.write_text(json.dumps({
                'language': [], 'city': 3, 'brightness': 'broken',
                'glass_mode': 'unexpected', 'glass_opacity': 0,
                'glass_tint': -50, 'bar_width': 9999, 'idle_minutes': -17,
                'launcher': ['one.exe', None, {'bad': 1}],
                'bar_anchor': 'broken', 'bar_locked': 'yes',
                'unknown_future_field': {'keep': True},
            }), encoding='utf-8')
            c = Config(f)
            self.assertEqual(c.get('language'), 'ru')
            self.assertEqual(c.get('city'), DEFAULTS['city'])
            self.assertEqual(c.get('brightness'), 100)
            self.assertEqual(c.get('bar_width'), 360)
            self.assertEqual(c.get('idle_minutes'), 0)
            self.assertEqual(c.get('glass_opacity'), 40)
            self.assertEqual(c.get('glass_tint'), 20)
            self.assertEqual(c.get('glass_mode'), 'classic')
            self.assertIsNone(c.get('bar_anchor'))
            self.assertEqual(len(c.get('launcher')), LAUNCHER_SLOTS)
            self.assertEqual(c.get('launcher')[1], '')
            self.assertFalse(c.get('bar_locked'))
            self.assertEqual(c.data['unknown_future_field'], {'keep': True})

    def test_bad_json_is_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'config.json'
            f.write_text('{broken', encoding='utf-8')
            self.assertEqual(Config(f).get('mascot'), DEFAULTS['mascot'])

    def test_atomic_save_and_load(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'nested' / 'config.json'
            c = Config(f)
            c.set('city', 'Казань', save=False)
            self.assertTrue(c.save())
            self.assertEqual(Config(f).get('city'), 'Казань')
            self.assertFalse(f.with_suffix('.tmp').exists())

    def test_failed_save_is_reported_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'config.json'
            c = Config(f)
            with patch('eyebar.config.os.replace', side_effect=OSError('blocked')):
                self.assertFalse(c.save())
            self.assertIn('blocked', str(c.last_save_error))
            self.assertFalse(f.with_suffix('.tmp').exists())


class TestResourcePaths(unittest.TestCase):
    def test_source_path(self):
        self.assertEqual(resource_dir(), ROOT)
        self.assertTrue(resource_path('locales', 'ru.json').is_file())

    def test_pyinstaller_path(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(sys, '_MEIPASS', td, create=True):
                self.assertEqual(resource_dir(), Path(td))
                self.assertEqual(resource_path('assets', 'a.png'), Path(td) / 'assets' / 'a.png')


class _SequenceRandom:
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


class TestReactions(unittest.TestCase):
    def test_rain_umbrella_persists_for_episode(self):
        logic = ReactionLogic(rng=_SequenceRandom([.2, .9]))
        rainy = {'code': 61, 'wind': 0, 'gust': 0}
        self.assertTrue(logic.update(rainy).changed)
        self.assertEqual(logic.rain_mode, 'umbrella')
        self.assertFalse(logic.update(rainy).changed)
        self.assertTrue(logic.update({'code': 0}).changed)
        self.assertEqual(logic.rain_mode, 'none')
        logic.update(rainy)
        self.assertEqual(logic.rain_mode, 'wet')

    def test_wind_blows_once_per_cooldown(self):
        t = [100.0]
        logic = ReactionLogic(rng=_SequenceRandom([.01, .5]), clock=lambda: t[0])
        windy = {'code': 0, 'wind': 12, 'gust': 0}
        self.assertTrue(logic.update(windy).blow)
        self.assertFalse(logic.update(windy).blow)
        t[0] += 3601
        self.assertFalse(logic.update(windy).blow)
        self.assertTrue(is_windy(windy))
        self.assertTrue(is_rain({'code': 61}))




class TestMascots(unittest.TestCase):
    def test_builtin_mascots_are_registered(self):
        try:
            from eyebar.mascots import discover
        except ModuleNotFoundError as exc:
            self.skipTest(str(exc))
        mascots = discover()
        self.assertIn('cyber_cat', mascots)
        self.assertIn('neon_ghost', mascots)
        self.assertIn('luna_bunny', mascots)
        self.assertIn('byte_fox', mascots)

class TestBundle(unittest.TestCase):
    def test_translations_have_same_keys_and_valid_json(self):
        ru = json.loads((ROOT / 'locales' / 'ru.json').read_text(encoding='utf-8'))
        en = json.loads((ROOT / 'locales' / 'en.json').read_text(encoding='utf-8'))
        self.assertEqual(set(ru), set(en))
        for lang in (ru, en):
            self.assertIn('settings.save_error', lang)
            self.assertIn('settings.glass_style.liquid', lang)

    def test_spec_explicit_mascots_and_onefile(self):
        spec = (ROOT / 'EyeBar.spec').read_text(encoding='utf-8')
        self.assertIn('eyebar.mascots.cyber_cat.cat', spec)
        self.assertIn('eyebar.mascots.neon_ghost.ghost', spec)
        self.assertIn('eyebar.mascots.luna_bunny.bunny', spec)
        self.assertIn('eyebar.mascots.byte_fox.fox', spec)
        self.assertIn('console=False', spec)
        self.assertIn('locales', spec)


if __name__ == '__main__':
    unittest.main()
