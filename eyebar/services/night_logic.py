"""Pure local-time night schedule, including midnight crossing."""
from __future__ import annotations

from datetime import datetime
from .alarm_logic import valid_time


def in_night_window(now: datetime, start: str, end: str) -> bool:
    """Start inclusive, end exclusive. Equal start/end disables automatic mode."""
    if not valid_time(start) or not valid_time(end) or start == end:
        return False
    current = now.strftime("%H:%M")
    if start < end:
        return start <= current < end
    return current >= start or current < end
