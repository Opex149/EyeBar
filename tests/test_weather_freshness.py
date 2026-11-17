"""Weather receipt times and failure states; HTTP and workers are always mocked."""
import json
import os
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    QApplication = None


@unittest.skipIf(QApplication is None, "PyQt6 is not installed")
class WeatherFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from eyebar.services.weather import WeatherService
        self.config = {"city": "Moscow"}
        self.service = WeatherService(self.config)
        self.service._timer.stop()
        self.events = []
        self.service.updated.connect(self.events.append)

    def tearDown(self):
        self.service.stop()

    @staticmethod
    def response(data):
        result = MagicMock()
        result.__enter__.return_value.read.return_value = json.dumps(data).encode("utf-8")
        return result

    def successful_fetch(self):
        geo = self.response({"results": [{"latitude": 55.75, "longitude": 37.62}]})
        forecast = self.response({"current": {"temperature_2m": -3.2, "weather_code": 3,
                                               "wind_speed_10m": 2.4}})
        with patch("eyebar.services.weather.urllib.request.urlopen", side_effect=[geo, forecast]) as request:
            self.service._fetch("Moscow")
        return request

    def test_success_records_real_response_time_and_version(self):
        request = self.successful_fetch()
        self.assertEqual(self.service.last["temp"], -3.2)
        self.assertIsNotNone(self.service.last_updated)
        self.assertIsNotNone(self.service.last_updated.tzinfo)
        self.assertIsNone(self.service.last_error)
        self.assertEqual(self.events[-1]["code"], 3)
        self.assertEqual(request.call_args_list[0].args[0].get_header("User-agent"), "EyeBar/1.1")

    def test_offline_clears_data_but_keeps_last_success_time(self):
        self.successful_fetch()
        receipt = self.service.last_updated
        with patch("eyebar.services.weather.urllib.request.urlopen", side_effect=URLError("offline")):
            self.service._fetch("Moscow")
        self.assertIsNone(self.service.last)
        self.assertIs(self.service.last_updated, receipt)
        self.assertEqual(self.service.last_error, "weather.error_network")
        self.assertIsNone(self.events[-1])
        self.assertFalse(self.service._working)

    def test_first_request_failure_does_not_invent_timestamp_or_temperature(self):
        with patch("eyebar.services.weather.urllib.request.urlopen", side_effect=TimeoutError()):
            self.service._fetch("Moscow")
        self.assertIsNone(self.service.last)
        self.assertIsNone(self.service.last_updated)
        self.assertEqual(self.service.last_error, "weather.error_network")

    def test_unknown_city_has_own_failure_state(self):
        with patch("eyebar.services.weather.urllib.request.urlopen", return_value=self.response({})):
            self.service._fetch("Moscow")
        self.assertIsNone(self.service.last)
        self.assertEqual(self.service.last_error, "weather.error_city")

    def test_malformed_and_nonfinite_data_is_rejected(self):
        self.service._cache["Moscow"] = (55.75, 37.62)
        for temperature in (None, float("nan"), float("inf")):
            with self.subTest(temperature=temperature):
                data = self.response({"current": {"temperature_2m": temperature, "weather_code": 0}})
                with patch("eyebar.services.weather.urllib.request.urlopen", return_value=data):
                    self.service._fetch("Moscow")
                self.assertIsNone(self.service.last)
                self.assertIsNone(self.service.last_updated)
                self.assertEqual(self.service.last_error, "weather.error_response")

    def test_refresh_uses_one_daemon_worker_and_does_not_perform_http_inline(self):
        with patch("eyebar.services.weather.threading.Thread") as thread, \
             patch("eyebar.services.weather.urllib.request.urlopen") as request:
            self.service.refresh()
            self.service.refresh()
        thread.assert_called_once()
        self.assertTrue(thread.call_args.kwargs["daemon"])
        self.assertEqual(thread.call_args.kwargs["args"], ("Moscow",))
        thread.return_value.start.assert_called_once()
        request.assert_not_called()

    def test_stale_result_triggers_current_city_fetch_without_accepting_it(self):
        self.config["city"] = "Kazan"
        with patch("eyebar.services.weather.threading.Thread") as thread:
            self.service._on_done("Moscow", {"temp": 20, "code": 0})
        self.assertIsNone(self.service.last)
        self.assertIsNone(self.service.last_updated)
        self.assertEqual(thread.call_args.kwargs["args"], ("Kazan",))
        self.assertNotIn({"temp": 20, "code": 0}, self.events)

    def test_city_change_clears_old_timestamp_even_if_worker_is_busy(self):
        self.successful_fetch()
        self.config["city"] = "Kazan"
        self.service._working = True
        with patch("eyebar.services.weather.threading.Thread") as thread:
            self.service.refresh()
        thread.assert_not_called()
        self.assertIsNone(self.service.last)
        self.assertIsNone(self.service.last_updated)
        self.assertIsNone(self.events[-1])

    def test_success_clears_failure_and_late_result_after_stop_is_ignored(self):
        self.service.last_error = "weather.error_network"
        self.successful_fetch()
        self.assertIsNone(self.service.last_error)
        self.service.stop()
        previous = (self.service.last, self.service.last_updated, len(self.events))
        self.service._on_done("Moscow", {"temp": 99, "code": 0})
        self.assertEqual((self.service.last, self.service.last_updated, len(self.events)), previous)
        with patch("eyebar.services.weather.threading.Thread") as thread:
            self.service.refresh()
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
