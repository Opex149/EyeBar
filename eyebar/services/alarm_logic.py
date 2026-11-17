"""Side-effect-free alarm validation and local-time matching (no network required)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def valid_time(value: object) -> bool:
    return isinstance(value, str) and bool(_TIME.fullmatch(value))


def normalize_audio(sound: object = "default", volume: object = 80,
                    sound_path: object = "") -> dict[str, Any]:
    """Validate persisted audio options without touching the filesystem."""
    if sound not in ("default", "soft", "custom"):
        sound = "default"
    volume = max(0, min(100, volume)) if type(volume) is int else 80
    if not isinstance(sound_path, str) or len(sound_path) > 2048 or "\x00" in sound_path:
        sound_path = ""
    if sound != "custom":
        sound_path = ""
    return {"sound": sound, "sound_path": sound_path, "volume": volume}


def sanitize_alarms(raw: object) -> list[dict[str, Any]]:
    """Keep only complete, safe entries; never allow arbitrary objects in persisted settings."""
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in raw[:40]:
        if not isinstance(item, dict):
            continue
        identity, alarm_time = item.get("id"), item.get("time")
        if not (isinstance(identity, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", identity)
                and identity not in ids and valid_time(alarm_time)):
            continue
        days = item.get("days", [])
        if not isinstance(days, list):
            days = []
        days = sorted(set(day for day in days if type(day) is int and 0 <= day <= 6))
        last_date = item.get("last_date", "")
        result.append({"id": identity, "time": alarm_time, "days": days,
                       "enabled": item.get("enabled") is True,
                       "last_date": last_date if isinstance(last_date, str) and _DATE.fullmatch(last_date) else "",
                       **normalize_audio(item.get("sound", "default"), item.get("volume", 80),
                                         item.get("sound_path", ""))})
        ids.add(identity)
    return result


def should_ring(alarm: dict, now: datetime) -> bool:
    """Only ring on the matching minute while EyeBar actually runs; no catch-up after sleep."""
    if not alarm.get("enabled", False) or not valid_time(alarm.get("time")):
        return False
    if now.strftime("%H:%M") != alarm["time"]:
        return False
    days = alarm.get("days", [])
    return (not days or now.weekday() in days) and alarm.get("last_date") != now.date().isoformat()


def next_alarm_time(alarms: list[dict], now: datetime) -> datetime | None:
    best: datetime | None = None
    for alarm in alarms:
        if not alarm.get("enabled") or not valid_time(alarm.get("time")):
            continue
        hour, minute = map(int, alarm["time"].split(":"))
        for offset in range(8):
            d = now.date() + timedelta(days=offset)
            when = datetime.combine(d, datetime.min.time()).replace(hour=hour, minute=minute)
            if when <= now or (alarm.get("days") and d.weekday() not in alarm["days"]):
                continue
            if alarm.get("last_date") == d.isoformat():
                continue
            if best is None or when < best:
                best = when
            break
    return best
