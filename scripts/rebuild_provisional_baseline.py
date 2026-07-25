#!/usr/bin/env python3
"""Rebuild the ADAPTIVE provisional climatology from every complete year-pair.

Uses only years for which BOTH a valid Tmax and Tmin ERA5-Land file exist
(validated, not merely present). Idempotent: if the set of valid year-pairs has
not changed since the last build, it does nothing.

Writes:
  data/processed/ukraine_heat_thresholds_provisional.npz   (numpy, Vercel-safe)
  data/processed/ukraine_heat_thresholds_provisional.meta.json
  data/processed/baseline_metadata.json                    (machine-readable)

Never names a provisional product *_1991_2020.* and never touches raw files.
The final promotion to *_1991_2020.* happens only when all 60 files validate
(see scripts/compute_thresholds.py --mode full).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from compute_thresholds import _to_celsius, calendar_percentile  # noqa: E402
from era5_common import RAW_DIR, validate_netcdf  # noqa: E402

PROCESSED = REPO / "data" / "processed"
OUT_NPZ = PROCESSED / "ukraine_heat_thresholds_provisional.npz"
META = PROCESSED / "ukraine_heat_thresholds_provisional.meta.json"
BASELINE_META = PROCESSED / "baseline_metadata.json"
ALGO_VERSION = "provisional-baseline-1.0.0"
EXPECTED_YEARS = list(range(1991, 2021))


def valid_year_pairs() -> tuple[list[int], list[str]]:
    years, files = [], []
    for y in EXPECTED_YEARS:
        tmax = RAW_DIR / f"tmax_{y}.nc"
        tmin = RAW_DIR / f"tmin_{y}.nc"
        if not (tmax.exists() and tmin.exists()):
            continue
        ok_max, _ = validate_netcdf(tmax, y)
        ok_min, _ = validate_netcdf(tmin, y)
        if ok_max and ok_min:
            years.append(y)
            files += [tmax.name, tmin.name]
    return years, files


def _open_years(tag: str, years: list[int]) -> xr.DataArray:
    das = []
    tdim = None
    for y in years:
        ds = xr.open_dataset(RAW_DIR / f"{tag}_{y}.nc", engine="netcdf4")
        v = max(ds.data_vars, key=lambda x: ds[x].size)
        da = ds[v]
        tdim = next((d for d in da.dims if d in ("valid_time", "time")), None)
        das.append(da)
    da = xr.concat(das, dim=tdim) if len(das) > 1 else das[0]
    ren = {}
    for c in ("valid_time", "time"):
        if c in da.dims:
            ren[c] = "time"
    for c in ("latitude", "lat"):
        if c in da.dims:
            ren[c] = "lat"
    for c in ("longitude", "lon"):
        if c in da.dims:
            ren[c] = "lon"
    return da.rename(ren)


def main() -> int:
    years, files = valid_year_pairs()
    if not years:
        print("No complete Tmax/Tmin year-pairs found yet; nothing to build.")
        return 0

    # Idempotent: skip if year set unchanged.
    if META.exists():
        prev = json.loads(META.read_text())
        prev_years = [int(y) for y in str(prev.get("baseline_years", "")).split(",") if y.strip().isdigit()]
        if prev_years == years:
            print(f"No new year-pair since last build (years={years}); nothing to do.")
            return 0

    print(f"Building adaptive provisional baseline from {len(years)} year(s): {years}")
    tmax, mconv = _to_celsius(_open_years("tmax", years))
    tmin, nconv = _to_celsius(_open_years("tmin", years))
    lat = tmax["lat"].values.astype("float32")
    lon = tmax["lon"].values.astype("float32")

    tx90 = calendar_percentile(tmax, 90)
    tx95 = calendar_percentile(tmax, 95)
    tx99 = calendar_percentile(tmax, 99)
    tn90 = calendar_percentile(tmin, 90)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    tmp = PROCESSED / "_provisional_tmp.npz"  # must end in .npz (savez appends otherwise)
    np.savez_compressed(tmp, tx90=tx90, tx95=tx95, tx99=tx99, tn90=tn90,
                        lat=lat, lon=lon, dayofyear=np.arange(1, 366, dtype="int16"))
    # validate written file
    chk = np.load(tmp)
    assert all(k in chk for k in ("tx90", "tx95", "tx99", "tn90", "lat", "lon"))
    assert chk["tx95"].shape == (365, lat.size, lon.size)
    os.replace(tmp, OUT_NPZ)

    meta = {
        "baseline_status": "provisional",
        "baseline_years": ",".join(map(str, years)),
        "baseline_year_count": len(years),
        "expected_baseline": "1991-2020",
        "expected_year_count": len(EXPECTED_YEARS),
        "provisional": True,
        "threshold_version": ALGO_VERSION,
        "algorithm_version": ALGO_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_files": files,
        "source_dataset": "derived-era5-land-daily-statistics (CDS)",
        "tmax_unit_conversion": mconv, "tmin_unit_conversion": nconv,
        "tn90_status": f"computed from {years}",
        "warning": (f"PROVISIONAL: percentile estimate from {len(years)} of "
                    f"{len(EXPECTED_YEARS)} baseline years ({years}) — statistically "
                    "incomplete. Thresholds will change as the baseline completes."),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    META.write_text(json.dumps(meta, indent=2))
    BASELINE_META.write_text(json.dumps({k: meta[k] for k in (
        "baseline_status", "baseline_years", "baseline_year_count",
        "expected_baseline", "expected_year_count", "threshold_version",
        "generated_at")}, indent=2))
    print(f"Wrote {OUT_NPZ.name} ({OUT_NPZ.stat().st_size/1e6:.1f} MB) — years {years}")
    print("WARNING:", meta["warning"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
