"""Tests for the Open-Meteo forecast adapter (no network required)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.forecast import ForecastError, _validate  # noqa: E402


class TestValidate(unittest.TestCase):
    def test_missing_daily_time_is_fatal(self):
        with self.assertRaises(ForecastError):
            _validate({"daily": {}})

    def test_missing_variable_warns(self):
        payload = {"daily": {"time": ["2026-07-24"],
                             "temperature_2m_max": [30.0]}}  # min & apparent absent
        warnings = _validate(payload)
        self.assertTrue(any("temperature_2m_min" in w for w in warnings))

    def test_null_values_flagged_not_zeroed(self):
        payload = {"daily": {"time": ["2026-07-24", "2026-07-25"],
                             "temperature_2m_max": [30.0, None],
                             "temperature_2m_min": [18.0, 19.0],
                             "apparent_temperature_max": [33.0, 34.0]}}
        warnings = _validate(payload)
        self.assertTrue(any("missing value" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
