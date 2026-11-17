"""Upgrade migration and real controller/settings integration regressions."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eyebar.config import Config


class UpgradeConfigTests(unittest.TestCase):
    def test_old_configuration_preserves_user_choices(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            old = dict(mascot='byte_fox', notes='Мои заметки', brightness=43,
                       glass_mode='frosted', future_option={'keep': True})
            path.write_text(json.dumps(old), encoding='utf-8')
            config = Config(path)
            self.assertFalse(config.get('classic_blue_default'))
            self.assertTrue(config.get('decorative_animations'))
            self.assertEqual(config.get('standby_mascot_position'), 'center')
            config.save()
            for key, value in old.items():
                self.assertEqual(Config(path).get(key), value)

    def test_invalid_upgrade_settings_fall_back_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            path.write_text(json.dumps(dict(classic_blue_default='yes',
                                           decorative_animations=0,
                                           standby_mascot_position=['left'])))
            config = Config(path)
            self.assertFalse(config.get('classic_blue_default'))
            self.assertTrue(config.get('decorative_animations'))
            self.assertEqual(config.get('standby_mascot_position'), 'center')


@unittest.skipUnless(importlib.util.find_spec('PyQt6'), 'PyQt6 is not installed')
class UpgradeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from eyebar.app import Controller
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'config.json'
        self.path.write_text(json.dumps(dict(mascot='byte_fox', classic_blue_default=True)))
        self.weather_patch = patch('eyebar.services.weather.WeatherService.refresh')
        self.weather_patch.start()
        self.addCleanup(self.weather_patch.stop)
        with patch('eyebar.app.Config', return_value=Config(self.path)):
            self.ctx = Controller(self.app)
        self.ctx.minibar.show()
        self.app.processEvents()

    def tearDown(self):
        if self.ctx.settings_dialog:
            self.ctx.settings_dialog.reject()
        self.ctx._cleanup()
        self.ctx.timer.stop()
        self.ctx.minibar.close()
        self.ctx.standby.close()
        self.app.processEvents()
        self.weather_patch.stop()
        self.tmp.cleanup()

    def test_startup_default_does_not_lock_character_selection(self):
        self.assertEqual(set(self.ctx.mascots),
                         {'cyber_cat', 'neon_ghost', 'luna_bunny', 'byte_fox', 'classic_blue'})
        self.assertEqual(self.ctx.current_mascot().id, 'classic_blue')
        self.ctx.set_mascot('luna_bunny')
        self.assertEqual(self.ctx.current_mascot().id, 'luna_bunny')
        self.assertTrue(Config(self.path).get('classic_blue_default'))
        self.assertEqual(self.ctx.minibar.mascot.mascot.id, 'luna_bunny')
        self.assertEqual(self.ctx.standby.mascot.mascot.id, 'luna_bunny')

    def test_new_preferences_save_reopen_and_cancel(self):
        self.ctx.open_settings()
        dialog = self.ctx.settings_dialog
        dialog.classic_blue_default.setChecked(False)
        dialog.decorative_animations.setChecked(False)
        dialog.standby_mascot_position.setCurrentIndex(dialog.standby_mascot_position.findData('right'))
        dialog._save()
        saved = Config(self.path)
        self.assertFalse(saved.get('classic_blue_default'))
        self.assertFalse(saved.get('decorative_animations'))
        self.assertEqual(saved.get('standby_mascot_position'), 'right')
        self.ctx.open_settings()
        dialog = self.ctx.settings_dialog
        self.assertFalse(dialog.decorative_animations.isChecked())
        self.assertEqual(dialog.standby_mascot_position.currentData(), 'right')
        dialog.classic_blue_default.setChecked(True)
        dialog.decorative_animations.setChecked(True)
        dialog.reject()
        self.assertFalse(self.ctx.config.get('classic_blue_default'))
        self.assertFalse(self.ctx.config.get('decorative_animations'))

    def test_full_personalization_roundtrip_and_cancel_keep_saved_profile(self):
        self.ctx.open_settings()
        dialog = self.ctx.settings_dialog
        dialog.standby_profile.setCurrentIndex(dialog.standby_profile.findData('minimal'))
        dialog.standby_autohide.setChecked(False)
        for name, check in dialog.standby_cards.items():
            check.setChecked(name in ('weather', 'notes'))
        dialog.mascot_scale.setValue(120)
        dialog.backlight_brightness.setValue(42)
        dialog.animation_intensity.setValue(25)
        dialog._outline_color = '#a855f7'
        dialog._sync_mascot_preview()
        self.assertEqual(self.ctx.config.get('mascot_scale'), 100)
        dialog._save()
        reopened = Config(self.path)
        expected = dict(standby_profile='minimal', standby_autohide=False,
                        standby_cards=['weather', 'notes'], mascot_scale=120,
                        backlight_brightness=42, animation_intensity=25,
                        outline_color='#a855f7')
        for key, value in expected.items():
            self.assertEqual(reopened.get(key), value)
        self.ctx.open_settings()
        dialog = self.ctx.settings_dialog
        self.assertEqual(dialog.mascot_scale.value(), 120)
        self.assertEqual(dialog.standby_profile.currentData(), 'minimal')
        dialog.standby_profile.setCurrentIndex(dialog.standby_profile.findData('dashboard'))
        dialog.animation_intensity.setValue(0)
        dialog.reject()
        for key, value in expected.items():
            self.assertEqual(self.ctx.config.get(key), value)

    def test_reset_appearance_preserves_notes_and_character(self):
        self.ctx.config.data.update(notes='Сохранить заметку', mascot_scale=80,
                                    outline_color='#f43f5e', backlight_brightness=30)
        selected = self.ctx.current_mascot().id
        self.ctx.open_settings()
        dialog = self.ctx.settings_dialog
        dialog._reset_appearance()
        dialog._save()
        self.assertEqual(self.ctx.config.get('notes'), 'Сохранить заметку')
        self.assertEqual(self.ctx.current_mascot().id, selected)
        self.assertEqual(self.ctx.config.get('mascot_scale'), 100)
        self.assertEqual(self.ctx.config.get('outline_color'), '#38BDF8')
        self.assertEqual(self.ctx.config.get('backlight_brightness'), 100)

    def test_zero_intensity_keeps_bar_visible_across_characters_and_themes(self):
        bar = self.ctx.minibar
        self.ctx.config.data.update(animation_intensity=0, glass_glow='ice')
        for theme in ('classic', 'frosted', 'liquid'):
            self.ctx.config.set('glass_mode', theme, save=False)
            for character in self.ctx.mascots:
                with self.subTest(theme=theme, character=character):
                    self.ctx.set_mascot(character, save=False)
                    bar.set_collapsed(not bar.collapsed, animate=True)
                    self.app.processEvents()
                    self.assertTrue(bar.isVisible())
                    self.assertIsNone(bar._anim)
                    self.assertFalse(bar._glass_timer.isActive())
                    image = bar.grab().toImage()
                    self.assertGreater(image.pixelColor(image.width() // 2, image.height() // 2).alpha(), 0)
        self.ctx.enter_standby()
        self.ctx.exit_standby()
        self.assertTrue(bar.isVisible())
        self.assertFalse(bar._glass_timer.isActive())

    def test_weather_loading_and_error_are_distinct_without_fake_data(self):
        self.ctx.weather.last_error = None
        self.ctx._on_weather(None)
        self.assertFalse(self.ctx.weather_failed)
        self.ctx.weather.last_error = 'weather.error_network'
        self.ctx._on_weather(None)
        self.ctx.minibar.refresh_labels()
        self.assertTrue(self.ctx.weather_failed)
        self.assertIsNone(self.ctx.weather.last)
        self.assertIn(self.ctx.i18n.t('weather.error_network'), self.ctx.minibar.weather_w.toolTip())

    def test_cancel_rolls_back_character_even_after_an_independent_save(self):
        original = self.ctx.current_mascot().id
        self.ctx.open_settings()
        dialog = self.ctx.settings_dialog
        dialog.picker.selected.emit('neon_ghost')
        self.ctx.config.set('notes', 'Saved independently')
        dialog.reject()
        reopened = Config(self.path)
        self.assertEqual(reopened.get('mascot'), original)
        self.assertEqual(reopened.get('notes'), 'Saved independently')

    def test_disable_decoration_cancels_transitions_but_timer_and_alert_work(self):
        bar = self.ctx.minibar
        bar.set_collapsed(True, animate=True)
        self.assertIsNotNone(bar._anim)
        self.ctx.config.set('decorative_animations', False, save=False)
        bar.apply_settings()
        self.assertIsNone(bar._anim)
        self.assertFalse(bar._glass_timer.isActive())
        self.ctx.start_timer(60)
        self.assertTrue(self.ctx.timer.active)
        self.ctx._on_timer_finished()
        self.assertTrue(bar.cube_mascot.state.alert)
        self.assertFalse(bar.cube_mascot._timer.isActive())
        self.ctx.dismiss_alert()
        bar.play_blow()
        self.assertFalse(bar._flying)
        self.assertTrue(bar.isVisible())

    def test_disable_decoration_restores_flying_bar(self):
        bar = self.ctx.minibar
        home = bar.pos()
        bar.play_blow()
        self.assertTrue(bar._flying)
        bar._flight.setCurrentTime(650)
        self.ctx.config.set('decorative_animations', False, save=False)
        bar.apply_settings()
        self.assertFalse(bar._flying)
        self.assertIsNone(bar._flight)
        self.assertTrue(bar.screen().availableGeometry().intersects(bar.geometry()))
        self.assertEqual(bar.pos(), home)

    def test_transition_objects_are_released(self):
        from PyQt6.QtCore import QAbstractAnimation, QCoreApplication, QEvent
        bar = self.ctx.minibar
        initial = len(bar.findChildren(QAbstractAnimation))
        for _ in range(20):
            bar.set_collapsed(not bar.collapsed, animate=True)
            bar._anim.setCurrentTime(bar._anim.duration())
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(len(bar.findChildren(QAbstractAnimation)), initial)

    def test_real_alarm_signal_wakes_classic_blue_and_snooze_stop_remain_available(self):
        from datetime import datetime, timedelta
        self.ctx.config.set('decorative_animations', False, save=False)
        self.ctx.minibar.apply_settings()
        self.ctx.standby.apply_settings()
        now = datetime(2026, 11, 17, 7, 30)
        self.ctx.alarms.put(None, '07:30', [], enabled=True)
        with patch('eyebar.services.alarms.datetime') as clock, \
             patch.object(self.ctx.alarms, '_start_sound'):
            clock.now.return_value = now
            self.ctx.alarms._tick()
            self.app.processEvents()
            self.assertTrue(self.ctx.standby.isVisible())
            self.assertTrue(self.ctx.standby.alarm_panel.isVisible())
            self.assertTrue(self.ctx.standby.mascot.state.alert)
            self.assertEqual(self.ctx.standby.mascot.state.blink, 1.0)
            self.assertFalse(self.ctx.standby.mascot._timer.isActive())
            self.ctx.standby.btn_snooze.click()
            self.assertIsNone(self.ctx.alarms.ringing)
            self.assertFalse(self.ctx.standby.alarm_panel.isVisible())
            clock.now.return_value = now + timedelta(minutes=5)
            self.ctx.alarms._tick()
            self.assertIsNotNone(self.ctx.alarms.ringing)
            self.ctx.standby.btn_alarm_stop.click()
            self.assertIsNone(self.ctx.alarms.ringing)
            self.assertFalse(self.ctx.standby.mascot.state.alert)


if __name__ == '__main__':
    unittest.main()
