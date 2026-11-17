"""Настройки приложения в JSON."""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import user_data_dir
from .services.alarm_logic import sanitize_alarms, valid_time

LAUNCHER_SLOTS = 4
CONFIG_VERSION = 1
BACKUP_COUNT = 3
_LOG = logging.getLogger(__name__)

DEFAULTS: dict[str, Any] = {
    "config_version": CONFIG_VERSION,
    "language": "ru",
    "mascot": "cyber_cat",
    "classic_blue_default": False,  # select Classic Blue on application startup
    "decorative_animations": True,
    "animation_intensity": 100,
    "mascot_scale": 100,
    "outline_color": "#38BDF8",
    "backlight_brightness": 100,
    "standby_mascot_position": "center",  # left | center | right
    "standby_profile": "classic",  # classic | minimal | dashboard
    "standby_cards": ["weather", "music", "timer", "notes"],
    "standby_autohide": True,
    "emotion": "normal",
    "music_accessory": "random",  # random | earbuds | headphones | off
    "follow_cursor": True,
    "weather_effects": True,
    "widget_order": ["status", "music", "controls", "launcher", "custom"],
    "widget_visible": ["status", "music", "controls", "launcher", "custom"],
    "custom_widgets": [],
    "standby_enabled": True,
    "hotkey": "Alt+S",
    "idle_minutes": 0,  # 0 = не включать StandBy по бездействию
    "city": "Moscow",
    "brightness": 100,  # 10..100
    "notes": "",
    # v1.1: persistent local alarms and reversible night mode
    "alarms": [],
    "night_auto": False,
    "night_start": "23:00",
    "night_end": "07:00",
    "night_power_enabled": False,
    "night_previous_scheme": "",
    "bar_anchor": None,  # [правый край, центр по вертикали] мини-бара
    "bar_collapsed": False,  # свёрнут ли в кубик
    "launcher": ["", "", "", ""],  # пути к закреплённым программам
    # Original EyeBar layout stays unchanged by default.
    "glass_mode": "classic",       # classic | frosted | liquid
    "glass_opacity": 100,         # 40..100 %, whole surface transparency
    "glass_tint": 70,             # 20..100 %, dark glass tint strength
    "glass_glow": "off",          # off | ice | mint | lilac | amber
    "glass_motion": True,         # animate decorative edge lighting and cube transition
    "glass_lite": False,         # low-cost material rendering, no OS blur
    "bar_width": 288,             # full mini-bar width, 280..360
    "bar_locked": False,         # prevent moving original side bar
    "exclude_capture": False,   # Windows 10 2004+ capture exclusion (best effort)
}


