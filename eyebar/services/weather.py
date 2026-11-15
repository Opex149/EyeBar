"""Погода через Open-Meteo (бесплатно, без ключа)."""
from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

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
    req = urllib.request.Request(full, headers={"User-Agent": "EyeBar/2.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


class WeatherService(QObject):
    updated = pyqtSignal(object)  # dict | None
    _result = pyqtSignal(str, object)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._cache: dict[str, tuple[float, float]] = {}
        self._working = False
        self._closed = False
        self.last: dict | None = None
        self._result.connect(self._on_done)
        self._timer = QTimer(self)
        self._timer.setInterval(15 * 60 * 1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def refresh(self) -> None:
        if self._working or self._closed:
            return
        city = str(self._config.get("city")).strip()
        self._working = True
        threading.Thread(target=self._fetch, args=(city,), name="eyebar-weather",
                         daemon=True).start()

    def _fetch(self, city: str) -> None:
        data = None
        try:
            if city not in self._cache:
                geo = _get_json(GEO_URL, {"name": city, "count": 1, "language": "ru"})
                place = geo["results"][0]
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
        except Exception:
            # Always deliver a completion signal so a failed HTTP request
            # never permanently blocks future refresh attempts.
            pass
        try:
            self._result.emit(city, data)
        except RuntimeError:  # application already exited while the HTTP call was waiting
            pass

    def _on_done(self, city: str, data) -> None:
        self._working = False
        if self._closed:
            return
        if city != str(self._config.get("city")).strip():
            # A previous city's weather must not overwrite a new selection.
            self.refresh()
            return
        self.last = data
        self.updated.emit(data)

    def stop(self) -> None:
        self._closed = True
        self._timer.stop()
