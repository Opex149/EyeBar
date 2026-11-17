"""Compact alarm list/editor used from StandBy, quick tools and settings."""
from __future__ import annotations

from PyQt6.QtCore import QTime, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMessageBox, QPushButton, QSlider, QTimeEdit,
                             QVBoxLayout)

DAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
DAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class AlarmDialog(QDialog):
    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint)
        self.ctx = ctx
        self.engine = ctx.alarms
        self._filling = False
        screen = QGuiApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        self.resize(min(470, max(320, available.width() - 40)) if available else 470,
                    min(580, max(390, available.height() - 60)) if available else 580)
        root = QVBoxLayout(self)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)
        self.list = QListWidget()
        self.list.setMinimumHeight(80)
        self.list.setStyleSheet(
            "QListWidget { background: #18181C; color: #F4F4F5; border: 1px solid #303038;"
            "border-radius: 8px; padding: 4px; }"
            "QListWidget::item { padding: 5px; border-radius: 4px; }"
            "QListWidget::item:selected { background: #30303A; }")
        self.list.currentItemChanged.connect(self._select)
        self.list.itemChanged.connect(self._toggle)
        root.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.time_label = QLabel()
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setStyleSheet(
            "QTimeEdit { background: #202026; color: #F4F4F5; border: 1px solid #303038;"
            "border-radius: 6px; padding: 5px 8px; }")
        self.time_edit.setTime(QTime.currentTime().addSecs(300))
        row.addWidget(self.time_label)
        row.addWidget(self.time_edit, 1)
        root.addLayout(row)
        self.repeat_label = QLabel()
        root.addWidget(self.repeat_label)
        days_row = QHBoxLayout()
        self.days: list[QCheckBox] = []
        for i in range(7):
            b = QCheckBox()
            b.setChecked(True)
            days_row.addWidget(b)
            self.days.append(b)
        root.addLayout(days_row)
        audio_form = QFormLayout()
        self.sound_label = QLabel()
        self.sound = QComboBox()
        for mode in ("default", "soft", "custom"):
            self.sound.addItem("", mode)
        self.sound.currentIndexChanged.connect(self._sync_sound)
        audio_form.addRow(self.sound_label, self.sound)
        self.sound_path = QLineEdit()
        self.sound_path.setReadOnly(True)
        self.btn_sound_browse = QPushButton()
        self.btn_sound_browse.clicked.connect(self._browse_sound)
        self.sound_file_row = QHBoxLayout()
        self.sound_file_row.addWidget(self.sound_path, 1)
        self.sound_file_row.addWidget(self.btn_sound_browse)
        self.sound_file_label = QLabel()
        audio_form.addRow(self.sound_file_label, self.sound_file_row)
        self.volume_label = QLabel()
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume_value = QLabel("80%")
        self.volume.valueChanged.connect(lambda value: self.volume_value.setText(f"{value}%"))
        volume_row = QHBoxLayout()
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_value)
        audio_form.addRow(self.volume_label, volume_row)
        root.addLayout(audio_form)
        self.audio_hint = QLabel()
        self.audio_hint.setObjectName("muted")
        self.audio_hint.setWordWrap(True)
        root.addWidget(self.audio_hint)
        actions = QHBoxLayout()
        self.btn_add, self.btn_save, self.btn_delete = QPushButton(), QPushButton(), QPushButton()
        self.btn_add.clicked.connect(self._add)
        self.btn_save.clicked.connect(self._save)
        self.btn_delete.clicked.connect(self._delete)
        for btn in (self.btn_add, self.btn_save, self.btn_delete):
            actions.addWidget(btn)
        root.addLayout(actions)
        self.power_hint = QLabel()
        self.power_hint.setWordWrap(True)
        self.power_hint.setObjectName("muted")
        root.addWidget(self.power_hint)
        self.engine.changed.connect(self.populate)
        self.ctx.i18n.changed.connect(self.retranslate)
        self.retranslate()
        self.populate()

    def retranslate(self) -> None:
        t = self.ctx.i18n.t
        self.setWindowTitle(t("alarm.title"))
        self.hint.setText(t("alarm.editor_hint"))
        self.time_label.setText(t("alarm.time"))
        self.repeat_label.setText(t("alarm.repeat"))
        for i, b in enumerate(self.days):
            b.setText((DAYS if self.ctx.config.get("language") == "ru" else DAYS_EN)[i])
        self.btn_add.setText(t("alarm.add"))
        self.btn_save.setText(t("alarm.save"))
        self.btn_delete.setText(t("alarm.delete"))
        self.power_hint.setText(t("alarm.limitations"))
        self.sound_label.setText(t("alarm.sound"))
        self.sound_file_label.setText(t("alarm.sound_file"))
        self.btn_sound_browse.setText(t("alarm.browse_sound"))
        self.volume_label.setText(t("alarm.volume"))
        self.audio_hint.setText(t("alarm.audio_hint"))
        for i in range(self.sound.count()):
            self.sound.setItemText(i, t("alarm.sound." + self.sound.itemData(i)))
        self._sync_sound()
        self.populate()

    def populate(self) -> None:
        current = self.list.currentItem()
        chosen = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._filling = True
        self.list.clear()
        for alarm in self.engine.alarms:
            weekdays = alarm["days"]
            d = (", ".join((DAYS if self.ctx.config.get("language") == "ru" else DAYS_EN)[i]
                           for i in weekdays) if weekdays else self.ctx.i18n.t("alarm.once"))
            item = QListWidgetItem(f"{alarm['time']}    {d}")
            item.setData(Qt.ItemDataRole.UserRole, alarm["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if alarm["enabled"] else Qt.CheckState.Unchecked)
            self.list.addItem(item)
            if alarm["id"] == chosen:
                self.list.setCurrentItem(item)
        self._filling = False

    def _select(self, current, previous=None) -> None:
        if self._filling or current is None:
            return
        ident = current.data(Qt.ItemDataRole.UserRole)
        alarm = next((a for a in self.engine.alarms if a["id"] == ident), None)
        if alarm:
            self.time_edit.setTime(QTime.fromString(alarm["time"], "HH:mm"))
            for i, control in enumerate(self.days):
                control.setChecked(i in alarm["days"])
            self.sound.setCurrentIndex(max(0, self.sound.findData(alarm.get("sound", "default"))))
            self.sound_path.setText(alarm.get("sound_path", ""))
            self.sound_path.setToolTip(self.sound_path.text())
            self.volume.setValue(alarm.get("volume", 80))
            self._sync_sound()

    def _sync_sound(self, *_args) -> None:
        custom = self.sound.currentData() == "custom"
        self.sound_path.setEnabled(custom)
        self.btn_sound_browse.setEnabled(custom)

    def _browse_sound(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, self.ctx.i18n.t("alarm.choose_sound"), self.sound_path.text(),
            self.ctx.i18n.t("alarm.wav_filter"))
        if path:
            self.sound_path.setText(path)
            self.sound_path.setToolTip(path)

    def _toggle(self, item) -> None:
        if not self._filling:
            self.engine.set_enabled(item.data(Qt.ItemDataRole.UserRole),
                                    item.checkState() == Qt.CheckState.Checked)

    def _add(self) -> None:
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self.time_edit.setTime(QTime.currentTime().addSecs(300))
        for b in self.days:
            b.setChecked(True)
        self.sound.setCurrentIndex(0)
        self.sound_path.clear()
        self.volume.setValue(80)

    def _save(self) -> None:
        item = self.list.currentItem()
        ident = item.data(Qt.ItemDataRole.UserRole) if item else None
        time = self.time_edit.time().toString("HH:mm")
        days = [i for i, box in enumerate(self.days) if box.isChecked()]
        if self.sound.currentData() == "custom" and not self.sound_path.text():
            QMessageBox.warning(self, "EyeBar", self.ctx.i18n.t("alarm.sound_required"))
            return
        if not self.engine.put(ident, time, days, sound=self.sound.currentData(),
                               sound_path=self.sound_path.text(), volume=self.volume.value()):
            QMessageBox.warning(self, "EyeBar", self.ctx.i18n.t("alarm.save_failed"))
        else:
            # Select the newly-created alarm or keep editing the selected one.
            target = ident or self.engine.alarms[-1]["id"]
            for i in range(self.list.count()):
                item = self.list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == target:
                    self.list.setCurrentItem(item)
                    break

    def _delete(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            if QMessageBox.question(self, self.ctx.i18n.t("alarm.title"),
                                    self.ctx.i18n.t("alarm.delete_confirm"),
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.engine.remove(item.data(Qt.ItemDataRole.UserRole))
