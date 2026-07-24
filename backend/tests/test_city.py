"""Tests for city drill-down geometry + hazard classification (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.city import _classify, _point_in_geom  # noqa: E402


SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]]}
SQUARE_WITH_HOLE = {"type": "Polygon", "coordinates": [
    [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]],
    [[4, 4], [4, 6], [6, 6], [6, 4], [4, 4]]]}


class TestPointInPolygon(unittest.TestCase):
    def test_inside(self):
        self.assertTrue(_point_in_geom(5, 5, SQUARE))

    def test_outside(self):
        self.assertFalse(_point_in_geom(15, 5, SQUARE))

    def test_hole_excluded(self):
        self.assertTrue(_point_in_geom(1, 1, SQUARE_WITH_HOLE))
        self.assertFalse(_point_in_geom(5, 5, SQUARE_WITH_HOLE))  # inside the hole

    def test_multipolygon(self):
        mp = {"type": "MultiPolygon", "coordinates": [SQUARE["coordinates"],
              [[[20, 20], [20, 30], [30, 30], [30, 20], [20, 20]]]]}
        self.assertTrue(_point_in_geom(25, 25, mp))
        self.assertTrue(_point_in_geom(5, 5, mp))
        self.assertFalse(_point_in_geom(15, 15, mp))


class TestClassify(unittest.TestCase):
    def _agg(self, **kw):
        base = dict(extreme_tx99=False, tx95_3day_event=False, heat_index_max=20,
                    tropical_nights_ahead=0, exceeds_tx90=False, tropical_night=False)
        base.update(kw)
        return base

    def test_critical_on_tx99(self):
        cat, reasons = _classify(self._agg(extreme_tx99=True))
        self.assertEqual(cat, "critical")
        self.assertTrue(any("TX99" in r for r in reasons))

    def test_high_on_event(self):
        self.assertEqual(_classify(self._agg(tx95_3day_event=True))[0], "high")

    def test_high_on_repeated_tropical(self):
        self.assertEqual(_classify(self._agg(tropical_nights_ahead=2))[0], "high")

    def test_moderate_on_tx90(self):
        self.assertEqual(_classify(self._agg(exceeds_tx90=True))[0], "moderate")

    def test_moderate_on_tropical_night(self):
        self.assertEqual(_classify(self._agg(tropical_night=True))[0], "moderate")

    def test_low_default(self):
        self.assertEqual(_classify(self._agg())[0], "low")


if __name__ == "__main__":
    unittest.main()
