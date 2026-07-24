"""Tests for heat-stress indices against published reference values."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.heat.indices import (  # noqa: E402
    excess_heat_factor,
    heat_index,
    humidex,
    is_tropical_night,
)


class TestHeatIndex(unittest.TestCase):
    def test_nws_reference_90f_70pct(self):
        # NWS Heat Index chart: 90 degF (32.22 degC) at 70% RH ~= 105 degF (40.6 degC).
        res = heat_index(32.22, 70)
        self.assertTrue(res.in_valid_range)
        self.assertAlmostEqual(res.value, 40.6, delta=0.8)

    def test_mild_conditions_flagged_out_of_range(self):
        res = heat_index(20.0, 50)
        self.assertFalse(res.in_valid_range)
        self.assertIn("validity", res.note.lower())

    def test_rejects_bad_humidity(self):
        with self.assertRaises(ValueError):
            heat_index(30.0, 150)


class TestHumidex(unittest.TestCase):
    def test_ec_reference_30c_dew25(self):
        # Environment Canada worked example: T=30, dew=25 -> humidex ~= 42.
        res = humidex(30.0, 25.0)
        self.assertAlmostEqual(res.value, 42.0, delta=1.0)
        self.assertTrue(res.in_valid_range)


class TestTropicalNight(unittest.TestCase):
    def test_absolute_threshold(self):
        self.assertTrue(is_tropical_night(21.0))
        self.assertFalse(is_tropical_night(19.0))

    def test_local_tn90_trigger(self):
        # Below 20C absolute but above local TN90 of 17 -> still tropical.
        self.assertTrue(is_tropical_night(18.0, tn90_c=17.0))

    def test_missing_returns_none(self):
        self.assertIsNone(is_tropical_night(None))


class TestEHF(unittest.TestCase):
    def test_hot_spell_gives_positive_ehf(self):
        # 40 days of cool baseline (~18C) then a hot 3-day spell (~30C).
        series = [18.0] * 40 + [30.0, 30.0, 30.0]
        res = excess_heat_factor(series, index=len(series) - 1, t95_daily_mean=24.0)
        self.assertTrue(res.in_valid_range)
        self.assertGreater(res.value, 0)

    def test_insufficient_leadin_flagged(self):
        res = excess_heat_factor([20.0] * 10, index=9, t95_daily_mean=24.0)
        self.assertIsNone(res.value)
        self.assertFalse(res.in_valid_range)

    def test_missing_in_window_flagged(self):
        series = [18.0] * 40 + [None, 30.0, 30.0]
        res = excess_heat_factor(series, index=len(series) - 1, t95_daily_mean=24.0)
        self.assertIsNone(res.value)


if __name__ == "__main__":
    unittest.main()
