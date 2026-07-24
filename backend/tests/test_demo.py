"""Tests for demo mode + offline resilience."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services import demo  # noqa: E402
from app.services.forecast import fetch_forecast  # noqa: E402


class TestHeatwaveScenario(unittest.TestCase):
    def test_scenario_has_4day_heatwave_and_is_labelled(self):
        s = demo.heatwave_scenario()
        self.assertIn("SYNTHETIC", s["_scenario"])
        tmaxes = s["daily"]["temperature_2m_max"]
        # At least 4 consecutive days >= 36 C.
        run = maxrun = 0
        for t in tmaxes:
            run = run + 1 if t >= 36 else 0
            maxrun = max(maxrun, run)
        self.assertGreaterEqual(maxrun, 4)
        # Hourly arrays are aligned (24 * n days).
        self.assertEqual(len(s["hourly"]["time"]), 24 * len(tmaxes))

    def test_fetch_scenario_returns_synthetic_labelled(self):
        r = fetch_forecast(50.45, 30.52, scenario="heatwave")
        self.assertIn("SYNTHETIC", r.provider)
        self.assertTrue(any("SYNTHETIC" in w for w in r.warnings))
        self.assertEqual(len(r.daily["time"]), 14)


class TestOfflineSnapshot(unittest.TestCase):
    def test_snapshot_present_and_real(self):
        snap = demo.offline_snapshot()
        self.assertIsNotNone(snap, "bundled Kyiv snapshot missing")
        self.assertIn("temperature_2m_max", snap["daily"])
        self.assertIn("REAL", snap.get("_snapshot_note", ""))


if __name__ == "__main__":
    unittest.main()
