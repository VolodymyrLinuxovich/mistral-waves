"""Tests for the calendar-day percentile climatology."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.heat.thresholds import (  # noqa: E402
    compute_thresholds,
    day_of_year_365,
    percentile_linear,
    smooth_circular,
)


class TestPercentile(unittest.TestCase):
    def test_linear_matches_numpy_type7(self):
        vals = [1, 2, 3, 4, 5]
        # numpy.percentile(vals, 90) == 4.6
        self.assertAlmostEqual(percentile_linear(vals, 90), 4.6, places=6)
        self.assertEqual(percentile_linear(vals, 0), 1)
        self.assertEqual(percentile_linear(vals, 100), 5)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            percentile_linear([], 90)


class TestDayOfYear(unittest.TestCase):
    def test_jan1_is_zero(self):
        self.assertEqual(day_of_year_365(date(2021, 1, 1)), 0)

    def test_feb29_maps_to_feb28(self):
        self.assertEqual(day_of_year_365(date(2024, 2, 29)),
                         day_of_year_365(date(2024, 2, 28)))

    def test_dec31(self):
        self.assertEqual(day_of_year_365(date(2021, 12, 31)), 364)


class TestClimatology(unittest.TestCase):
    def _synthetic_baseline(self):
        """CLEARLY SYNTHETIC test fixture (not real ERA5): a smooth seasonal
        sine plus a fixed per-year offset, 1991-2020, so percentiles are
        predictable. This is an algorithm fixture, not climate data."""
        import math
        obs = []
        for year in range(1991, 2021):
            d = date(year, 1, 1)
            for _ in range(365):
                doy = day_of_year_365(d)
                seasonal = 15 + 12 * math.sin(2 * math.pi * (doy - 100) / 365)
                value = seasonal + (year - 2005) * 0.05  # tiny trend
                obs.append((d, value))
                d = d + timedelta(days=1)
        return obs

    def test_summer_threshold_higher_than_winter(self):
        obs = self._synthetic_baseline()
        tx95 = compute_thresholds(obs, percentile=95, variable="tmax", window_days=15)
        summer = tx95.for_date(date(2020, 7, 15))
        winter = tx95.for_date(date(2020, 1, 15))
        self.assertIsNotNone(summer)
        self.assertIsNotNone(winter)
        self.assertGreater(summer, winter)

    def test_min_samples_leaves_none(self):
        # Only a handful of observations -> below min_samples -> None, not faked.
        obs = [(date(2000, 7, 1), 30.0), (date(2000, 7, 2), 31.0)]
        t = compute_thresholds(obs, percentile=95, window_days=15, min_samples=30)
        self.assertTrue(all(v is None for v in t.values))

    def test_smoothing_preserves_missing(self):
        vals = [10.0, 11.0, None, 13.0, 14.0] + [12.0] * 360
        out = smooth_circular(vals, window=3)
        # Position 2 window includes the None -> stays None.
        self.assertIsNone(out[2])


if __name__ == "__main__":
    unittest.main()
