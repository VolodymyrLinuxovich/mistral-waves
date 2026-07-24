"""Shared helpers for ERA5-Land download: validation + manifest.

A downloaded NetCDF is COMPLETE only when validate_netcdf() passes every check:
opens, has the expected variable, valid coords, the expected year, Ukraine extent,
physically-plausible values, and is not an HTML/error page disguised as NetCDF.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]
RAW_DIR = REPO / "data" / "raw" / "era5_land"
MANIFEST = RAW_DIR / "manifest.json"

# Ukraine bounding box [north, west, south, east] = [53, 22, 44, 41].
UA = {"north": 53, "west": 22, "south": 44, "east": 41}
EXPECTED_VAR = "t2m"


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _looks_like_netcdf(path: Path) -> bool:
    """Reject HTML/JSON error bodies masquerading as NetCDF."""
    with open(path, "rb") as f:
        head = f.read(8)
    # NetCDF classic: b'CDF\x01/2'; NetCDF4/HDF5: b'\x89HDF\r\n\x1a\n'.
    return head[:3] == b"CDF" or head[:4] == b"\x89HDF"


def validate_netcdf(path: Path, year: int) -> tuple[bool, dict]:
    """Return (ok, info). info always includes a human-readable 'error' on failure."""
    info: dict = {"path": str(path)}
    if not path.exists() or path.stat().st_size < 5000:
        return False, {**info, "error": "missing or too small"}
    info["file_size"] = path.stat().st_size
    if not _looks_like_netcdf(path):
        return False, {**info, "error": "not NetCDF (HTML/error body?)"}

    try:
        import numpy as np
        import pandas as pd
        import xarray as xr

        ds = xr.open_dataset(path, engine="netcdf4")
    except Exception as e:  # noqa: BLE001
        return False, {**info, "error": f"open failed: {type(e).__name__}: {e}"}

    try:
        if EXPECTED_VAR not in ds.data_vars:
            return False, {**info, "error": f"variable '{EXPECTED_VAR}' absent; "
                                            f"have {list(ds.data_vars)}"}
        da = ds[EXPECTED_VAR]
        latname = next((c for c in ("latitude", "lat") if c in da.coords), None)
        lonname = next((c for c in ("longitude", "lon") if c in da.coords), None)
        timename = next((c for c in ("valid_time", "time") if c in da.coords), None)
        if not (latname and lonname and timename):
            return False, {**info, "error": "missing lat/lon/time coords"}

        lat = ds[latname].values
        lon = ds[lonname].values
        info["dimensions"] = {k: int(v) for k, v in ds.sizes.items()}

        # Geographic extent must cover Ukraine bbox (allow 0.2 deg tolerance).
        if not (lat.min() <= UA["south"] + 0.2 and lat.max() >= UA["north"] - 0.2):
            return False, {**info, "error": f"lat extent {lat.min()}..{lat.max()} "
                                            "does not cover Ukraine"}
        if not (lon.min() <= UA["west"] + 0.2 and lon.max() >= UA["east"] - 0.2):
            return False, {**info, "error": f"lon extent {lon.min()}..{lon.max()} "
                                            "does not cover Ukraine"}

        times = pd.DatetimeIndex(ds[timename].values)
        years_present = set(times.year)
        info["date_coverage"] = [str(times.min().date()), str(times.max().date())]
        if year not in years_present:
            return False, {**info, "error": f"expected year {year} not in {sorted(years_present)}"}

        # Physical plausibility (Kelvin ERA5-Land 2 m temp).
        sample = da.isel({timename: slice(0, 5)}).values
        finite = sample[np.isfinite(sample)]
        info["units"] = str(da.attrs.get("units", "unknown"))
        if finite.size:
            vmin, vmax = float(finite.min()), float(finite.max())
            info["value_range_sample"] = [round(vmin, 2), round(vmax, 2)]
            # Accept Kelvin (180-340) or Celsius (-90..70).
            k_ok = 180 <= vmin and vmax <= 340
            c_ok = -90 <= vmin and vmax <= 70
            if not (k_ok or c_ok):
                return False, {**info, "error": f"implausible values {vmin}..{vmax}"}
        return True, info
    finally:
        ds.close()


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"entries": {}, "updated_utc": None}


def save_manifest(man: dict) -> None:
    man["updated_utc"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(man, indent=2))
    tmp.replace(MANIFEST)


def record(man: dict, year: int, stat: str, status: str, info: dict,
           error: Optional[str] = None) -> None:
    tag = "tmax" if stat == "daily_maximum" else "tmin"
    man["entries"][f"{tag}_{year}"] = {
        "year": year,
        "statistic": stat,
        "status": status,
        "path": info.get("path"),
        "file_size": info.get("file_size"),
        "checksum_sha256": info.get("checksum_sha256"),
        "dimensions": info.get("dimensions"),
        "date_coverage": info.get("date_coverage"),
        "units": info.get("units"),
        "value_range_sample": info.get("value_range_sample"),
        "download_timestamp": datetime.now(timezone.utc).isoformat(),
        "error": error or info.get("error"),
    }
