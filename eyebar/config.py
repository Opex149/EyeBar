"""Настройки приложения в JSON."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from .paths import user_data_dir

LAUNCHER_SLOTS = 4

DEFAULTS: dict[str, Any] = {
    "language": "ru",
    "mascot": "cyber_cat",
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
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return
        if not isinstance(raw, dict):
            return
        # Unknown keys are preserved for forward compatibility, but malformed
        # values must never make a GUI constructor crash after an upgrade.
        self.data.update(raw)
        for key, default in DEFAULTS.items():
            value = self.data.get(key)
            if key == "bar_anchor":
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
                            ("bar_width", 280, 360)):
            self.data[key] = max(lo, min(hi, self.data[key]))
        for key, choices in (("glass_mode", ("classic", "frosted", "liquid")),
                             ("glass_glow", ("off", "ice", "mint", "lilac", "amber"))):
            if self.data[key] not in choices:
                self.data[key] = DEFAULTS[key]
        if self.data["emotion"] not in ("normal", "happy", "angry", "sleepy", "curious", "surprised", "love", "sad", "dancing"):
            self.data["emotion"] = "normal"
        if self.data["music_accessory"] not in ("random", "earbuds", "headphones", "off"):
            self.data["music_accessory"] = "random"
        if not self.data["city"].strip():
            self.data["city"] = DEFAULTS["city"]

    def save(self) -> bool:
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            self.last_save_error = None
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.last_save_error = exc
            print("EyeBar: failed to save settings:", exc)
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False

    def get(self, key: str) -> Any:
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self.data[key] = value
        if save:
            self.save()
