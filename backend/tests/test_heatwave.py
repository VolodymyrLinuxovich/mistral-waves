"""Tests for footprint connected-components + historical labelling (no network)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.heatwave import _connected_footprints  # noqa: E402


def cell(r, c, lvl):
    return {"row": r, "col": c, "severity_level": lvl}


class TestConnectedComponents(unittest.TestCase):
    def test_adjacent_cells_grouped(self):
        cells = [cell(0, 0, 2), cell(0, 1, 3), cell(1, 0, 2)]  # all touch
        comp = _connected_footprints(cells)
        self.assertEqual(len({comp[(0, 0)], comp[(0, 1)], comp[(1, 0)]}), 1)

    def test_separate_components(self):
        cells = [cell(0, 0, 2), cell(0, 1, 2),      # component A
                 cell(0, 5, 3), cell(0, 6, 3)]      # component B (gap at cols 2-4)
        comp = _connected_footprints(cells)
        self.assertNotEqual(comp[(0, 0)], comp[(0, 5)])
        self.assertEqual(comp[(0, 0)], comp[(0, 1)])

    def test_level1_cells_excluded(self):
        cells = [cell(0, 0, 1), cell(0, 1, 1)]      # watch only -> no footprint
        comp = _connected_footprints(cells)
        self.assertEqual(comp, {})

    def test_diagonal_not_connected_4neighbour(self):
        cells = [cell(0, 0, 2), cell(1, 1, 2)]      # only diagonal touch
        comp = _connected_footprints(cells)
        self.assertNotEqual(comp[(0, 0)], comp[(1, 1)])


class TestHistoricalLabelling(unittest.TestCase):
    def test_catalogue_events_are_observed(self):
        # If a catalogue exists, every event must be labelled observed ERA5-Land.
        from app.services import historical
        if not historical.available():
            self.skipTest("no catalogue built")
        evs = historical.list_events(limit=5)["events"]
        for e in evs:
            self.assertEqual(e["observed_or_forecast"], "observed")
            self.assertEqual(e["source"], "ERA5-Land")


if __name__ == "__main__":
    unittest.main()