class Config:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (user_data_dir() / "config.json")
        self.data: dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.last_save_error: Exception | None = None
        self.last_backup_error: Exception | None = None
        self.recovered_from: Path | None = None
        self.load()

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.path.name + ".bak")

    @property
    def migration_backup_path(self) -> Path:
        # Keep the original upgrade input apart from rotating recovery copies.
        return self.path.with_name(self.path.name + ".pre-v1.bak")

    def _backup_paths(self) -> list[Path]:
        return [self.backup_path] + [
            self.backup_path.with_name(self.backup_path.name + f".{index}")
            for index in range(1, BACKUP_COUNT)
        ]

    @staticmethod
    def _decode(payload: bytes) -> dict[str, Any]:
        raw = json.loads(payload.decode("utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError("configuration must contain a JSON object")
        return raw

    def _log(self, level: int, message: str, error: Exception | None = None) -> None:
        detail = f"{message}: {error}" if error is not None else message
        _LOG.log(level, "%s", detail)
        # Windowed Windows builds have no console. Record recovery/save failures
        # in the same local log used by the application's exception handler.
        try:
            with (self.path.parent / "eyebar.log").open("a", encoding="utf-8") as stream:
                stream.write(f"{datetime.now().isoformat(timespec='seconds')} {detail}\n")
        except OSError:
            pass

    def load(self) -> None:
        raw = None
        self.recovered_from = None
        candidates = [self.path, *self._backup_paths(), self.migration_backup_path]
        for candidate in candidates:
            try:
                raw = self._decode(candidate.read_bytes())
            except FileNotFoundError:
                continue
            except (OSError, ValueError, UnicodeError) as exc:
                self._log(logging.WARNING, f"EyeBar: cannot read settings {candidate.name}", exc)
                continue
            if candidate != self.path:
                self.recovered_from = candidate
                self._log(logging.WARNING, f"EyeBar: settings recovered from {candidate.name}")
            break
        if raw is None:
            return
        # Unknown keys are preserved for forward compatibility, but malformed
        # values must never make a GUI constructor crash after an upgrade.
        self.data.update(raw)
        for key, default in DEFAULTS.items():
            value = self.data.get(key)
            if key == "alarms":
                self.data[key] = sanitize_alarms(value)
            elif key == "standby_cards":
                allowed = DEFAULTS["standby_cards"]
                if not isinstance(value, list):
                    value = list(allowed)
                self.data[key] = list(dict.fromkeys(
                    item for item in value if isinstance(item, str) and item in allowed))
            elif key == "bar_anchor":
                if not (isinstance(value, (tuple, list)) and len(value) == 2
                        and all(type(v) is int and -100000 < v < 100000 for v in value)):
                    self.data[key] = None
            elif key in ("widget_order", "widget_visible"):
                allowed = ("status", "music", "controls", "launcher", "custom")
                if not isinstance(value, list):
                    value = list(allowed)
                self.data[key] = [v for v in value if type(v) is str and v in allowed]
                self.data[key] = list(dict.fromkeys(self.data[key]))
                if key == "widget_order":
                    self.data[key] += [v for v in allowed if v not in self.data[key]]
            elif key == "custom_widgets":
                if not isinstance(value, list):
                    value = []
                self.data[key] = [{"name": v["name"][:35], "command": v["command"][:1500]}
                                  for v in value[:12] if isinstance(v, dict)
                                  and isinstance(v.get("name"), str) and v["name"].strip()
                                  and isinstance(v.get("command"), str) and v["command"].strip()]
            elif key == "launcher":
                if not isinstance(value, list):
                    value = []
                self.data[key] = [str(v) if isinstance(v, str) else "" for v in value[:LAUNCHER_SLOTS]]
                self.data[key] += [""] * (LAUNCHER_SLOTS - len(self.data[key]))
            elif isinstance(default, bool):
                if type(value) is not bool:
                    self.data[key] = default
            elif isinstance(default, int):
                if type(value) is not int:
                    self.data[key] = default
            elif isinstance(default, str):
                if not isinstance(value, str):
                    self.data[key] = default
        for key, lo, hi in (("brightness", 10, 100), ("idle_minutes", 0, 240),
                            ("glass_opacity", 40, 100), ("glass_tint", 20, 100),
                            ("bar_width", 280, 360), ("animation_intensity", 0, 100),
                            ("mascot_scale", 80, 120), ("backlight_brightness", 10, 100)):
            self.data[key] = max(lo, min(hi, self.data[key]))
        for key, choices in (("glass_mode", ("classic", "frosted", "liquid")),
                             ("glass_glow", ("off", "ice", "mint", "lilac", "amber")),
                             ("standby_mascot_position", ("left", "center", "right")),
                             ("standby_profile", ("classic", "minimal", "dashboard"))):
            if self.data[key] not in choices:
                self.data[key] = DEFAULTS[key]
        if self.data["emotion"] not in ("normal", "happy", "angry", "sleepy", "curious", "surprised", "love", "sad", "dancing"):
            self.data["emotion"] = "normal"
        if self.data["music_accessory"] not in ("random", "earbuds", "headphones", "off"):
            self.data["music_accessory"] = "random"
        for key in ("night_start", "night_end"):
            if not valid_time(self.data[key]):
                self.data[key] = DEFAULTS[key]
        if not self.data["city"].strip():
            self.data["city"] = DEFAULTS["city"]
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", self.data["outline_color"]):
            self.data["outline_color"] = DEFAULTS["outline_color"]
        # Preserve a future version marker instead of silently downgrading it.
        self.data["config_version"] = max(CONFIG_VERSION, self.data["config_version"])

    @staticmethod
    def _atomic_write(target: Path, payload: bytes) -> None:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=target.parent,
                                             prefix=f".{target.name}.", suffix=".tmp",
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = None
            # POSIX directory sync makes the rename durable. Windows does not
            # support this operation; file fsync + atomic replace still apply.
            if os.name != "nt":
                directory = None
                try:
                    directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                    os.fsync(directory)
                except OSError:
                    pass
                finally:
                    if directory is not None:
                        os.close(directory)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _store_backup(self, payload: bytes) -> None:
        """Rotate only valid JSON copies; corruption can never become a backup."""
        self._decode(payload)
        paths = self._backup_paths()
        try:
            if paths[0].read_bytes() == payload:
                return
        except FileNotFoundError:
            pass
        for index in range(len(paths) - 1, 0, -1):
            try:
                previous = paths[index - 1].read_bytes()
                self._decode(previous)
            except (OSError, ValueError, UnicodeError):
                continue
            self._atomic_write(paths[index], previous)
        self._atomic_write(paths[0], payload)

    def _protect_existing(self) -> None:
        try:
            previous = self.path.read_bytes()
        except FileNotFoundError:
            return
        try:
            raw = self._decode(previous)
        except (ValueError, UnicodeError):
            # Retain the damaged input for manual recovery; never rotate it over
            # a known-good backup. A failed archive leaves the primary intact.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            damaged = self.path.with_name(f"{self.path.name}.corrupt.{stamp}")
            self._atomic_write(damaged, previous)
            self._log(logging.WARNING, f"EyeBar: damaged settings preserved as {damaged.name}")
            return
        version = raw.get("config_version", 0)
        if (type(version) is not int or version < CONFIG_VERSION) and not self.migration_backup_path.exists():
            self._atomic_write(self.migration_backup_path, previous)
            self._log(logging.INFO, f"EyeBar: upgrade backup saved as {self.migration_backup_path.name}")
        self._store_backup(previous)

    def save(self) -> bool:
        try:
            payload = json.dumps(self.data, ensure_ascii=False, indent=2,
                                 allow_nan=False).encode("utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._protect_existing()
            self._atomic_write(self.path, payload)
            self.last_save_error = None
        except (OSError, TypeError, ValueError) as exc:
            self.last_save_error = exc
            self._log(logging.ERROR, "EyeBar: failed to save settings; previous file retained", exc)
            return False
        try:
            # Mirror the latest successful save, including first-run notes.
            # This happens after commit: a mirror failure must not claim that
            # an already committed primary write failed.
            self._store_backup(payload)
            self.last_backup_error = None
        except (OSError, TypeError, ValueError) as exc:
            self.last_backup_error = exc
            self._log(logging.WARNING, "EyeBar: settings saved but recovery copy could not be refreshed", exc)
        return True

    def get(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self.data[key] = value
        if save:
            self.save()
