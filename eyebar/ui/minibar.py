"""Режим 1 — боковой мини-бар у правого края экрана + режим «Складной кубик».

Устройство окна: у MiniBar нет собственного layout. Внутри лежат две независимые панели
фиксированного размера — полная (self.full) и кубик (self.cube) — прижатые к правому краю
окна и центрированные по вертикали. Анимация меняет только размер окна (панели «раскрываются»
из центра) и плавно перекрёстно гасит/проявляет панели.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import os
import shlex
import subprocess

from PyQt6.QtCore import (
    QEasingCurve, QFileInfo, QPauseAnimation, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize,
    QSequentialAnimationGroup, QStandardPaths, QVariantAnimation, QTimer, Qt,
)
from PyQt6.QtGui import QCursor, QGuiApplication, QPainter, QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QFileIconProvider, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QMessageBox, QMenu,
    QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from ..mascots.base import FORM_MINI
from ..services.launcher import launch
from ..services import winapi
from .glass import paint_surface
from .icons import icon
from .widgets import (
    IconText, MascotWidget, NotesEdit, NowPlayingView, timer_info, weather_info,
)

FULL_W = 288
CUBE_W, CUBE_H = 160, 178
RADIUS = 28
EDGE_GAP = 12  # отступ от края экрана по умолчанию


class NotesDialog(QDialog):
    def __init__(self, ctx) -> None:
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.ctx = ctx
        self.resize(320, 260)
        lay = QVBoxLayout(self)
        self.edit = NotesEdit(ctx, self)
        lay.addWidget(self.edit)
        ctx.i18n.changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.ctx.i18n.t("notes.title"))


class MiniBar(QWidget):
    def __init__(self, ctx) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.ctx = ctx
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.collapsed = bool(ctx.config.get("bar_collapsed"))
        self._press: QPoint | None = None  # где нажали (глобально)
        self._grab: QPoint | None = None  # смещение курсора внутри окна
        self._moved = False
        self._anim: QVariantAnimation | None = None
        self._anim_anchor: tuple[int, int] | None = None
        self._flight: QSequentialAnimationGroup | None = None
        self._flying = False
        self._notes: NotesDialog | None = None
        self._tips: list[tuple[QPushButton, str]] = []
        self._glass_phase = 0.0
        self._glass_timer = QTimer(self)
        self._glass_timer.setInterval(70)
        self._glass_timer.timeout.connect(self._tick_glass)

        self.full = QWidget(self)
        self.cube = QWidget(self)
        self._build_full()
        self._build_cube()

        ctx.i18n.changed.connect(self.retranslate)
        ctx.weather.updated.connect(lambda _d: self.refresh_labels())
        ctx.timer.tick.connect(lambda _s: self.refresh_labels())
        ctx.alertChanged.connect(self._on_alert)
        ctx.media.updated.connect(self._on_media)

        self.apply_settings()
        self.retranslate()
        self._init_geometry()

    # ------------------------------------------------------------------ сборка
    def _btn(self, icon_name: str, tip_key: str, slot, parent: QWidget, size: int = 18,
             name: str = "icon") -> QPushButton:
        b = QPushButton(parent)
        b.setObjectName(name)
        b.setIcon(icon(icon_name, size))
        b.setIconSize(QSize(size, size))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # кнопки не перехватывают фокус у других окон
        b.clicked.connect(lambda _checked=False: slot())
        self._tips.append((b, tip_key))
        return b

    def _build_full(self) -> None:
        ctx, f = self.ctx, self.full
        lay = QVBoxLayout(f)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        self.mascot = MascotWidget(ctx.current_mascot(), FORM_MINI, f)
        self.mascot.setFixedSize(104, 83)
        self.weather_w = IconText(18)
        self.timer_w = IconText(18)
        info = QVBoxLayout()
        info.setSpacing(6)
        info.addStretch(1)
        info.addWidget(self.weather_w)
        info.addWidget(self.timer_w)
        info.addStretch(1)
        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(self.mascot)
        head.addLayout(info, 1)
        self.section_status = QWidget(f)
        self.section_status.setLayout(head)
        lay.addWidget(self.section_status)

        self.now = NowPlayingView(ctx, 44, f)
        self.section_music = self.now
        lay.addWidget(self.section_music)

        self.btn_prev = self._btn("prev", "minibar.prev", lambda: ctx.media.command("prev"), f)
        self.btn_play = self._btn("play", "minibar.play", lambda: ctx.media.command("play"), f,
                                  size=20, name="iconMid")
        self.btn_next = self._btn("next", "minibar.next", lambda: ctx.media.command("next"), f)
        controls = QHBoxLayout()
        controls.setSpacing(14)
        controls.addStretch(1)
        for b in (self.btn_prev, self.btn_play, self.btn_next):
            controls.addWidget(b)
        controls.addStretch(1)
        self.section_controls = QWidget(f)
        self.section_controls.setLayout(controls)
        lay.addWidget(self.section_controls)

        self.launch_box = QWidget(f)
        self.launch_lay = QHBoxLayout(self.launch_box)
        self.launch_lay.setContentsMargins(0, 0, 0, 0)
        self.launch_lay.setSpacing(6)
        self.section_launcher = self.launch_box
        lay.addWidget(self.section_launcher)
        self.section_custom = QWidget(f)
        self.custom_layout = QGridLayout(self.section_custom)
        self.custom_layout.setContentsMargins(0, 0, 0, 0)
        self.custom_layout.setSpacing(5)
        lay.addWidget(self.section_custom)

        self.btn_timer = self._btn("timer", "minibar.timer", self._show_timer_menu, f)
        self.btn_notes = self._btn("notes", "minibar.notes", self._show_notes, f)
        self.btn_standby = self._btn("moon", "minibar.standby", ctx.enter_standby, f)
        self.btn_screenshot = self._btn("camera", "quick.screenshot", self._take_screenshot, f)
        self.btn_quick = self._btn("more", "quick.menu", self._show_quick_menu, f)
        self.btn_settings = self._btn("gear", "minibar.settings", ctx.open_settings, f)
        self.btn_collapse = self._btn("collapse", "minibar.collapse", lambda: self.set_collapsed(True), f)
        self.btn_hide = self._btn("close", "minibar.hide", self.hide, f)
        # Without a system tray the user would have no way to restore the bar.
        self.btn_hide.setEnabled(QSystemTrayIcon.isSystemTrayAvailable())
        actions = QHBoxLayout()
        actions.setSpacing(0)
        buttons = (self.btn_timer, self.btn_notes, self.btn_screenshot, self.btn_quick,
                   self.btn_standby, self.btn_settings, self.btn_collapse, self.btn_hide)
        for i, b in enumerate(buttons):
            if i:
                actions.addStretch(1)
            actions.addWidget(b)
        lay.addLayout(actions)

    def _build_cube(self) -> None:
        ctx, c = self.ctx, self.cube
        lay = QVBoxLayout(c)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(0)

        self.btn_expand = self._btn("expand", "minibar.expand", lambda: self.set_collapsed(False), c)
        top = QHBoxLayout()
        top.addStretch(1)
        top.addWidget(self.btn_expand)
        lay.addLayout(top)

        self.cube_mascot = MascotWidget(ctx.current_mascot(), FORM_MINI, c)
        self.cube_mascot.setFixedSize(138, 116)
        lay.addStretch(1)
        lay.addWidget(self.cube_mascot, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)

    # ------------------------------------------------------------------ состояние
    def apply_settings(self) -> None:
        self.btn_standby.setVisible(bool(self.ctx.config.get("standby_enabled")))
        mascot = self.ctx.current_mascot()
        self.mascot.set_mascot(mascot)
        self.cube_mascot.set_mascot(mascot)
        self._rebuild_launcher()
        self._rebuild_custom_widgets()
        self._apply_widget_layout()
        self.mascot.set_cursor_tracking(bool(self.ctx.config.get("follow_cursor")))
        self.cube_mascot.set_cursor_tracking(bool(self.ctx.config.get("follow_cursor")))
        self._refresh_sizes()
        mode = str(self.ctx.config.get("glass_mode"))
        animated = (bool(self.ctx.config.get("glass_motion"))
                    and not bool(self.ctx.config.get("glass_lite"))
                    and (mode == "liquid" or self.ctx.config.get("glass_glow") != "off"))
        if animated and self.isVisible():
            self._glass_timer.start()
        else:
            self._glass_timer.stop()
        self.update()
        if self.isVisible():
            self._apply_native_effects()
        if self.isVisible() and not self._anim and not self._flying:
            self.setGeometry(self._rect_for(self._target_size(), self._anchor()))

    def set_emotion(self, name: str) -> None:
        self.mascot.set_emotion(name)
        self.cube_mascot.set_emotion(name)

    def set_music_accessory(self, accessory: str) -> None:
        self.mascot.set_music_accessory(accessory)
        self.cube_mascot.set_music_accessory(accessory)

    def _apply_widget_layout(self) -> None:
        lay = self.full.layout()
        sections = {name: getattr(self, "section_" + name) for name in
                    ("status", "music", "controls", "launcher", "custom")}
        for name in self.ctx.config.get("widget_order"):
            widget = sections[name]
            lay.removeWidget(widget)
            lay.insertWidget(lay.count() - 1, widget)  # above the fixed action buttons
        visible = set(self.ctx.config.get("widget_visible"))
        for name, widget in sections.items():
            widget.setVisible(name in visible and (name != "custom" or bool(self.ctx.config.get("custom_widgets")))
                              and (name != "launcher" or bool([v for v in self.ctx.config.get("launcher") if v])))

    def _rebuild_custom_widgets(self) -> None:
        while self.custom_layout.count():
            item = self.custom_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for i, entry in enumerate(self.ctx.config.get("custom_widgets")):
            b = QPushButton(entry["name"][:16], self.section_custom)
            b.setObjectName("chip")
            b.setToolTip(entry["command"])
            b.clicked.connect(lambda _checked=False, c=entry["command"]: self._run_custom_command(c))
            b.setMaximumWidth(120)
            self.custom_layout.addWidget(b, i // 2, i % 2)

    def _run_custom_command(self, command: str) -> None:
        try:
            # Never execute via a shell. Commands are local user configuration.
            argv = command if os.name == "nt" else shlex.split(command)
            subprocess.Popen(argv, shell=False, close_fds=True)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "EyeBar", str(exc))

    def set_temperature_text(self, text: str) -> None:
        self.mascot.set_temperature_text(text)
        self.cube_mascot.set_temperature_text(text)

    def set_weather_state(self, rain_mode: str, windy: bool) -> None:
        self.mascot.set_weather(rain_mode, windy)
        self.cube_mascot.set_weather(rain_mode, windy)

    def _rebuild_launcher(self) -> None:
        while self.launch_lay.count():
            item = self.launch_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        paths = [p for p in (self.ctx.config.get("launcher") or []) if p]
        self.launch_box.setVisible(bool(paths))
        if not paths:
            return
        self.launch_lay.addStretch(1)
        provider = QFileIconProvider()
        for path in paths:
            b = QPushButton()
            b.setObjectName("icon")
            ico = provider.icon(QFileInfo(path))  # настоящая иконка программы
            b.setIcon(ico if not ico.isNull() else icon("apps", 18))
            b.setIconSize(QSize(20, 20))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(self.ctx.i18n.t("minibar.launch", name=Path(path).stem))
            b.clicked.connect(lambda _checked=False, p=path: self._launch_app(p))
            self.launch_lay.addWidget(b)
        self.launch_lay.addStretch(1)

    def retranslate(self) -> None:
        for b, key in self._tips:
            b.setToolTip(self.ctx.i18n.t(key))
        self._rebuild_launcher()
        self.refresh_labels()

    def refresh_labels(self) -> None:
        i18n, ctx = self.ctx.i18n, self.ctx
        self.weather_w.set(*weather_info(i18n, ctx.weather.last, ctx.weather_failed))
        self.timer_w.set(*timer_info(i18n, ctx.timer, ctx.alert_active))
        data = ctx.weather.last
        temp = f"{float(data['temp']):+.0f}°" if isinstance(data, dict) and isinstance(data.get("temp"), (int, float)) else "--°"
        self.mascot.set_temperature_text(temp)
        self.cube_mascot.set_temperature_text(temp)
        self.timer_w.setToolTip(i18n.t("timer.dismiss_hint") if ctx.alert_active else "")

    def _on_media(self, info) -> None:
        self.btn_play.setIcon(icon("pause" if info.playing else "play", 20))

    def _on_alert(self, on: bool) -> None:
        self.mascot.set_alert(on)
        self.cube_mascot.set_alert(on)
        self.refresh_labels()

    def _launch_app(self, path: str) -> None:
        if not launch(path):
            QMessageBox.warning(self, self.ctx.i18n.t("app.name"),
                                self.ctx.i18n.t("launcher.launch_failed", path=path))

    # ------------------------------------------------------------------ геометрия
    def _refresh_sizes(self) -> None:
        h = self.full.layout().sizeHint().height()
        width = max(280, min(360, int(self.ctx.config.get("bar_width") or FULL_W)))
        self.full.setFixedSize(width, h)
        self.cube.setFixedSize(CUBE_W, CUBE_H)

    def _target_size(self) -> QSize:
        return self.cube.size() if self.collapsed else self.full.size()

    def _anchor(self) -> tuple[int, int]:
        """Правый край и центр по вертикали — именно их мы сохраняем и удерживаем."""
        g = self.geometry()
        return g.right() + 1, g.center().y()

    def _rect_for(self, size: QSize, anchor: tuple[int, int]) -> QRect:
        right, cy = anchor
        screen = QGuiApplication.screenAt(QPoint(right - 1, cy)) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(max(right - size.width(), geo.left()), geo.right() + 1 - size.width())
        y = min(max(cy - size.height() // 2, geo.top()), geo.bottom() + 1 - size.height())
        return QRect(x, y, size.width(), size.height())

    def _init_geometry(self) -> None:
        saved = self.ctx.config.get("bar_anchor")
        if saved and len(saved) == 2:
            anchor = (int(saved[0]), int(saved[1]))
        else:  # по умолчанию: правый край экрана, по центру (не мешает вкладкам браузера)
            geo = QGuiApplication.primaryScreen().availableGeometry()
            anchor = (geo.right() + 1 - EDGE_GAP, geo.center().y())
        self.setGeometry(self._rect_for(self._target_size(), anchor))
        self._show_mode_panels()

    def _place_panels(self) -> None:
        for panel in (self.full, self.cube):
            panel.move(self.width() - panel.width(), (self.height() - panel.height()) // 2)

    def _show_mode_panels(self) -> None:
        self.full.setVisible(not self.collapsed)
        self.cube.setVisible(self.collapsed)
        self._place_panels()

    def resizeEvent(self, e) -> None:
        self._place_panels()
        super().resizeEvent(e)

    # ------------------------------------------------------------------ кубик
    def set_collapsed(self, flag: bool, animate: bool = True) -> None:
        if flag == self.collapsed or self._flying:
            return
        self._finish_anim()
        start = self.geometry()
        anchor = (start.right() + 1, start.center().y())
        self.collapsed = flag
        self.ctx.config.set("bar_collapsed", flag)
        end = self._rect_for(self._target_size(), anchor)
        if not self.ctx.config.get("glass_motion"):
            animate = False
        if not animate or not self.isVisible():
            self.setGeometry(end)
            self._show_mode_panels()
            return

        self.full.show()
        self.cube.show()
        eff_full, eff_cube = QGraphicsOpacityEffect(self.full), QGraphicsOpacityEffect(self.cube)
        self.full.setGraphicsEffect(eff_full)
        self.cube.setGraphicsEffect(eff_cube)

        def clamp(v: float) -> float:
            return max(0.0, min(1.0, v))

        def step(value) -> None:
            t = float(value)
            self.setGeometry(QRect(
                round(start.x() + (end.x() - start.x()) * t), round(start.y() + (end.y() - start.y()) * t),
                round(start.width() + (end.width() - start.width()) * t),
                round(start.height() + (end.height() - start.height()) * t)))
            fade_out, fade_in = clamp(1 - t * 2.6), clamp((t - 0.25) * 1.7)
            eff_full.setOpacity(fade_out if flag else fade_in)
            eff_cube.setOpacity(fade_in if flag else fade_out)

        self._anim_anchor = anchor
        anim = QVariantAnimation(self)
        anim.setDuration(260)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(step)
        anim.finished.connect(self._finish_anim)
        self._anim = anim
        anim.start()

    def _finish_anim(self) -> None:
        anim, self._anim = self._anim, None
        anchor, self._anim_anchor = self._anim_anchor, None
        if anim is not None:
            anim.stop()
            self.setGeometry(self._rect_for(self._target_size(), anchor or self._anchor()))
        self.full.setGraphicsEffect(None)
        self.cube.setGraphicsEffect(None)
        self._show_mode_panels()

    # ------------------------------------------------------------------ пасхалка: сдувает ветром
    def play_blow(self) -> None:
        """Окно (кубик или панель) уносит за правый край экрана; оно возвращается слева."""
        if not self.isVisible() or self._flying:
            return
        self._finish_anim()
        self._flying = True
        screen = (self.screen() or QGuiApplication.primaryScreen()).geometry()
        home = self.pos()
        out_right = QPoint(screen.right() + 20, home.y())
        in_left = QPoint(screen.left() - self.width() - 20, home.y())

        fly_out = QPropertyAnimation(self, b"pos")
        fly_out.setDuration(850)
        fly_out.setStartValue(home)
        fly_out.setEndValue(out_right)
        fly_out.setEasingCurve(QEasingCurve.Type.InCubic)
        fly_in = QPropertyAnimation(self, b"pos")
        fly_in.setDuration(1500)
        fly_in.setStartValue(in_left)
        fly_in.setEndValue(home)
        fly_in.setEasingCurve(QEasingCurve.Type.OutBack)  # смешной «перелёт» и возврат с отскоком

        group = QSequentialAnimationGroup(self)
        group.addAnimation(fly_out)
        group.addAnimation(QPauseAnimation(500))
        group.addAnimation(fly_in)
        group.finished.connect(lambda: self._end_blow(home))
        self._flight = group
        group.start()

    def _end_blow(self, home: QPoint) -> None:
        self.move(home)
        self._flying = False
        self._flight = None

    # ------------------------------------------------------------------ действия
    def _show_timer_menu(self) -> None:
        i18n = self.ctx.i18n
        menu = QMenu(self)
        for n in (1, 5, 10, 25):
            menu.addAction(i18n.t("timer.preset", n=n), lambda n=n: self.ctx.start_timer(n * 60))
        menu.addAction(i18n.t("timer.custom"), self._custom_timer)
        if self.ctx.timer.active:
            menu.addSeparator()
            menu.addAction(i18n.t("timer.stop"), self.ctx.stop_timer)
        menu.exec(self.btn_timer.mapToGlobal(QPoint(0, self.btn_timer.height())))

    def _custom_timer(self) -> None:
        i18n = self.ctx.i18n
        minutes, ok = QInputDialog.getInt(self, i18n.t("timer.custom.title"),
                                          i18n.t("timer.custom.label"), 10, 1, 999)
        if ok:
            self.ctx.start_timer(minutes * 60)

    def _show_quick_menu(self) -> None:
        """Additional quick tools without making the compact bar wider."""
        t = self.ctx.i18n.t
        menu = QMenu(self)
        menu.addAction(t("quick.screenshot"), self._take_screenshot)
        region = menu.addAction(t("quick.region"), lambda: self._windows_shortcut("snip"))
        region.setEnabled(os.name == "nt")
        menu.addSeparator()
        clipboard = menu.addAction(t("quick.clipboard"), lambda: self._windows_shortcut("clipboard"))
        clipboard.setEnabled(os.name == "nt")
        menu.addAction(t("quick.explorer"), self._open_explorer)
        menu.addAction(t("quick.calculator"), self._open_calculator)
        desktop = menu.addAction(t("quick.desktop"), lambda: self._windows_shortcut("desktop"))
        desktop.setEnabled(os.name == "nt")
        menu.exec(self.btn_quick.mapToGlobal(QPoint(0, self.btn_quick.height())))

    def _windows_shortcut(self, action: str) -> None:
        if not winapi.send_quick_shortcut(action):
            QMessageBox.warning(self, "EyeBar", self.ctx.i18n.t("quick.unavailable"))

    def _open_explorer(self) -> None:
        if os.name == "nt":
            self._start_tool(["explorer.exe"])
        else:
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path.home())))

    def _open_calculator(self) -> None:
        if os.name == "nt":
            self._start_tool(["calc.exe"])
        else:
            import shutil
            app = next((path for name in ("gnome-calculator", "kcalc", "qalculate-gtk")
                        if (path := shutil.which(name))), None)
            if app:
                self._start_tool([app])
            else:
                QMessageBox.warning(self, "EyeBar", self.ctx.i18n.t("quick.unavailable"))

    def _start_tool(self, argv: list[str]) -> None:
        try:
            subprocess.Popen(argv, shell=False, close_fds=True)
        except OSError as exc:
            QMessageBox.warning(self, "EyeBar", str(exc))

    def _take_screenshot(self) -> None:
        """Hide EyeBar before grabbing, then save PNG and copy it to clipboard."""
        if getattr(self, "_capturing", False):
            return
        self._capturing = True
        self._restore_after_capture = self.isVisible()
        if self._restore_after_capture:
            self.hide()
        QTimer.singleShot(280, self._finish_screenshot)

    def _finish_screenshot(self) -> None:
        try:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            if screen is None:
                raise RuntimeError(self.ctx.i18n.t("quick.capture_failed"))
            image = screen.grabWindow(0)
            if image.isNull():
                raise RuntimeError(self.ctx.i18n.t("quick.capture_failed"))
            pictures = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
            folder = Path(pictures) if pictures else Path.home() / "Pictures"
            folder = folder / "EyeBar Screenshots"
            folder.mkdir(parents=True, exist_ok=True)
            # A suffix avoids accidental overwrite on rapid consecutive captures.
            name = datetime.now().strftime("EyeBar_%Y-%m-%d_%H-%M-%S_%f.png")
            target = folder / name
            if not image.save(str(target), "PNG"):
                raise OSError(self.ctx.i18n.t("quick.capture_failed"))
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setPixmap(image)
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.ctx.tray.showMessage("EyeBar", self.ctx.i18n.t("quick.saved", path=str(target)),
                                          QSystemTrayIcon.MessageIcon.Information, 3500)
        except (OSError, RuntimeError) as exc:
            QMessageBox.warning(self, "EyeBar", str(exc))
        finally:
            self._capturing = False
            if self._restore_after_capture:
                self.show()
                self.raise_()

    def _show_notes(self) -> None:
        if self._notes is None:
            self._notes = NotesDialog(self.ctx)
        self._notes.show()
        self._notes.raise_()
        self._notes.activateWindow()

    # ------------------------------------------------------------------ рисование и мышь
    def _tick_glass(self) -> None:
        self._glass_phase += .065
        self.update()

    def _apply_native_effects(self) -> None:
        mode = self.ctx.config.get("glass_mode")
        winapi.set_window_acrylic(self, mode in ("frosted", "liquid")
                                  and not self.ctx.config.get("glass_lite"))
        winapi.set_capture_exclusion(self, bool(self.ctx.config.get("exclude_capture")))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_native_effects()
        self.apply_settings()

    def hideEvent(self, event) -> None:
        self._glass_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, e) -> None:
        p = QPainter(self)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = min(RADIUS, rect.height() / 2)
        pointer = self.mapFromGlobal(QCursor.pos())
        paint_surface(p, rect, self.ctx.config, radius, self._glass_phase, QPointF(pointer))
        p.end()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or self._flying:
            return
        if self.ctx.alert_active:
            self.ctx.dismiss_alert()
            return
        self._press = e.globalPosition().toPoint()
        self._grab = self._press - self.frameGeometry().topLeft()
        self._moved = False

    def mouseMoveEvent(self, e) -> None:
        if (self._press is None or self.ctx.config.get("bar_locked")
                or not (e.buttons() & Qt.MouseButton.LeftButton)):
            return
        pos = e.globalPosition().toPoint()
        if not self._moved and (pos - self._press).manhattanLength() > 4:
            self._moved = True
        if self._moved and self._grab is not None:
            self.move(pos - self._grab)

    def mouseReleaseEvent(self, e) -> None:
        if self._press is None:
            return
        moved, self._press, self._grab = self._moved, None, None
        if moved:
            self.ctx.config.set("bar_anchor", list(self._anchor()))
        elif self.collapsed:  # простой клик по кубику разворачивает его
            self.set_collapsed(False)
