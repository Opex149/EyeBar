"""Локализация на внешних JSON-файлах (locales/<код>.json).

Чтобы добавить язык — положите рядом новый файл, например locales/de.json,
с ключом "_meta": {"name": "Deutsch"}. Он сразу появится в настройках.
Отсутствующие ключи берутся из ru.json, а если и там нет — показывается сам ключ.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal


class I18n(QObject):
    changed = pyqtSignal()

    def __init__(self, locales_dir: Path, default: str = "ru") -> None:
        super().__init__()
        self._dir = locales_dir
        self._default = default
        self._fallback = self._read(default)
        self._strings = self._fallback
        self.language = default

    def _read(self, code: str) -> dict[str, str]:
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", code):
            return {}
        try:
            raw = json.loads((self._dir / f"{code}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return {k: v for k, v in raw.items() if isinstance(v, str)}

    def available(self) -> list[tuple[str, str]]:
        """[(код, название на своём языке), ...]"""
        result = []
        for f in sorted(self._dir.glob("*.json")):
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError, UnicodeError):
                continue
            if not isinstance(raw, dict) or not any(isinstance(v, str) for v in raw.values()):
                continue
            meta = raw.get("_meta", {})
            name = meta.get("name") if isinstance(meta, dict) else None
            result.append((f.stem, name if isinstance(name, str) and name else f.stem))
        return result or [(self._default, self._default)]

    def set_language(self, code: str) -> bool:
        data = self._read(code)
        if not data:
            return False
        self._strings = data
        self.language = code
        self.changed.emit()
        return True

    def t(self, key: str, **kwargs) -> str:
        s = self._strings.get(key) or self._fallback.get(key) or key
        if kwargs:
            try:
                return s.format(**kwargs)
            except (KeyError, IndexError, TypeError, ValueError):
                return s
        return s
