"""Тонкая обёртка над Windows API: медиа-клавиши, простой ввода, глобальный хоткей.
На других платформах всё безопасно превращается в «ничего не делать»."""
from __future__ import annotations

import sys
from typing import Callable

from PyQt6.QtCore import QAbstractNativeEventFilter, QTimer

IS_WIN = sys.platform == "win32"

VK_MEDIA = {"next": 0xB0, "prev": 0xB1, "play": 0xB3}

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def send_media_key(action: str) -> None:
    """action: 'play' | 'next' | 'prev' — реальные системные медиа-клавиши."""
    if not IS_WIN:
        return
    vk = VK_MEDIA.get(action)
    if vk:
        _user32.keybd_event(vk, 0, 0, 0)
        _user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP


def send_quick_shortcut(action: str) -> bool:
    """Windows quick access: region screenshot, clipboard history, desktop."""
    keys = {"snip": (0x5B, 0x10, 0x53),  # Win+Shift+S
            "clipboard": (0x5B, 0x56),  # Win+V
            "desktop": (0x5B, 0x44)}  # Win+D
    seq = keys.get(action)
    if not IS_WIN or seq is None:
        return False
    try:
        for key in seq:
            _user32.keybd_event(key, 0, 0, 0)
        for key in reversed(seq):
            _user32.keybd_event(key, 0, 2, 0)
        return True
    except (AttributeError, OSError):
        return False


def idle_seconds() -> float:
    if not IS_WIN:
        return 0.0
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    # GetTickCount64 avoids signed 32-bit overflow and preserves rollover of
    # LASTINPUTINFO.dwTime (which is a DWORD, even on 64-bit Windows).
    _kernel32.GetTickCount64.restype = ctypes.c_ulonglong
    current = _kernel32.GetTickCount64() & 0xFFFFFFFF
    return ((current - info.dwTime) & 0xFFFFFFFF) / 1000.0


_MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "meta": 0x8, "win": 0x8}
_SPECIAL_KEYS = {
    "space": 0x20, "tab": 0x09, "backspace": 0x08, "esc": 0x1B, "escape": 0x1B,
    "enter": 0x0D, "return": 0x0D, "home": 0x24, "end": 0x23,
    "insert": 0x2D, "ins": 0x2D, "delete": 0x2E, "del": 0x2E,
    "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}


def _parse_hotkey(seq: str) -> tuple[int, int] | None:
    mods, vk = 0, 0
    for part in seq.split(",")[0].split("+"):
        part = part.strip()
        low = part.lower()
        if low in _MODS:
            mods |= _MODS[low]
        elif len(part) == 1 and ("A" <= part.upper() <= "Z" or "0" <= part <= "9"):
            vk = ord(part.upper())
        elif low in _SPECIAL_KEYS:
            vk = _SPECIAL_KEYS[low]
        elif low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
            vk = 0x70 + int(low[1:]) - 1
        else:
            return None
    return (mods, vk) if vk else None


class GlobalHotkey(QAbstractNativeEventFilter):
    """Глобальная горячая клавиша (Windows, RegisterHotKey)."""

    WM_HOTKEY = 0x0312
    _ID = 0x4579  # произвольный id

    def __init__(self, callback: Callable[[], None]) -> None:
        super().__init__()
        self._callback = callback
        self._registered = False

    def register(self, seq: str) -> bool:
        self.unregister()
        if not IS_WIN:
            return False
        parsed = _parse_hotkey(seq)
        if not parsed:
            return False
        mods, vk = parsed
        self._registered = bool(_user32.RegisterHotKey(None, self._ID, mods | 0x4000, vk))
        return self._registered

    def unregister(self) -> None:
        if IS_WIN and self._registered:
            _user32.UnregisterHotKey(None, self._ID)
        self._registered = False

    def nativeEventFilter(self, event_type, message):
        if IS_WIN and self._registered and bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == self.WM_HOTKEY and msg.wParam == self._ID:
                QTimer.singleShot(0, self._callback)
                return True, 0
        return False, 0

# ---------- Optional Windows compositor effects ----------
# These functions intentionally do nothing on Linux/macOS and return False if
# unsupported. The software renderer in ui/glass.py is always available.
def set_window_acrylic(widget, enabled: bool) -> bool:
    """Try to turn on Windows 10/11 background blur for a native Qt window.

    This undocumented Windows compositor API may vary with OS/theme/drivers;
    it is an enhancement, not a requirement for EyeBar to work.
    """
    if not IS_WIN:
        return False
    try:
        import ctypes

        class AccentPolicy(ctypes.Structure):
            _fields_ = [("state", ctypes.c_int), ("flags", ctypes.c_int),
                        ("gradient_color", ctypes.c_uint32), ("animation_id", ctypes.c_int)]

        class CompositionData(ctypes.Structure):
            _fields_ = [("attribute", ctypes.c_int), ("data", ctypes.c_void_p),
                        ("data_size", ctypes.c_size_t)]

        setter = ctypes.windll.user32.SetWindowCompositionAttribute
        setter.argtypes = [ctypes.c_void_p, ctypes.POINTER(CompositionData)]
        setter.restype = ctypes.c_int
        policy = AccentPolicy(4 if enabled else 0, 0, 0x22000000, 0)
        data = CompositionData(19, ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
                               ctypes.sizeof(policy))
        ok = bool(setter(ctypes.c_void_p(int(widget.winId())), ctypes.byref(data)))
        if enabled and not ok:
            policy.state = 3  # less sophisticated native blur fallback
            ok = bool(setter(ctypes.c_void_p(int(widget.winId())), ctypes.byref(data)))
        return ok
    except (AttributeError, OSError, ValueError, TypeError):
        return False


def set_capture_exclusion(widget, exclude: bool) -> bool:
    """Best-effort WDA_EXCLUDEFROMCAPTURE; requires supported Windows compositor.

    When off, explicitly removes the affinity to avoid stale protection after
    reopening a window or editing settings. Other screen capture tools may
    have their own behavior, so this is not a security boundary.
    """
    if not IS_WIN:
        return False
    try:
        import ctypes
        set_affinity = ctypes.windll.user32.SetWindowDisplayAffinity
        set_affinity.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        set_affinity.restype = ctypes.c_int
        return bool(set_affinity(ctypes.c_void_p(int(widget.winId())),
                                 0x11 if exclude else 0))
    except (AttributeError, OSError, ValueError, TypeError):
        return False
