"""Окно настроек: персонаж, проверка эмоций, основные параметры, быстрый запуск."""
from __future__ import annotations

import os

from PyQt6.QtCore import QDir, QEasingCurve, QPropertyAnimation, QRectF, QSize, QTime, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QKeySequence, QPainter
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QKeySequenceEdit, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
)

from ..config import DEFAULTS, LAUNCHER_SLOTS
from ..mascots.base import EMOTIONS, FORM_FULL
from ..services.winapi import _parse_hotkey
from ..services.weather import COMMON_RUSSIAN_CITIES
from .icons import icon
from .glass import paint_surface
from .mascot_cards import MascotPicker
from .widgets import MascotWidget



class AppearancePreview(QWidget):
    """Live, unsaved material preview; never changes the real bar until Save."""

    def __init__(self, settings: "SettingsDialog") -> None:
        super().__init__(settings)
        self.settings = settings
        self.setMinimumHeight(110)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        area = QRectF(self.rect()).adjusted(15, 7, -15, -7)
        paint_surface(p, area, self.settings._appearance_values(), 25)
        p.setPen(QColor("#F4F4F5"))
        font = p.font()
        font.setPointSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(area.adjusted(20, 0, -16, -20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "EyeBar")
        p.setPen(QColor("#A1A1AA"))
        font.setPointSize(9)
        font.setBold(False)
        p.setFont(font)
        p.drawText(area.adjusted(20, 43, -16, 0),
                   Qt.AlignmentFlag.AlignLeft, self.settings.ctx.i18n.t("settings.glass_preview"))
        p.end()


class SettingsDialog(QDialog):
    def __init__(self, ctx) -> None:
        # «поверх всех»: иначе окно скрывается ПОД мини-баром и полноэкранным StandBy,
        # которые тоже всегда сверху, и кажется, что кнопка настроек не работает
        super().__init__(None, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowCloseButtonHint)
        self.ctx = ctx
        cfg = ctx.config
        self._open_fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._open_fade.setDuration(180)
        self._open_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._initial_mascot = str(cfg.get("mascot"))
        screen_obj = QGuiApplication.primaryScreen()
        screen = screen_obj.availableGeometry() if screen_obj else None
        available_w = screen.width() if screen else 800
        available_h = screen.height() if screen else 800
        self.resize(min(620, max(320, available_w - 35)),
                    min(760, max(300, available_h - 60)))
        self.setMinimumWidth(min(560, max(320, available_w - 35)))

        # ---------- персонаж ----------
        self.sec_mascot = self._section()
        self.picker = MascotPicker(ctx, str(cfg.get("mascot")))
        self.picker.selected.connect(self._on_mascot)
        self.classic_blue_default = QCheckBox()
        self.classic_blue_default.setChecked(bool(cfg.get("classic_blue_default")))

        # ---------- эмоции (ручная проверка) ----------
        self.sec_emotions = self._section()
        self.preview = MascotWidget(ctx.current_mascot(), FORM_FULL)
        self.preview.setFixedSize(200, 160)
        self.emotion_group = QButtonGroup(self)
        self.emotion_group.setExclusive(True)
        self.emotion_btns: dict[str, QPushButton] = {}
        emo_col = QVBoxLayout()
        emo_col.setSpacing(6)
        for name in EMOTIONS:
            b = QPushButton()
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _checked=False, n=name: self._on_emotion(n))
            self.emotion_group.addButton(b)
            self.emotion_btns[name] = b
            emo_col.addWidget(b)
        selected_emo = str(cfg.get("emotion"))
        self.emotion_btns.get(selected_emo, self.emotion_btns["normal"]).setChecked(True)
        self.preview.set_emotion(selected_emo)
        self.weather_preview_buttons = {}
        weather_demo_row = QHBoxLayout()
        for demo in ("umbrella", "wet", "wind", "clear"):
            button = QPushButton()
            button.clicked.connect(lambda _checked=False, d=demo: self._demo_weather(d))
            self.weather_preview_buttons[demo] = button
            weather_demo_row.addWidget(button)
        self.emotion_hint = QLabel()
        self.emotion_hint.setObjectName("muted")
        self.emotion_hint.setWordWrap(True)
        emo_col.addWidget(self.emotion_hint)
        emo_col.addStretch(1)
        emo_row = QHBoxLayout()
        emo_row.setSpacing(16)
        emo_row.addWidget(self.preview)
        emo_row.addLayout(emo_col, 1)

        # ---------- поведение персонажа ----------
        self.music_accessory = QComboBox()
        for option in ("random", "earbuds", "headphones", "off"):
            self.music_accessory.addItem(option, option)
        self.music_accessory.setCurrentIndex(max(0, self.music_accessory.findData(cfg.get("music_accessory"))))
        self.music_accessory.currentIndexChanged.connect(self._preview_accessory)
        self._preview_accessory()
        self.follow_cursor = QCheckBox()
        self.follow_cursor.setChecked(bool(cfg.get("follow_cursor")))
        self.preview.set_cursor_tracking(self.follow_cursor.isChecked())
        self.follow_cursor.toggled.connect(self.preview.set_cursor_tracking)
        self.weather_effects = QCheckBox()
        self.weather_effects.setChecked(bool(cfg.get("weather_effects")))
        self.decorative_animations = QCheckBox()
        self.decorative_animations.setChecked(bool(cfg.get("decorative_animations")))
        self.preview.set_animations_enabled(self.decorative_animations.isChecked())
        self.decorative_animations.toggled.connect(self.preview.set_animations_enabled)
        self.animation_intensity = QSlider(Qt.Orientation.Horizontal)
        self.animation_intensity.setRange(0, 100)
        self.animation_intensity.setValue(int(cfg.get("animation_intensity")))
        self.intensity_value = QLabel()
        self.mascot_scale = QSpinBox()
        self.mascot_scale.setRange(80, 120)
        self.mascot_scale.setSuffix("%")
        self.mascot_scale.setValue(int(cfg.get("mascot_scale")))
        self.backlight_brightness = QSlider(Qt.Orientation.Horizontal)
        self.backlight_brightness.setRange(10, 100)
        self.backlight_brightness.setValue(int(cfg.get("backlight_brightness")))
        self.backlight_value = QLabel()
        self._outline_color = str(cfg.get("outline_color"))
        self.outline_color = QPushButton()
        self.outline_color.clicked.connect(self._choose_outline_color)
        self.mascot_form = QFormLayout()
        self._mascot_rows = [
            ("settings.animation_intensity", self._slider_field(self.animation_intensity, self.intensity_value)),
            ("settings.mascot_scale", self.mascot_scale),
            ("settings.outline_color", self.outline_color),
            ("settings.backlight_brightness", self._slider_field(self.backlight_brightness, self.backlight_value)),
        ]
        self._mascot_labels = []
        for _key, field in self._mascot_rows:
            label = QLabel()
            self._mascot_labels.append(label)
            self.mascot_form.addRow(label, field)
        for signal in (self.animation_intensity.valueChanged, self.mascot_scale.valueChanged,
                       self.backlight_brightness.valueChanged):
            signal.connect(self._sync_mascot_preview)
        self._sync_mascot_preview()

        # ---------- оформление оригинальной боковой панели ----------
        self.sec_appearance = self._section()
        self.glass_mode = QComboBox()
        for mode in ("classic", "frosted", "liquid"):
            self.glass_mode.addItem("", mode)
        mode_idx = self.glass_mode.findData(cfg.get("glass_mode"))
        self.glass_mode.setCurrentIndex(max(0, mode_idx))

        self.glass_opacity = QSlider(Qt.Orientation.Horizontal)
        self.glass_opacity.setRange(40, 100)
        self.glass_opacity.setValue(int(cfg.get("glass_opacity") or 100))
        self.opacity_value = QLabel()
        opacity_row = self._slider_field(self.glass_opacity, self.opacity_value)

        self.glass_tint = QSlider(Qt.Orientation.Horizontal)
        self.glass_tint.setRange(20, 100)
        self.glass_tint.setValue(int(cfg.get("glass_tint") or 70))
        self.tint_value = QLabel()
        tint_row = self._slider_field(self.glass_tint, self.tint_value)

        self.glass_glow = QComboBox()
        for name in ("off", "ice", "mint", "lilac", "amber"):
            self.glass_glow.addItem("", name)
        glow_idx = self.glass_glow.findData(cfg.get("glass_glow"))
        self.glass_glow.setCurrentIndex(max(0, glow_idx))

        self.glass_motion = QCheckBox()
        self.glass_motion.setChecked(bool(cfg.get("glass_motion")))
        self.glass_lite = QCheckBox()
        self.glass_lite.setChecked(bool(cfg.get("glass_lite")))
        self.bar_locked = QCheckBox()
        self.bar_locked.setChecked(bool(cfg.get("bar_locked")))
        self.exclude_capture = QCheckBox()
        self.exclude_capture.setChecked(bool(cfg.get("exclude_capture")))

        self.bar_width = QSpinBox()
        self.bar_width.setRange(280, 360)
        self.bar_width.setSingleStep(8)
        self.bar_width.setValue(int(cfg.get("bar_width") or 288))

        self.glass_preview = AppearancePreview(self)
        self.appearance_form = QFormLayout()
        self.appearance_form.setVerticalSpacing(10)
        self._appearance_rows = [
            ("settings.glass_mode", self.glass_mode),
            ("settings.glass_opacity", opacity_row),
            ("settings.glass_tint", tint_row),
            ("settings.glass_glow", self.glass_glow),
            ("settings.bar_width", self.bar_width),
        ]
        self._appearance_labels = []
        for _key, field in self._appearance_rows:
            label = QLabel()
            self._appearance_labels.append(label)
            self.appearance_form.addRow(label, field)
        for check in (self.glass_motion, self.glass_lite, self.bar_locked, self.exclude_capture):
            self.appearance_form.addRow(check)
        self.appearance_hint = QLabel()
        self.appearance_hint.setObjectName("muted")
        self.appearance_hint.setWordWrap(True)
        self.reset_appearance = QPushButton()
        self.reset_appearance.clicked.connect(self._reset_appearance)
        self.reset_appearance.setMaximumWidth(240)
        for widget, signal in (
            (self.glass_mode, self.glass_mode.currentIndexChanged),
            (self.glass_glow, self.glass_glow.currentIndexChanged),
            (self.glass_opacity, self.glass_opacity.valueChanged),
            (self.glass_tint, self.glass_tint.valueChanged),
            (self.bar_width, self.bar_width.valueChanged),
            (self.glass_motion, self.glass_motion.toggled),
            (self.glass_lite, self.glass_lite.toggled),
        ):
            signal.connect(self._sync_appearance)
        self._sync_appearance()

        # ---------- основные ----------
        self.sec_general = self._section()
        self.standby = QCheckBox()
        self.standby.setChecked(bool(cfg.get("standby_enabled")))
        self.language = QComboBox()
        self.hotkey = QKeySequenceEdit(QKeySequence(str(cfg.get("hotkey"))))
        if hasattr(self.hotkey, "setMaximumSequenceLength"):
            self.hotkey.setMaximumSequenceLength(1)
        self.idle = QSpinBox()
        self.idle.setRange(0, 240)
        self.idle.setValue(int(cfg.get("idle_minutes")))
        self.city = QComboBox()
        self.city.setEditable(True)
        self.city.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.city.addItems(COMMON_RUSSIAN_CITIES)
        current_city = str(cfg.get("city"))
        if self.city.findText(current_city) < 0:
            self.city.addItem(current_city)
        self.city.setCurrentText(current_city)

        self.general_form = QFormLayout()
        self.general_form.setVerticalSpacing(10)
        self.general_form.addRow(self.standby)
        self.standby_mascot_position = QComboBox()
        for position in ("left", "center", "right"):
            self.standby_mascot_position.addItem("", position)
        self.standby_mascot_position.setCurrentIndex(max(
            0, self.standby_mascot_position.findData(cfg.get("standby_mascot_position"))))
        self.standby_profile = QComboBox()
        for profile in ("classic", "minimal", "dashboard"):
            self.standby_profile.addItem("", profile)
        self.standby_profile.setCurrentIndex(max(0, self.standby_profile.findData(cfg.get("standby_profile"))))
        self.standby_autohide = QCheckBox()
        self.standby_autohide.setChecked(bool(cfg.get("standby_autohide")))
        self.standby_cards = {}
        self.standby_cards_row = QWidget()
        cards_layout = QHBoxLayout(self.standby_cards_row)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        for name in ("weather", "music", "timer", "notes"):
            check = QCheckBox()
            check.setChecked(name in cfg.get("standby_cards"))
            self.standby_cards[name] = check
            cards_layout.addWidget(check)
        self._general_rows = [("settings.language", self.language), ("settings.hotkey", self.hotkey),
                              ("settings.idle", self.idle), ("settings.city", self.city),
                              ("settings.standby_mascot_position", self.standby_mascot_position),
                              ("settings.standby_profile", self.standby_profile),
                              ("settings.standby_cards", self.standby_cards_row)]
        self._general_labels = []
        for _key, widget in self._general_rows:
            label = QLabel()
            self._general_labels.append(label)
            self.general_form.addRow(label, widget)
        self.general_form.addRow(self.standby_autohide)

        # ---------- будильники / ночной режим ----------
        self.sec_night = self._section()
        self.btn_alarms = QPushButton()
        self.btn_alarms.clicked.connect(lambda _checked=False: ctx.open_alarms())
        self.night_auto = QCheckBox()
        self.night_auto.setChecked(bool(cfg.get("night_auto")))
        self.night_start = QTimeEdit()
        self.night_start.setDisplayFormat("HH:mm")
        self.night_start.setTime(QTime.fromString(str(cfg.get("night_start")), "HH:mm"))
        self.night_end = QTimeEdit()
        self.night_end.setDisplayFormat("HH:mm")
        self.night_end.setTime(QTime.fromString(str(cfg.get("night_end")), "HH:mm"))
        self.night_power = QCheckBox()
        self.night_power.setChecked(bool(cfg.get("night_power_enabled")))
        self.night_hint = QLabel()
        self.night_hint.setWordWrap(True)
        self.night_hint.setObjectName("muted")
        self.night_form = QFormLayout()
        self.night_form.addRow(self.night_auto)
        self.night_start_lbl = QLabel()
        self.night_end_lbl = QLabel()
        self.night_form.addRow(self.night_start_lbl, self.night_start)
        self.night_form.addRow(self.night_end_lbl, self.night_end)
        self.night_form.addRow(self.night_power)

        # ---------- быстрый запуск ----------
        self.sec_launcher = self._section()
        saved = list(cfg.get("launcher") or [])
        saved += [""] * (LAUNCHER_SLOTS - len(saved))
        self.launch_edits: list[QLineEdit] = []
        self._browse_btns: list[QPushButton] = []
        self.launcher_form = QFormLayout()
        self.launcher_form.setVerticalSpacing(8)
        self._launcher_rows: list[tuple[int, QWidget]] = []
        self._launcher_labels = []
        for i in range(LAUNCHER_SLOTS):
            edit = QLineEdit(saved[i])
            edit.setReadOnly(True)
            browse = QPushButton()
            browse.clicked.connect(lambda _checked=False, e=edit: self._browse(e))
            clear = QPushButton()
            clear.setObjectName("icon")
            clear.setIcon(icon("close", 14))
            clear.setIconSize(QSize(14, 14))
            clear.clicked.connect(lambda _checked=False, e=edit: e.clear())
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(edit, 1)
            h.addWidget(browse)
            h.addWidget(clear)
            self.launch_edits.append(edit)
            self._browse_btns.append(browse)
            self._launcher_rows.append((i + 1, row))
            label = QLabel()
            self._launcher_labels.append(label)
            self.launcher_form.addRow(label, row)

        # ---------- виджеты ----------
        self.sec_widgets = self._section()
        self.widget_hint = QLabel()
        self.widget_hint.setWordWrap(True)
        self.widget_hint.setObjectName("muted")
        self.widget_list = QListWidget()
        self.widget_list.setMinimumHeight(175)
        self.widget_list.setMaximumHeight(220)
        self.widget_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.widget_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.widget_list.setToolTip("Drag to reorder / Перетащите для изменения порядка")
        visible = set(cfg.get("widget_visible"))
        for name in cfg.get("widget_order"):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
            item.setCheckState(Qt.CheckState.Checked if name in visible else Qt.CheckState.Unchecked)
            self.widget_list.addItem(item)
        self.widget_up = QPushButton("↑")
        self.widget_down = QPushButton("↓")
        self.widget_up.clicked.connect(lambda: self._move_widget(-1))
        self.widget_down.clicked.connect(lambda: self._move_widget(1))
        widget_buttons = QHBoxLayout()
        widget_buttons.addWidget(self.widget_up)
        widget_buttons.addWidget(self.widget_down)
        widget_buttons.addStretch()
        self.custom_list = QListWidget()
        self.custom_list.setMaximumHeight(115)
        for entry in cfg.get("custom_widgets"):
            item = QListWidgetItem(entry["name"] + " — " + entry["command"])
            item.setData(Qt.ItemDataRole.UserRole, dict(entry))
            self.custom_list.addItem(item)
        self.custom_name = QLineEdit()
        self.custom_command = QLineEdit()
        self.custom_add = QPushButton()
        self.custom_remove = QPushButton()
        self.custom_add.clicked.connect(self._add_custom)
        self.custom_remove.clicked.connect(self._remove_custom)
        custom_buttons = QHBoxLayout()
        custom_buttons.addWidget(self.custom_add)
        custom_buttons.addWidget(self.custom_remove)
        custom_form = QFormLayout()
        self.custom_name_label = QLabel()
        self.custom_command_label = QLabel()
        custom_form.addRow(self.custom_name_label, self.custom_name)
        custom_form.addRow(self.custom_command_label, self.custom_command)

        # ---------- прокручиваемое содержимое ----------
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(4, 0, 12, 0)
        cl.setSpacing(8)
        cl.addWidget(self.sec_appearance)
        cl.addWidget(self.glass_preview)
        cl.addLayout(self.appearance_form)
        cl.addWidget(self.appearance_hint)
        cl.addWidget(self.reset_appearance)
        cl.addSpacing(8)
        cl.addWidget(self.sec_mascot)
        cl.addWidget(self.picker)
        cl.addWidget(self.classic_blue_default)
        cl.addSpacing(8)
        cl.addWidget(self.sec_emotions)
        cl.addLayout(emo_row)
        cl.addLayout(weather_demo_row)
        cl.addWidget(self.follow_cursor)
        cl.addWidget(self.weather_effects)
        cl.addWidget(self.decorative_animations)
        cl.addLayout(self.mascot_form)
        self.music_accessory_label = QLabel()
        cl.addWidget(self.music_accessory_label)
        cl.addWidget(self.music_accessory)
        cl.addSpacing(8)
        cl.addWidget(self.sec_widgets)
        cl.addWidget(self.widget_hint)
        cl.addWidget(self.widget_list)
        cl.addLayout(widget_buttons)
        cl.addWidget(self.custom_list)
        cl.addLayout(custom_form)
        cl.addLayout(custom_buttons)
        cl.addSpacing(8)
        cl.addWidget(self.sec_general)
        cl.addLayout(self.general_form)
        cl.addSpacing(8)
        cl.addWidget(self.sec_night)
        cl.addWidget(self.btn_alarms)
        cl.addLayout(self.night_form)
        cl.addWidget(self.night_hint)
        cl.addSpacing(8)
        cl.addWidget(self.sec_launcher)
        cl.addLayout(self.launcher_form)
        cl.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)

        self.btn_save = QPushButton()
        self.btn_cancel = QPushButton()
        self.btn_save.clicked.connect(lambda _checked=False: self._save())
        self.btn_cancel.clicked.connect(lambda _checked=False: self.reject())
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_save)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 12, 16)
        lay.setSpacing(12)
        lay.addWidget(scroll, 1)
        lay.addLayout(buttons)

        self.standby.toggled.connect(self._sync_enabled)
        self._sync_enabled(self.standby.isChecked())
        self._fill_languages()
        self.retranslate()

    @staticmethod
    def _section() -> QLabel:
        lbl = QLabel()
        lbl.setObjectName("section")
        return lbl

    @staticmethod
    def _slider_field(slider: QSlider, value: QLabel) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(slider, 1)
        value.setMinimumWidth(45)
        layout.addWidget(value)
        return container

    def _appearance_values(self) -> dict:
        return {
            "glass_mode": self.glass_mode.currentData(),
            "glass_opacity": self.glass_opacity.value(),
            "glass_tint": self.glass_tint.value(),
            "glass_glow": self.glass_glow.currentData(),
            "glass_motion": self.glass_motion.isChecked(),
            "glass_lite": self.glass_lite.isChecked(),
        }

    def _sync_appearance(self, *_args) -> None:
        self.opacity_value.setText(f"{self.glass_opacity.value()}%")
        self.tint_value.setText(f"{self.glass_tint.value()}%")
        self.glass_tint.setEnabled(self.glass_mode.currentData() != "classic")
        self.glass_preview.update()

    def _reset_appearance(self, *_args) -> None:
        self.glass_mode.setCurrentIndex(self.glass_mode.findData(DEFAULTS["glass_mode"]))
        self.glass_opacity.setValue(DEFAULTS["glass_opacity"])
        self.glass_tint.setValue(DEFAULTS["glass_tint"])
        self.glass_glow.setCurrentIndex(self.glass_glow.findData(DEFAULTS["glass_glow"]))
        self.glass_motion.setChecked(DEFAULTS["glass_motion"])
        self.glass_lite.setChecked(DEFAULTS["glass_lite"])
        self.bar_width.setValue(DEFAULTS["bar_width"])
        self.bar_locked.setChecked(DEFAULTS["bar_locked"])
        self.exclude_capture.setChecked(DEFAULTS["exclude_capture"])
        self.animation_intensity.setValue(DEFAULTS["animation_intensity"])
        self.mascot_scale.setValue(DEFAULTS["mascot_scale"])
        self.backlight_brightness.setValue(DEFAULTS["backlight_brightness"])
        self._outline_color = DEFAULTS["outline_color"]
        self._sync_mascot_preview()
        self._sync_appearance()

    def _choose_outline_color(self, *_args) -> None:
        color = QColorDialog.getColor(QColor(self._outline_color), self,
                                      self.ctx.i18n.t("settings.outline_color"))
        if color.isValid():
            self._outline_color = color.name()
            self._sync_mascot_preview()

    def _sync_mascot_preview(self, *_args) -> None:
        self.intensity_value.setText(f"{self.animation_intensity.value()}%")
        self.backlight_value.setText(f"{self.backlight_brightness.value()}%")
        self.outline_color.setText(self._outline_color.upper())
        self.outline_color.setStyleSheet(f"border: 1px solid {self._outline_color};")
        self.preview.set_animation_intensity(self.animation_intensity.value())
        self.preview.set_appearance(self.mascot_scale.value(), self._outline_color,
                                    self.backlight_brightness.value())

    def _sync_enabled(self, on: bool) -> None:
        self.hotkey.setEnabled(on)
        self.idle.setEnabled(on)
        self.standby_mascot_position.setEnabled(on)
        self.standby_profile.setEnabled(on)
        self.standby_cards_row.setEnabled(on)
        self.standby_autohide.setEnabled(on)

    def _fill_languages(self) -> None:
        self.language.clear()
        for code, name in self.ctx.i18n.available():
            self.language.addItem(name, code)
        idx = self.language.findData(self.ctx.config.get("language"))
        self.language.setCurrentIndex(max(0, idx))

    def _on_mascot(self, mascot_id: str) -> None:
        """Выбор персонажа применяется сразу — в один клик, без перезапуска."""
        self.picker.set_current(mascot_id)
        # Preview immediately, but do not persist until Save is clicked.
        self.ctx.set_mascot(mascot_id, save=False)
        self.preview.set_mascot(self.ctx.current_mascot())

    def _on_emotion(self, name: str) -> None:
        """Показывает эмоцию в окне предпросмотра и на живых маскотах (на ~10 секунд)."""
        self.preview.set_emotion(name)
        self.ctx.preview_emotion(None if name == "normal" else name)

    def _preview_accessory(self, *_args) -> None:
        mode = self.music_accessory.currentData()
        self.preview.set_music_accessory("earbuds" if mode == "random" else mode)

    def _demo_weather(self, mode: str) -> None:
        rain_mode = mode if mode in ("umbrella", "wet") else "none"
        self.preview.set_weather(rain_mode, mode == "wind")
        if mode == "wet":
            self.preview.set_emotion("angry")
        elif mode == "clear":
            name = next((name for name, btn in self.emotion_btns.items() if btn.isChecked()), "normal")
            self.preview.set_emotion(name)

    def _move_widget(self, delta: int) -> None:
        current = self.widget_list.currentRow()
        target = current + delta
        if current < 0 or not 0 <= target < self.widget_list.count():
            return
        item = self.widget_list.takeItem(current)
        self.widget_list.insertItem(target, item)
        self.widget_list.setCurrentRow(target)

    def _add_custom(self) -> None:
        name = self.custom_name.text().strip()
        command = self.custom_command.text().strip()
        if not name or not command:
            QMessageBox.warning(self, "EyeBar", "Введите название и команду / Enter name and command")
            return
        if self.custom_list.count() >= 12:
            QMessageBox.warning(self, "EyeBar", "Maximum 12 custom widgets")
            return
        entry = {"name": name[:35], "command": command[:1500]}
        item = QListWidgetItem(entry["name"] + " — " + entry["command"])
        item.setData(Qt.ItemDataRole.UserRole, entry)
        self.custom_list.addItem(item)
        self.custom_name.clear()
        self.custom_command.clear()

    def _remove_custom(self) -> None:
        row = self.custom_list.currentRow()
        if row >= 0:
            self.custom_list.takeItem(row)

    def _browse(self, edit: QLineEdit) -> None:
        t = self.ctx.i18n.t
        start = os.path.dirname(edit.text()) if edit.text() else ""
        path, _ = QFileDialog.getOpenFileName(self, t("settings.file_dialog"), start,
                                              t("settings.file_filter"))
        if path:
            edit.setText(QDir.toNativeSeparators(path))

    def retranslate(self) -> None:
        t = self.ctx.i18n.t
        self.setWindowTitle(t("settings.title"))
        self.sec_mascot.setText(t("settings.section.mascot").upper())
        self.sec_emotions.setText(t("settings.section.emotions").upper())
        self.sec_general.setText(t("settings.section.general").upper())
        self.sec_night.setText(t("night.section").upper())
        self.btn_alarms.setText(t("alarm.manage"))
        self.night_auto.setText(t("night.auto"))
        self.night_start_lbl.setText(t("night.start"))
        self.night_end_lbl.setText(t("night.end"))
        self.night_power.setText(t("night.power"))
        self.night_hint.setText(t("night.hint"))
        self.sec_appearance.setText(t("settings.section.appearance").upper())
        for (key, _widget), label in zip(self._appearance_rows, self._appearance_labels):
            label.setText(t(key))
        for i in range(self.glass_mode.count()):
            key = self.glass_mode.itemData(i)
            self.glass_mode.setItemText(i, t("settings.glass_style." + key))
        for i in range(self.glass_glow.count()):
            key = self.glass_glow.itemData(i)
            self.glass_glow.setItemText(i, t("settings.glow." + key))
        self.glass_motion.setText(t("settings.glass_motion"))
        self.glass_lite.setText(t("settings.glass_lite"))
        self.bar_locked.setText(t("settings.bar_locked"))
        self.exclude_capture.setText(t("settings.exclude_capture"))
        self.appearance_hint.setText(t("settings.glass_hint"))
        self.reset_appearance.setText(t("settings.reset_appearance"))
        self.glass_preview.update()
        self.sec_launcher.setText(t("settings.section.launcher").upper())
        for name, btn in self.emotion_btns.items():
            btn.setText(t(f"emotions.{name}"))
        self.emotion_hint.setText(t("settings.emotions_hint"))
        self.follow_cursor.setText(t("settings.follow_cursor"))
        self.weather_effects.setText(t("settings.weather_effects"))
        self.classic_blue_default.setText(t("settings.classic_blue_default"))
        self.classic_blue_default.setToolTip(t("settings.classic_blue_default_hint"))
        self.decorative_animations.setText(t("settings.decorative_animations"))
        for (key, _field), label in zip(self._mascot_rows, self._mascot_labels):
            label.setText(t(key))
        for i in range(self.standby_profile.count()):
            self.standby_profile.setItemText(i, t("settings.profile." + self.standby_profile.itemData(i)))
        self.standby_autohide.setText(t("settings.standby_autohide"))
        for name, check in self.standby_cards.items():
            check.setText(t({"weather": "standby.weather", "music": "standby.media",
                             "timer": "standby.timer", "notes": "notes.title"}[name]))
        for i in range(self.standby_mascot_position.count()):
            position = self.standby_mascot_position.itemData(i)
            self.standby_mascot_position.setItemText(i, t("settings.mascot_position." + position))
        self.music_accessory_label.setText(t("settings.music_accessory"))
        for mode, btn in self.weather_preview_buttons.items():
            btn.setText(t("settings.weather_demo." + mode))
        for i in range(self.music_accessory.count()):
            option = self.music_accessory.itemData(i)
            self.music_accessory.setItemText(i, t("settings.music_accessory." + option))
        self.sec_widgets.setText(t("settings.section.widgets").upper())
        self.widget_hint.setText(t("settings.widgets_hint"))
        for i in range(self.widget_list.count()):
            item = self.widget_list.item(i)
            item.setText(t("settings.widget." + item.data(Qt.ItemDataRole.UserRole)))
        self.custom_name_label.setText(t("settings.custom_name"))
        self.custom_command_label.setText(t("settings.custom_command"))
        self.custom_add.setText(t("settings.custom_add"))
        self.custom_remove.setText(t("settings.custom_remove"))
        self.standby.setText(t("settings.standby_enabled"))
        for (key, _widget), label in zip(self._general_rows, self._general_labels):
            label.setText(t(key))
        for (n, _row), label in zip(self._launcher_rows, self._launcher_labels):
            label.setText(t("settings.launcher", n=n))
        if self.city.lineEdit() is not None:
            self.city.lineEdit().setPlaceholderText(t("settings.city_placeholder"))
        self.idle.setSpecialValueText(t("settings.idle_off"))
        self.idle.setSuffix(t("settings.idle_suffix"))
        for b in self._browse_btns:
            b.setText(t("settings.browse"))
        self.btn_save.setText(t("settings.save"))
        self.btn_cancel.setText(t("settings.cancel"))
        self.picker.retranslate()

    def reject(self) -> None:
        # Cancel and the window close button both undo unsaved mascot changes.
        changed = self.ctx.config.get("mascot") != self._initial_mascot
        self.ctx.set_mascot(self._initial_mascot, save=False)
        if changed:
            # Notes, brightness or alarms may have saved the shared config while
            # the live character preview was active. Roll that preview back too.
            self.ctx.config.save()
        self.ctx.preview_emotion(None)
        super().reject()

    def _save(self) -> None:
        cfg = self.ctx.config
        seq = self.hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        shortcut = seq.split(",")[0].strip() or DEFAULTS["hotkey"]
        if self.standby.isChecked() and _parse_hotkey(shortcut) is None:
            QMessageBox.warning(self, self.ctx.i18n.t("settings.title"),
                                self.ctx.i18n.t("settings.hotkey_invalid"))
            self.hotkey.setFocus()
            return
        # This is an explicit, informed opt-in, not a silent power plan change.
        if self.night_power.isChecked() and not cfg.get("night_power_enabled"):
            reply = QMessageBox.question(self, self.ctx.i18n.t("night.power_title"),
                                         self.ctx.i18n.t("night.power_confirm"),
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                self.night_power.setChecked(False)
        before = cfg.data.copy()
        cfg.data.update({
            "mascot": str(cfg.get("mascot")),
            "classic_blue_default": self.classic_blue_default.isChecked(),
            "decorative_animations": self.decorative_animations.isChecked(),
            "standby_mascot_position": self.standby_mascot_position.currentData(),
            "animation_intensity": self.animation_intensity.value(),
            "mascot_scale": self.mascot_scale.value(),
            "outline_color": self._outline_color,
            "backlight_brightness": self.backlight_brightness.value(),
            "standby_profile": self.standby_profile.currentData(),
            "standby_cards": [name for name, check in self.standby_cards.items() if check.isChecked()],
            "standby_autohide": self.standby_autohide.isChecked(),
            "emotion": next((name for name, btn in self.emotion_btns.items() if btn.isChecked()), "normal"),
            "music_accessory": self.music_accessory.currentData(),
            "follow_cursor": self.follow_cursor.isChecked(),
            "weather_effects": self.weather_effects.isChecked(),
            "widget_order": [self.widget_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.widget_list.count())],
            "widget_visible": [self.widget_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.widget_list.count()) if self.widget_list.item(i).checkState() == Qt.CheckState.Checked],
            "custom_widgets": [self.custom_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.custom_list.count())],
            "standby_enabled": self.standby.isChecked(),
            "night_auto": self.night_auto.isChecked(),
            "night_start": self.night_start.time().toString("HH:mm"),
            "night_end": self.night_end.time().toString("HH:mm"),
            "night_power_enabled": self.night_power.isChecked(),
            "language": self.language.currentData(),
            "hotkey": shortcut,
            "idle_minutes": self.idle.value(),
            "city": self.city.currentText().strip() or DEFAULTS["city"],
            "launcher": [e.text() for e in self.launch_edits],
            "glass_mode": self.glass_mode.currentData(),
            "glass_opacity": self.glass_opacity.value(),
            "glass_tint": self.glass_tint.value(),
            "glass_glow": self.glass_glow.currentData(),
            "glass_motion": self.glass_motion.isChecked(),
            "glass_lite": self.glass_lite.isChecked(),
            "bar_width": self.bar_width.value(),
            "bar_locked": self.bar_locked.isChecked(),
            "exclude_capture": self.exclude_capture.isChecked(),
        })
        if not cfg.save():
            cfg.data = before
            QMessageBox.critical(self, self.ctx.i18n.t("settings.title"),
                                 self.ctx.i18n.t("settings.save_error") + "\n" +
                                 str(cfg.last_save_error))
            return
        if not self.ctx.i18n.set_language(str(cfg.get("language"))):
            self.ctx.i18n.set_language(DEFAULTS["language"])
        self.ctx.preview_emotion(None)
        self.ctx.apply_settings()
        self.accept()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._open_fade.stop()
        if self.ctx.config.get("decorative_animations") and self.ctx.config.get("animation_intensity") > 0:
            self._open_fade.setStartValue(0.65)
            self._open_fade.setEndValue(1.0)
            self._open_fade.start()
        else:
            self.setWindowOpacity(1.0)

    def hideEvent(self, event) -> None:
        self._open_fade.stop()
        self.setWindowOpacity(1.0)
        super().hideEvent(event)
