"""Tests for assessment helper logic (pure functions; no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.assessment import _daily_index_maxes, _hazard_level  # noqa: E402


class TestDailyIndexMaxes(unittest.TestCase):
    def test_takes_daily_max_and_skips_missing(self):
        hourly = {
            "time": ["2026-07-24T00:00", "2026-07-24T12:00", "2026-07-25T12:00"],
            "temperature_2m": [28.0, 34.0, None],           # None hour skipped
            "relative_humidity_2m": [60, 55, 50],
            "dew_point_2m": [20.0, 22.0, 21.0],
        }
        out = _daily_index_maxes(hourly)
        # Day 24 heat index is the max over its two hours; day 25 T is missing.
        self.assertIn("2026-07-24", out["heat_index_max"])
        self.assertIsNotNone(out["heat_index_max"]["2026-07-24"])
        self.assertNotIn("2026-07-25", out["heat_index_max"])


class TestHazardLevel(unittest.TestCase):
    def _day(self, **kw):
        base = {"tmax": 25, "thresholds": {"tx90": 28, "tx95": 30, "tx99": 34},
                "in_primary_event": False, "exceeds_tx90": False, "heat_index_max": 20}
        base.update(kw)
        return base

    def test_low_when_cool(self):
        self.assertEqual(_hazard_level([self._day()]), "low")

    def test_critical_above_tx99(self):
        d = self._day(tmax=35)  # > tx99=34
        self.assertEqual(_hazard_level([d]), "critical")

    def test_high_in_primary_event(self):
        d = self._day(in_primary_event=True)
        self.assertEqual(_hazard_level([d]), "high")

    def test_moderate_on_tx90_or_hi(self):
        self.assertEqual(_hazard_level([self._day(exceeds_tx90=True)]), "moderate")
        self.assertEqual(_hazard_level([self._day(heat_index_max=33)]), "moderate")


if __name__ == "__main__":
    unittest.main()
