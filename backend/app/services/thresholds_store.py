"""Runtime access to the precomputed ERA5-Land threshold climatology.

Prefers a compact numpy .npz (read with numpy ONLY — no netCDF4/xarray/pandas,
so the serverless bundle stays small); falls back to the .nc via a lazy xarray
import for local/dev use. Serves the FULL baseline when present, else the
clearly-labelled provisional file.

Exposes baseline_status / baseline_years / expected_baseline everywhere.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

PROCESSED = Path(__file__).resolve().parents[3] / "data" / "processed"
EXPECTED_BASELINE = "1991-2020"

# Priority order: full baseline, then the adaptive provisional product, then the
# legacy 2020-only provisional, then .nc fallbacks (local dev).
CANDIDATES = [
    PROCESSED / "ukraine_heat_thresholds_1991_2020.npz",
    PROCESSED / "ukraine_heat_thresholds_provisional.npz",
    PROCESSED / "ukraine_heat_thresholds_2020_provisional.npz",
    PROCESSED / "ukraine_heat_thresholds_1991_2020.nc",
    PROCESSED / "ukraine_heat_thresholds_2020_provisional.nc",
]

_MONTH_CUMDAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def _cal_index_365(d: date) -> int:
    if d.month == 2 and d.day == 29:
        return 58
    return _MONTH_CUMDAYS[d.month - 1] + (d.day - 1)


class ThresholdStore:
    def __init__(self, candidates: Optional[list[Path]] = None):
        self.candidates = candidates if candidates is not None else CANDIDATES
        self._loaded_path: Optional[Path] = None
        self._mtime = None
        self._vars: dict = {}
        self._lat = None
        self._lon = None
        self._meta: dict = {}

    def active_path(self) -> Optional[Path]:
        for p in self.candidates:
            if p.exists():
                return p
        return None

    def is_available(self) -> bool:
        return self.active_path() is not None

    def _load(self) -> bool:
        path = self.active_path()
        if path is None:
            return False
        mtime = path.stat().st_mtime
        if self._loaded_path == path and self._mtime == mtime and self._vars:
            return True
        if path.suffix == ".npz":
            self._load_npz(path)
        else:
            self._load_nc(path)
        self._loaded_path = path
        self._mtime = mtime
        return True

    def _load_npz(self, path: Path) -> None:
        data = np.load(path)
        self._vars = {v: data[v] for v in ("tx90", "tx95", "tx99", "tn90")}
        self._lat = data["lat"]
        self._lon = data["lon"]
        meta_path = path.with_suffix(".meta.json")
        self._meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    def _load_nc(self, path: Path) -> None:
        import xarray as xr  # lazy: only for local .nc use
        ds = xr.open_dataset(path)
        self._vars = {v: ds[v].values for v in ("tx90", "tx95", "tx99", "tn90")}
        self._lat = ds["lat"].values
        self._lon = ds["lon"].values
        self._meta = {k: str(v) for k, v in ds.attrs.items()}
        ds.close()

    def baseline_info(self) -> dict:
        if not self._load():
            return {"baseline_status": "unavailable", "baseline_years": [],
                    "expected_baseline": EXPECTED_BASELINE, "provisional": True}
        status = str(self._meta.get("baseline_status", "provisional"))
        years_raw = str(self._meta.get("baseline_years", ""))
        years = [int(y) for y in years_raw.split(",") if y.strip().isdigit()]
        return {
            "baseline_status": status,
            "baseline_years": years,
            "baseline_year_count": int(self._meta.get("baseline_year_count", len(years))),
            "expected_baseline": str(self._meta.get("expected_baseline", EXPECTED_BASELINE)),
            "expected_year_count": int(self._meta.get("expected_year_count", 30)),
            "threshold_version": str(self._meta.get("threshold_version", "unknown")),
            "provisional": status != "complete",
            "warning": str(self._meta.get("warning", "")) or None,
            "tn90_status": str(self._meta.get("tn90_status", "unknown")),
            "source_file": self._loaded_path.name if self._loaded_path else None,
        }

    def metadata(self) -> dict:
        if not self.is_available():
            return {"available": False, "baseline_status": "unavailable",
                    "expected_baseline": EXPECTED_BASELINE}
        self._load()
        info = self.baseline_info()
        info.update({
            "available": True,
            "variables": list(self._vars.keys()),
            "grid": {"lat": int(self._lat.size), "lon": int(self._lon.size)},
            "created_utc": str(self._meta.get("created_utc", "unknown")),
            "warning": str(self._meta.get("WARNING_partial_baseline", "")) or None,
        })
        return info

    def at_point(self, lat: float, lon: float, d: date) -> Optional[dict]:
        if not self._load():
            return None
        li = int(np.abs(self._lat - lat).argmin())
        oi = int(np.abs(self._lon - lon).argmin())
        di = _cal_index_365(d)  # 0-based index into 365
        out = {}
        for v, arr in self._vars.items():
            val = float(arr[di, li, oi])
            out[v] = None if (val != val) else round(val, 2)
        info = self.baseline_info()
        return {
            "requested": {"lat": lat, "lon": lon, "date": d.isoformat()},
            "grid_cell": {"lat": round(float(self._lat[li]), 4),
                          "lon": round(float(self._lon[oi]), 4)},
            "dayofyear": di + 1,
            "unit": "degC",
            "thresholds": out,
            "baseline_status": info["baseline_status"],
            "baseline_years": info["baseline_years"],
            "expected_baseline": info["expected_baseline"],
            "provisional": info["provisional"],
            "source": str(self._meta.get("source_dataset", "unknown")),
        }


@lru_cache(maxsize=1)
def get_store() -> ThresholdStore:
    return ThresholdStore()
