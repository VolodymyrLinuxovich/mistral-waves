"""Tests for the runtime threshold store using a tiny synthetic processed file.

The synthetic NetCDF here is a CLEARLY-LABELLED test fixture, not climate data.
"""
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.thresholds_store import ThresholdStore, _cal_index_365  # noqa: E402


class TestCalIndex(unittest.TestCase):
    def test_feb29_folds_to_feb28(self):
        self.assertEqual(_cal_index_365(date(2024, 2, 29)),
                         _cal_index_365(date(2024, 2, 28)))


class TestStore(unittest.TestCase):
    def test_missing_file_degrades_gracefully(self):
        from pathlib import Path
        store = ThresholdStore(candidates=[Path("/no/such/full.nc"),
                                           Path("/no/such/prov.nc")])
        self.assertFalse(store.is_available())
        self.assertIsNone(store.at_point(50.45, 30.52, date(2026, 7, 25)))
        self.assertFalse(store.metadata()["available"])
        self.assertEqual(store.metadata()["baseline_status"], "unavailable")

    def test_point_query_on_synthetic_fixture(self):
        import numpy as np
        import xarray as xr
        doy = np.arange(1, 366)
        lat = np.array([50.0, 50.5, 51.0])
        lon = np.array([30.0, 30.5, 31.0])
        shape = (365, 3, 3)
        ds = xr.Dataset(
            {
                "tx90": (("dayofyear", "lat", "lon"), np.full(shape, 28.0, "float32")),
                "tx95": (("dayofyear", "lat", "lon"), np.full(shape, 31.0, "float32")),
                "tx99": (("dayofyear", "lat", "lon"), np.full(shape, 35.0, "float32")),
                "tn90": (("dayofyear", "lat", "lon"), np.full(shape, 18.0, "float32")),
            },
            coords={"dayofyear": doy, "lat": lat, "lon": lon},
            attrs={"baseline_status": "provisional", "baseline_years": "2020",
                   "expected_baseline": "1991-2020", "source_dataset": "SYNTHETIC-FIXTURE"},
        )
        with tempfile.TemporaryDirectory() as d:
            from pathlib import Path
            p = Path(d) / "thr.nc"
            ds.to_netcdf(p)
            store = ThresholdStore(candidates=[p])
            self.assertTrue(store.is_available())
            r = store.at_point(50.4, 30.4, date(2026, 7, 25))
            self.assertEqual(r["thresholds"]["tx95"], 31.0)
            self.assertEqual(r["thresholds"]["tn90"], 18.0)
            self.assertEqual(r["unit"], "degC")
            self.assertEqual(r["baseline_status"], "provisional")
            self.assertTrue(r["provisional"])


if __name__ == "__main__":
    unittest.main()
