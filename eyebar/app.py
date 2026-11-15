"""Контроллер приложения: связывает сервисы и окна."""
from __future__ import annotations

import sys
import random
import time
import threading
import traceback
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .config import Config
from .i18n import I18n
from .mascots import discover
from .paths import resource_dir, user_data_dir
from .services import winapi
from .services.media import MediaService
from .services.reactions import WeatherReactions
from .services.timer import CountdownTimer
from .services.weather import WeatherService
from .ui.minibar import MiniBar
from .ui.settings import SettingsDialog
from .ui.standby import StandbyWindow
from .ui.theme import STYLE, app_icon

MANUAL_EMOTION_SECONDS = 10


def report_exception(exc_type, exc, tb) -> None:
    """Печатает ошибку в консоль и дописывает её в %APPDATA%\\EyeBar\\eyebar.log."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        if sys.stderr:
            sys.stderr.write(text)
    except Exception:
        pass
    try:
        with open(user_data_dir() / "eyebar.log", "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n{text}\n")
    except OSError:
        pass


def install_excepthook() -> None:
    """Без своего хука PyQt6 аварийно завершает программу при любой ошибке в обработчике кнопки —
    окно просто пропадает без единого слова. С хуком ошибка логируется, а приложение живёт дальше."""
    sys.excepthook = report_exception
    threading.excepthook = lambda a: report_exception(a.exc_type, a.exc_value, a.exc_traceback)


class Controller(QObject):
    alertChanged = pyqtSignal(bool)

    def __init__(self, app: QApplication, sim_weather: str | None = None) -> None:
        super().__init__()
        self.app = app
        self.sim_weather = sim_weather
        self.config = Config()
        self.i18n = I18n(resource_dir() / "locales")
        if not self.i18n.set_language(str(self.config.get("language"))):
            self.config.data["language"] = "ru"
        self.mascots = discover()
        if not self.mascots:
            raise RuntimeError("No built-in mascots are available. Reinstall EyeBar.")
        self.timer = CountdownTimer(self)
        self.weather = WeatherService(self.config, self)
        self.media = MediaService(self)
        self.reactions = WeatherReactions(self)
        self.weather_failed = False
        self.alert_active = False
        self.settings_dialog: SettingsDialog | None = None
        self._idle_snooze_until = 0.0
        self._manual_emotion: str | None = None
        self._accessory = "off"
        self._was_playing = False
        self._manual_timer = QTimer(self)
        self._manual_timer.setSingleShot(True)
        self._manual_timer.setInterval(MANUAL_EMOTION_SECONDS * 1000)
        self._manual_timer.timeout.connect(lambda: self.preview_emotion(None))

        self._beeps_left = 0
        self._beep_timer = QTimer(self)
        self._beep_timer.setInterval(900)
        self._beep_timer.timeout.connect(self._beep)

        self.hotkey = winapi.GlobalHotkey(self.enter_standby)
        app.installNativeEventFilter(self.hotkey)
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(5000)
        self._idle_timer.timeout.connect(self._check_idle)

        self.minibar = MiniBar(self)
        self.standby = StandbyWindow(self)
        self._update_emotion()
        self.standby.exitRequested.connect(self.exit_standby)

        self.timer.finished.connect(self._on_timer_finished)
        self.weather.updated.connect(self._on_weather)
        self.media.updated.connect(self._on_media_emotion)
        self.reactions.changed.connect(self._on_reactions)
        self.reactions.blowAway.connect(self._on_blow)
        self._build_tray()
        self.i18n.changed.connect(self._retranslate_tray)
        app.aboutToQuit.connect(self._cleanup)

    # ---------- общее API для окон ----------
    def current_mascot(self):
        return self.mascots.get(str(self.config.get("mascot"))) or next(iter(self.mascots.values()))

    def set_mascot(self, mascot_id: str, save: bool = True) -> None:
        """Мгновенная смена персонажа во всех окнах."""
        if mascot_id in self.mascots:
            self.config.set("mascot", mascot_id, save=save)
            self.minibar.apply_settings()
            self.standby.apply_settings()

    def start_timer(self, seconds: int) -> None:
        self.dismiss_alert()
        self.timer.start(seconds)

    def stop_timer(self) -> None:
        self.dismiss_alert()
        self.timer.stop()

    def open_settings(self) -> None:
        """Show and focus the settings window, reporting startup errors visibly."""
        try:
            dlg = self.settings_dialog
            if dlg is None:
                # Keep a strong reference: the window must survive after this slot returns.
                dlg = SettingsDialog(self)
                dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
                self.settings_dialog = dlg
                self.i18n.changed.connect(dlg.retranslate)
                dlg.finished.connect(lambda _code, d=dlg: self._on_settings_closed(d))

            # Calling show() is important even when an existing dialog is hidden.
            if dlg.isMinimized():
                dlg.showNormal()
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            details = traceback.format_exc()
            report_exception(*sys.exc_info())
            QMessageBox.critical(
                self.standby if self.standby.isVisible() else
                (self.minibar if self.minibar.isVisible() else None),
                "EyeBar — Settings error",
                "Could not open the Settings window.\n\n"
                f"{details[-3000:]}\n\n"
                f"Details are saved to: {user_data_dir() / 'eyebar.log'}",
            )

    def _on_settings_closed(self, dlg: SettingsDialog) -> None:
        try:
            self.i18n.changed.disconnect(dlg.retranslate)
        except (TypeError, RuntimeError):
            pass
        if self.settings_dialog is dlg:
            self.settings_dialog = None
        dlg.deleteLater()
        self.preview_emotion(None)

    # ---------- эмоции ----------
    def preview_emotion(self, name: str | None) -> None:
        """Ручная проверка эмоции из настроек: действует несколько секунд."""
        self._manual_emotion = name
        if name:
            self._manual_timer.start()
        else:
            self._manual_timer.stop()
        self._update_emotion()

    def _on_media_emotion(self, info) -> None:
        playing = bool(info.playing)
        if playing and not self._was_playing:
            mode = str(self.config.get("music_accessory"))
            self._accessory = random.choice(("earbuds", "headphones")) if mode == "random" else mode
        elif not playing:
            self._accessory = "off"
        self._was_playing = playing
        self._update_emotion()

    def _update_emotion(self) -> None:
        if self.alert_active:
            emotion = "normal"  # тревога таймера показывает «! !»
        elif self._manual_emotion:
            emotion = self._manual_emotion
        elif self.reactions.rain_mode == "wet" and self.config.get("weather_effects"):
            emotion = "angry"  # мокнет под дождём и злится
        elif self.media.info.playing and self.config.get("emotion") == "normal":
            emotion = "dancing"  # автоматическая реакция на музыку
        else:
            emotion = str(self.config.get("emotion"))
        self.minibar.set_emotion(emotion)
        self.standby.set_emotion(emotion)
        mode = str(self.config.get("music_accessory"))
        accessory = (self._accessory if mode == "random" else mode) if self.media.info.playing else "off"
        self.minibar.set_music_accessory(accessory)
        self.standby.set_music_accessory(accessory)

    # ---------- погодные реакции ----------
    def _on_reactions(self, rain_mode: str, windy: bool) -> None:
        if not self.config.get("weather_effects"):
            rain_mode, windy = "none", False
        self.minibar.set_weather_state(rain_mode, windy)
        self.standby.set_weather_state(rain_mode, windy)
        self._update_emotion()

    def _on_blow(self) -> None:
        """Редкая пасхалка (5%): сдувает ветром. В StandBy улетает кот, иначе — мини-бар."""
        if self.standby.isVisible():
            self.standby.play_blow()
        elif self.minibar.isVisible():
            self.minibar.play_blow()

    # ---------- StandBy ----------
    def enter_standby(self) -> None:
        if not self.config.get("standby_enabled") or self.standby.isVisible():
            return
        self.minibar.hide()
        self.standby.enter()

    def exit_standby(self) -> None:
        self.standby.hide()
        self.minibar.show()
        # Otherwise StandBy reopens on the next 5-second idle tick.
        self._idle_snooze_until = time.monotonic() + 60

    def _check_idle(self) -> None:
        if (self.standby.isVisible() or
                (self.settings_dialog is not None and self.settings_dialog.isVisible()) or
                time.monotonic() < self._idle_snooze_until):
            return
        minutes = int(self.config.get("idle_minutes"))
        if minutes > 0 and winapi.idle_seconds() >= minutes * 60:
            self.enter_standby()

    # ---------- таймер и тревога ----------
    def _on_timer_finished(self) -> None:
        self.alert_active = True
        self.alertChanged.emit(True)
        self._update_emotion()
        self._beeps_left = 8
        self._beep_timer.start()
        self._beep()
        if not self.standby.isVisible():
            self.minibar.show()
            self.minibar.raise_()

    def _beep(self) -> None:
        if self._beeps_left <= 0 or not self.alert_active:
            self._beep_timer.stop()
            return
        self._beeps_left -= 1
        QApplication.beep()

    def dismiss_alert(self) -> None:
        if self.alert_active:
            self.alert_active = False
            self._beep_timer.stop()
            self.alertChanged.emit(False)
            self._update_emotion()

    def _on_weather(self, data) -> None:
        self.weather_failed = data is None
        temp_text = f"{data['temp']:+.0f}°" if data and "temp" in data else "--°"
        self.minibar.set_temperature_text(temp_text)
        self.standby.set_temperature_text(temp_text)
        if not self.sim_weather:  # при --sim-weather реальная погода реакции не трогает
            self.reactions.update(data)

    # ---------- настройки ----------
    def apply_settings(self) -> None:
        self.hotkey.unregister()
        enabled = bool(self.config.get("standby_enabled"))
        if enabled:
            self.hotkey.register(str(self.config.get("hotkey")))
            self._idle_timer.start()
        else:
            self._idle_timer.stop()
            if self.standby.isVisible():
                self.exit_standby()
        self.minibar.apply_settings()
        self.standby.apply_settings()
        self._update_emotion()
        temp = self.weather.last
        temp_text = f"{temp['temp']:+.0f}°" if temp and "temp" in temp else "--°"
        self.minibar.set_temperature_text(temp_text)
        self.standby.set_temperature_text(temp_text)
        self._on_reactions(self.reactions.rain_mode, self.reactions.windy)
        self._retranslate_tray()
        self.weather.refresh()

    # ---------- трей ----------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        menu = QMenu()
        self.act_show = menu.addAction("", lambda *_: self._show_bar())
        self.act_standby = menu.addAction("", lambda *_: self.enter_standby())
        self.act_settings = menu.addAction("", lambda *_: self.open_settings())
        menu.addSeparator()
        self.act_quit = menu.addAction("", lambda *_: self.quit())
        self.tray.setContextMenu(menu)
        self._tray_menu = menu
        self.tray.activated.connect(
            lambda reason: self._show_bar() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._retranslate_tray()

    def _retranslate_tray(self) -> None:
        t = self.i18n.t
        self.tray.setToolTip(t("app.name"))
        self.act_show.setText(t("tray.show"))
        self.act_standby.setText(t("tray.standby"))
        self.act_standby.setVisible(bool(self.config.get("standby_enabled")))
        self.act_settings.setText(t("tray.settings"))
        self.act_quit.setText(t("tray.quit"))

    def _show_bar(self) -> None:
        if self.standby.isVisible():
            self.exit_standby()
        self.minibar.show()
        self.minibar.raise_()
        self.minibar.activateWindow()

    def _cleanup(self) -> None:
        # Also runs during a regular Windows/session shutdown, not just tray Quit.
        if self.minibar._notes is not None:
            self.minibar._notes.edit.flush()
        self.standby.notes.flush()
        self.hotkey.unregister()
        self.media.stop()
        self.weather.stop()
        self.config.save()
        self.tray.hide()

    def quit(self) -> None:
        self.app.quit()

    def start(self) -> None:
        self.apply_settings()
        self.media.start()
        self.minibar.show()
        if self.sim_weather:  # проверка пасхалок: python main.py --sim-weather=umbrella
            QTimer.singleShot(1500, lambda: self.reactions.simulate(self.sim_weather))


def run(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    sim = next((a.split("=", 1)[1] for a in argv if a.startswith("--sim-weather=")), None)
    install_excepthook()
    app = QApplication(argv)
    app.setApplicationName("EyeBar")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())
    try:
        controller = Controller(app, sim_weather=sim)
        controller.start()
    except Exception:
        report_exception(*sys.exc_info())
        QMessageBox.critical(None, "EyeBar — Startup error",
                             "EyeBar could not start. See the log at:\n" +
                             str(user_data_dir() / "eyebar.log") + "\n\n" +
                             traceback.format_exc()[-2500:])
        return 1
    return app.exec()
