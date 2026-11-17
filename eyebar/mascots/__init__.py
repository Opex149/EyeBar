"""Реестр талисманов. Каждый талисман — подпакет с функцией create() -> Mascot.

Чтобы добавить нового персонажа: создайте папку eyebar/mascots/<имя>/,
в __init__.py определите create(), а в locales/*.json — ключ "mascots.<id>".
"""
from __future__ import annotations

import importlib
import pkgutil

from .base import Mascot
# Static imports guarantee that PyInstaller finds built-in mascots.
from . import cyber_cat, neon_ghost, luna_bunny, byte_fox, classic_blue

_BUILTINS = (cyber_cat, neon_ghost, luna_bunny, byte_fox, classic_blue)


def discover() -> dict[str, Mascot]:
    """Register built-ins explicitly, plus source-installed optional mascots."""
    found: dict[str, Mascot] = {}
    builtin_names = {m.__name__.split('.')[-1] for m in _BUILTINS}
    for module in _BUILTINS:
        try:
            mascot = module.create()
            found[mascot.id] = mascot
        except Exception as exc:
            print(f"EyeBar: mascot {module.__name__} failed to load: {exc}")

    # Additional plugins can be discovered when installed as normal packages.
    # Frozen one-file bundles need explicit imports / hiddenimports for extras.
    for info in pkgutil.iter_modules(__path__):
        if not info.ispkg or info.name in builtin_names:
            continue
        try:
            module = importlib.import_module(f"{__name__}.{info.name}")
            if hasattr(module, "create"):
                mascot = module.create()
                found[mascot.id] = mascot
        except Exception as exc:
            print(f"EyeBar: mascot {info.name} failed to load: {exc}")
    return found
