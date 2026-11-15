"""Regression tests for preferences and widget customization (no Qt required)."""
import json
import tempfile
import unittest
from pathlib import Path

from eyebar.config import Config, DEFAULTS
from eyebar.services.reaction_logic import ReactionLogic


class TestFeatureConfig(unittest.TestCase):
    def test_emotion_and_custom_widgets_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            c = Config(path)
            c.data.update(emotion='sleepy', music_accessory='random',
                          widget_order=['custom', 'music', 'status', 'controls', 'launcher'],
                          widget_visible=['custom', 'music'],
                          custom_widgets=[{'name': 'Terminal', 'command': 'cmd.exe'}])
            self.assertTrue(c.save())
            reopened = Config(path)
            self.assertEqual(reopened.get('emotion'), 'sleepy')
            self.assertEqual(reopened.get('widget_order')[0], 'custom')
            self.assertEqual(reopened.get('widget_visible'), ['custom', 'music'])
            self.assertEqual(reopened.get('custom_widgets')[0]['command'], 'cmd.exe')

    def test_invalid_widget_values_are_sanitized(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps({'emotion': 'hacked', 'music_accessory': 'bad',
                                        'widget_order': [3, 'music', 'music', 'invalid'],
                                        'widget_visible': 'status',
                                        'custom_widgets': [{'name': 'bad'}, {}, 42]}))
            c = Config(path)
            self.assertEqual(c.get('emotion'), 'normal')
            self.assertEqual(c.get('music_accessory'), 'random')
            self.assertEqual(len(c.get('widget_order')), 5)
            self.assertEqual(c.get('widget_order')[0], 'music')
            self.assertEqual(c.get('widget_visible'), DEFAULTS['widget_visible'])
            self.assertEqual(c.get('custom_widgets'), [])

    def test_feature_defaults_are_immutable_between_instances(self):
        a = Config(Path('/does-not-exist/eyebar-a.json'))
        b = Config(Path('/does-not-exist/eyebar-b.json'))
        a.data['widget_order'].reverse()
        a.data['custom_widgets'].append({'name': 'X', 'command': 'x'})
        self.assertEqual(b.get('widget_order'), DEFAULTS['widget_order'])
        self.assertEqual(b.get('custom_widgets'), [])


if __name__ == '__main__':
    unittest.main()
