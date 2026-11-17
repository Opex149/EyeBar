"""Погода через Open-Meteo (бесплатно, без ключа)."""
from __future__ import annotations

import json
import logging
import math
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_LOG = logging.getLogger(__name__)


class _CityNotFound(ValueError):
    pass


COMMON_RUSSIAN_CITIES = (
    "Moscow", "Saint Petersburg", "Novosibirsk", "Yekaterinburg", "Kazan",
    "Nizhny Novgorod", "Chelyabinsk", "Samara", "Omsk", "Rostov-on-Don",
    "Ufa", "Krasnoyarsk", "Perm", "Voronezh", "Volgograd", "Krasnodar",
    "Saratov", "Tyumen", "Tolyatti", "Izhevsk", "Barnaul", "Ulyanovsk",
    "Irkutsk", "Khabarovsk", "Yaroslavl", "Vladivostok", "Makhachkala",
    "Tomsk", "Orenburg", "Kemerovo", "Novokuznetsk", "Ryazan", "Astrakhan",
    "Naberezhnye Chelny", "Penza", "Lipetsk", "Tula", "Kirov", "Cheboksary",
    "Kaliningrad", "Balashikha", "Kursk", "Sevastopol", "Sochi", "Murmansk",
    "Arkhangelsk", "Yakutsk", "Vladikavkaz", "Petrozavodsk",
)

# код погоды WMO -> (ключ локализации, имя векторной иконки из ui/icons.py)
def describe(code: int) -> tuple[str, str]:
    if code == 0:
        return "weather.clear", "sun"
    if code in (1, 2, 3):
        return "weather.partly", "partly"
    if code in (45, 48):
        return "weather.fog", "fog"
    if code in (51, 53, 55, 56, 57):
        return "weather.drizzle", "rain"
    if code in (61, 63, 65, 66, 67):
        return "weather.rain", "rain"
    if code in (71, 73, 75, 77, 85, 86):
        return "weather.snow", "snow"
    if code in (80, 81, 82):
        return "weather.showers", "rain"
    if code in (95, 96, 99):
        return "weather.thunder", "thunder"
    return "weather.partly", "partly"


def _get_json(url: str, params: dict) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full, headers={"User-Agent": "EyeBar/1.1"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


class WeatherService(QObject):
    updated = pyqtSignal(object)  # dict | None
    _result = pyqtSignal(str, object, object)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._cache: dict[str, tuple[float, float]] = {}
        self._working = False
        self._closed = False
        self.last: dict | None = None
        # Local, timezone-aware receipt time of an accepted successful result.
        # Retain it on a failed refresh so the UI can report data freshness;
        # never present the previous city's time as the current city's weather.
        self.last_updated: datetime | None = None
        self.last_error: str | None = None  # localization key, not raw HTTP text
        self._city = str(self._config.get("city")).strip()
        self._result.connect(self._on_done)
        self._timer = QTimer(self)
        self._timer.setInterval(15 * 60 * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def refresh(self) -> None:
        if self._closed:
            return
        city = str(self._config.get("city")).strip()
        if city != self._city:
            self._city = city
            self.last = None
            self.last_updated = None
            self.last_error = None
            self.updated.emit(None)
        if self._working:
            return
        self._working = True
        threading.Thread(target=self._fetch, args=(city,), name="eyebar-weather",
                         daemon=True).start()

    def _fetch(self, city: str) -> None:
        data = None
        error = None
        try:
            if not city:
                raise _CityNotFound("No city selected")
            if city not in self._cache:
                geo = _get_json(GEO_URL, {"name": city, "count": 1, "language": "ru"})
                places = geo.get("results")
                if not places:
                    raise _CityNotFound("City not found")
                place = places[0]
                self._cache[city] = (place["latitude"], place["longitude"])
            lat, lon = self._cache[city]
            current = _get_json(FORECAST_URL, {
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,weather_code,wind_speed_10m,wind_gusts_10m,precipitation",
                "wind_speed_unit": "ms",
            })["current"]
            data = {
                "temp": float(current["temperature_2m"]),
                "code": int(current["weather_code"]),
                "wind": float(current.get("wind_speed_10m") or 0.0),
                "gust": float(current.get("wind_gusts_10m") or 0.0),
                "precip": float(current.get("precipitation") or 0.0),
            }
            if not all(math.isfinite(value) for value in data.values()):
                raise ValueError("Weather response contains non-finite values")
        except _CityNotFound as exc:
            error = "weather.error_city"
            _LOG.warning("Weather location %r: %s", city, exc)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = "weather.error_network"
            _LOG.warning("Weather connection for %r: %s", city, exc)
        except Exception as exc:
            error = "weather.error_response"
            _LOG.warning("Weather response for %r: %s", city, exc)
        if error is not None:
            data = None
        try:
            # Always complete, including failed HTTP requests, so refreshes
            # remain available. The GUI thread alone mutates public state.
            self._result.emit(city, data, error)
        except RuntimeError:  # application already exited while the HTTP call was waiting
            pass

    def _on_done(self, city: str, data, error: str | None = None) -> None:
        self._working = False
        if self._closed:
            return
        if city != str(self._config.get("city")).strip():
            # A previous city's weather must not overwrite a new selection.
            self.refresh()
            return
        if city != self._city:
            self._city = city
            self.last_updated = None
        self.last = data
        self.last_error = error if data is None else None
        if data is None and self.last_error is None:
            self.last_error = "weather.error_response"
        if data is not None:
            self.last_updated = datetime.now().astimezone()
        self.updated.emit(data)

    def stop(self) -> None:
        self._closed = True
        self._timer.stop()
