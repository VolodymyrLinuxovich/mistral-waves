"""Unit tests for the authoritative 5-level severity engine (spec section 14)."""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.severity import classify_series, is_tropical_night, summarize_levels  # noqa: E402


def series(tmaxes, tmins=None, tx90=30.0, tx95=33.0, tx99=37.0, tn90=19.0,
           hi=None, start=date(2020, 7, 20)):
    out = []
    for i, tx in enumerate(tmaxes):
        out.append({"date": (start + timedelta(days=i)).isoformat(), "tmax": tx,
                    "tmin": None if tmins is None else tmins[i],
                    "tx90": tx90, "tx95": tx95, "tx99": tx99, "tn90": tn90,
                    "heat_index": None if hi is None else hi[i]})
    return classify_series(out)


class TestLevels(unittest.TestCase):
    def test_no_exceedance_level0(self):
        r = series([25, 26, 24])
        self.assertTrue(all(d["severity_level"] == 0 for d in r))

    def test_one_tx90_day_level1(self):
        r = series([31, 25])
        self.assertEqual(r[0]["severity_level"], 1)
        self.assertEqual(r[1]["severity_level"], 0)

    def test_two_consecutive_tx90_level2(self):
        r = series([31, 32, 24])
        self.assertEqual(r[1]["severity_level"], 2)
        self.assertEqual(r[1]["current_tx90_run_length"], 2)

    def test_three_tx95_days_level3(self):
        r = series([34, 35, 36])
        self.assertEqual(r[2]["severity_level"], 3)
        self.assertEqual(r[2]["current_tx95_run_length"], 3)

    def test_tx99_during_event_level4(self):
        r = series([34, 35, 38])  # run90>=2 active, day2 tmax>tx99=37
        self.assertEqual(r[2]["severity_level"], 4)

    def test_repeated_tropical_nights_escalate_to_severe(self):
        r = series([31, 31, 31], tmins=[21, 21, 21])  # active + 3 tropical nights
        self.assertEqual(r[2]["severity_level"], 3)
        self.assertEqual(r[2]["consecutive_tropical_nights"], 3)

    def test_equality_not_strict_exceed(self):
        r = series([30, 30])  # tmax == tx90 -> not an exceedance
        self.assertTrue(all(d["severity_level"] == 0 for d in r))

    def test_missing_day_breaks_run(self):
        r = series([31, None, 31, 31])  # None resets; day3 run=2
        self.assertEqual(r[3]["current_tx90_run_length"], 2)
        self.assertEqual(r[3]["severity_level"], 2)
        self.assertEqual(r[1]["data_quality_flag"], "missing")

    def test_heat_index_danger_severe(self):
        r = series([31, 25], hi=[42, 20])  # HI>=41 danger -> severe
        self.assertEqual(r[0]["severity_level"], 3)

    def test_month_boundary_event(self):
        r = series([34, 35, 36], start=date(2020, 7, 30))  # Jul30-Aug1
        self.assertEqual(r[2]["severity_level"], 3)
        self.assertEqual(r[0]["event_start"], "2020-07-30")
        self.assertEqual(r[2]["event_end"], "2020-08-01")

    def test_tropical_night_definition(self):
        self.assertTrue(is_tropical_night(21, 19))       # >=20
        self.assertTrue(is_tropical_night(18.5, 18.0))   # >TN90
        self.assertFalse(is_tropical_night(17.8, 18.7))
        self.assertIsNone(is_tropical_night(None, 19))


class TestSummary(unittest.TestCase):
    def test_status(self):
        self.assertEqual(summarize_levels([0, 0, 0])["status"], "no_event")
        self.assertEqual(summarize_levels([0, 1, 0])["status"], "watch")
        self.assertEqual(summarize_levels([0, 2, 1])["status"], "confirmed")
        self.assertEqual(summarize_levels([0, 1, 0])["counts_by_level"][1], 1)


if __name__ == "__main__":
    unittest.main()
