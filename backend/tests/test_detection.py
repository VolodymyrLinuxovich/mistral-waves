"""Acceptance tests for heatwave event detection (spec section 2 test list).

Run:  .venv/bin/python -m unittest discover -s backend/tests -v
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.heat.detection import (  # noqa: E402
    DayRecord,
    detect_events,
    detect_primary,
    detect_sensitivity_2day,
)


def series(threshold, tmaxes, start=date(2024, 7, 1), tmins=None, tn=None):
    """Build a daily DayRecord series; None in tmaxes means a missing day."""
    recs = []
    for i, tx in enumerate(tmaxes):
        recs.append(
            DayRecord(
                day=start + timedelta(days=i),
                tmax=tx,
                threshold=threshold,
                tmin=None if tmins is None else tmins[i],
                tn_threshold=tn,
            )
        )
    return recs


class TestRunLength(unittest.TestCase):
    def test_exactly_two_days_not_a_primary_event(self):
        # 2 hot days must NOT trigger the 3-day primary definition.
        r = detect_primary(series(30.0, [31, 31, 25, 25]))
        self.assertEqual(len(r.events), 0)

    def test_exactly_two_days_is_a_sensitivity_event(self):
        # ...but the 2-day sensitivity definition must catch it.
        r = detect_sensitivity_2day(series(30.0, [31, 31, 25, 25]))
        self.assertEqual(len(r.events), 1)
        self.assertEqual(r.events[0].duration_days, 2)

    def test_exactly_three_days(self):
        r = detect_primary(series(30.0, [31, 32, 33, 25]))
        self.assertEqual(len(r.events), 1)
        ev = r.events[0]
        self.assertEqual(ev.duration_days, 3)
        self.assertEqual(ev.max_exceedance, 3.0)          # 33-30
        self.assertEqual(ev.cumulative_exceedance, 6.0)   # 1+2+3
        self.assertEqual(ev.mean_exceedance, 2.0)

    def test_value_exactly_equal_to_threshold_does_not_qualify(self):
        # Strict comparison: Tmax == threshold is NOT an exceedance.
        r = detect_primary(series(30.0, [30, 30, 30, 30]))
        self.assertEqual(len(r.events), 0)
        self.assertEqual(r.n_days_qualifying, 0)

    def test_interrupted_sequence_splits_runs(self):
        # hot,hot,cool,hot,hot,hot -> only the 3-day tail is a primary event.
        r = detect_primary(series(30.0, [31, 31, 20, 31, 31, 31]))
        self.assertEqual(len(r.events), 1)
        self.assertEqual(r.events[0].duration_days, 3)

    def test_multiple_events_separated_by_normal_days(self):
        r = detect_primary(series(30.0, [31, 32, 33, 20, 20, 34, 35, 36]))
        self.assertEqual(len(r.events), 2)
        self.assertEqual(r.events[0].duration_days, 3)
        self.assertEqual(r.events[1].duration_days, 3)
        # Recovery between the two events = 2 cool days.
        self.assertEqual(r.events[0].recovery_days, 2)

    def test_missing_day_breaks_run_and_is_flagged(self):
        # A missing Tmax in the middle must break the run, not extend it.
        r = detect_primary(series(30.0, [31, 32, None, 33, 34]))
        self.assertEqual(len(r.events), 0)  # neither side reaches 3
        self.assertEqual(r.n_days_missing, 1)
        self.assertTrue(any("missing" in w.lower() for w in r.warnings))

    def test_missing_threshold_breaks_run(self):
        recs = series(30.0, [31, 32, 33, 34])
        recs[1] = DayRecord(day=recs[1].day, tmax=32, threshold=None)
        r = detect_primary(recs)
        self.assertEqual(len(r.events), 0)
        self.assertEqual(r.n_days_missing, 1)

    def test_sequence_crossing_month_boundary(self):
        # Run spanning Jul 30 -> Aug 2 must be detected as one event.
        r = detect_primary(series(30.0, [31, 32, 33, 34], start=date(2024, 7, 30)))
        self.assertEqual(len(r.events), 1)
        self.assertEqual(r.events[0].start, date(2024, 7, 30))
        self.assertEqual(r.events[0].end, date(2024, 8, 2))

    def test_leap_year_feb_29_in_run(self):
        # Feb 28, 29, Mar 1 2024 (leap) as a valid 3-day run.
        r = detect_primary(series(10.0, [12, 13, 14], start=date(2024, 2, 28)))
        self.assertEqual(len(r.events), 1)
        self.assertEqual(r.events[0].end, date(2024, 3, 1))

    def test_tropical_night_counting(self):
        # tmins 21,22,19 with absolute 20C -> 2 tropical nights inside a 3-day event.
        r = detect_primary(series(30.0, [31, 32, 33], tmins=[21, 22, 19]))
        self.assertEqual(len(r.events), 1)
        self.assertEqual(r.events[0].tropical_nights, 2)


if __name__ == "__main__":
    unittest.main()
