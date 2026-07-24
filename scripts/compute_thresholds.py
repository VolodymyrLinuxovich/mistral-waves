#!/usr/bin/env python3
"""Compute calendar-day percentile climatology from downloaded ERA5-Land files.

Reads data/raw/era5_land/era5land_tmax_*.nc and era5land_tmin_*.nc, computes per
grid cell:
    TX90/TX95/TX99  from daily Tmax
    TN90            from daily Tmin
using a +/-15-day calendar-day window across the available baseline years, and
writes a compact result to
    data/processed/ukraine_heat_thresholds_1991_2020.nc

The window/percentile logic matches backend/app/services/heat/thresholds.py
(fixed 365-day calendar; Feb 29 -> Feb 28 slot; numpy linear percentile).

The deployed app loads this compact file; it never processes 30 years at runtime.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
RAW_DIR = REPO / "data" / "raw" / "era5_land"
PROCESSED = REPO / "data" / "processed"
# Provisional output (partial baseline) vs the promoted full-baseline output.
# The full-baseline name is created ONLY after all 1991-2020 years validate.
OUT_PROVISIONAL = PROCESSED / "ukraine_heat_thresholds_2020_provisional.nc"
OUT_FULL = PROCESSED / "ukraine_heat_thresholds_1991_2020.nc"
FULL_YEARS = list(range(1991, 2021))
WINDOW = 15  # +/- days

_MONTH_CUMDAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def cal_index_365(dt: pd.Timestamp) -> int:
    """0-based fixed-calendar day index; Feb 29 -> Feb 28 (58)."""
    if dt.month == 2 and dt.day == 29:
        return 58
    return _MONTH_CUMDAYS[dt.month - 1] + (dt.day - 1)


def _open_var(pattern: str) -> tuple[xr.DataArray, list[int]]:
    files = sorted(glob.glob(str(RAW_DIR / pattern)))
    if not files:
        raise FileNotFoundError(f"no files match {pattern} in {RAW_DIR}")
    # Open each file plainly (no dask) and concatenate along the time axis.
    per_file = []
    time_dim = None
    for f in files:
        ds = xr.open_dataset(f, engine="netcdf4")
        varname = max(ds.data_vars, key=lambda v: ds[v].size)
        da_f = ds[varname]
        time_dim = next((d for d in da_f.dims if d in ("valid_time", "time")), None)
        per_file.append(da_f)
    da = xr.concat(per_file, dim=time_dim) if len(per_file) > 1 else per_file[0]
    # Normalise coordinate names.
    rename = {}
    for cand in ("valid_time", "time"):
        if cand in da.dims:
            rename[cand] = "time"
    for cand in ("latitude", "lat"):
        if cand in da.dims:
            rename[cand] = "lat"
    for cand in ("longitude", "lon"):
        if cand in da.dims:
            rename[cand] = "lon"
    da = da.rename(rename)
    years = sorted({int(f.split("_")[-1].split(".")[0]) for f in files})
    return da, years


def _to_celsius(da: xr.DataArray) -> tuple[xr.DataArray, str]:
    sample = float(np.nanmean(da.isel(time=0).values))
    if sample > 100:  # Kelvin
        return da - 273.15, "converted_from_kelvin"
    return da, "already_celsius"


def calendar_percentile(da: xr.DataArray, pct: float) -> np.ndarray:
    """Return (365, lat, lon) percentile array using a +/-WINDOW calendar window.

    Optimisation: ERA5-Land sea cells are permanently NaN. We compute percentiles
    only on cells that are finite across *all* times (pure land) using the fast
    np.percentile; non-land cells are left NaN (flagged as missing, not faked).
    This keeps results identical to the nan-aware version while avoiding the very
    slow per-cell nan sorting over the full baseline.
    """
    times = pd.DatetimeIndex(da["time"].values)
    cal_idx = np.array([cal_index_365(t) for t in times])
    values = da.transpose("time", "lat", "lon").values.astype("float32")  # (T,lat,lon)
    t, nlat, nlon = values.shape
    flat = values.reshape(t, nlat * nlon)
    land = np.isfinite(flat).all(axis=0)  # cells finite at every timestep
    landvals = flat[:, land]
    out = np.full((365, nlat * nlon), np.nan, dtype="float32")
    for center in range(365):
        window = {(center + k) % 365 for k in range(-WINDOW, WINDOW + 1)}
        mask = np.isin(cal_idx, list(window))
        if not mask.any():
            continue
        out[center, land] = np.percentile(landvals[mask], pct, axis=0)
    return out.reshape(365, nlat, nlon)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["provisional", "full"], default="provisional",
                    help="provisional: whatever years exist -> *_2020_provisional.nc; "
                         "full: require all 1991-2020, promote to *_1991_2020.nc")
    ap.add_argument("--out", default=None, help="override output path")
    args = ap.parse_args()

    PROCESSED.mkdir(parents=True, exist_ok=True)

    # Tmax is required.
    print("Opening Tmax files...", flush=True)
    try:
        tmax, tmax_years = _open_var("tmax_*.nc")
    except FileNotFoundError as e:
        print(f"ERROR: {e}", flush=True)
        return 2
    tmax, tmax_conv = _to_celsius(tmax)
    print(f"  Tmax years: {tmax_years} ({tmax_conv})", flush=True)

    lat = tmax["lat"].values
    lon = tmax["lon"].values

    # Tmin is OPTIONAL for provisional; REQUIRED for full.
    tmin = None
    tmin_years: list[int] = []
    tmin_conv = "not_available"
    try:
        print("Opening Tmin files...", flush=True)
        tmin, tmin_years = _open_var("tmin_*.nc")
        tmin, tmin_conv = _to_celsius(tmin)
        print(f"  Tmin years: {tmin_years} ({tmin_conv})", flush=True)
    except FileNotFoundError:
        print("  Tmin NOT available yet -> TN90 will be missing (NaN).", flush=True)

    baseline = sorted(tmax_years)
    have_full = (baseline == FULL_YEARS and sorted(tmin_years) == FULL_YEARS)

    if args.mode == "full":
        if not have_full:
            missing_tx = [y for y in FULL_YEARS if y not in tmax_years]
            missing_tn = [y for y in FULL_YEARS if y not in tmin_years]
            print("ERROR: full baseline incomplete; refusing to promote.")
            print(f"  missing Tmax years: {missing_tx}")
            print(f"  missing Tmin years: {missing_tn}")
            return 3
        out_path = OUT_FULL
        baseline_status = "complete"
    else:
        out_path = OUT_PROVISIONAL
        baseline_status = "complete" if have_full else "provisional"

    if args.out:
        out_path = Path(args.out)

    print("Computing TX90/TX95/TX99 (calendar +/-15d)...", flush=True)
    tx90 = calendar_percentile(tmax, 90)
    tx95 = calendar_percentile(tmax, 95)
    tx99 = calendar_percentile(tmax, 99)
    if tmin is not None:
        print("Computing TN90...", flush=True)
        tn90 = calendar_percentile(tmin, 90)
    else:
        tn90 = np.full((365, len(lat), len(lon)), np.nan, dtype="float32")

    doy = np.arange(1, 366)
    coords = {"dayofyear": doy, "lat": lat, "lon": lon}
    dims = ("dayofyear", "lat", "lon")
    out_ds = xr.Dataset(
        {"tx90": (dims, tx90), "tx95": (dims, tx95),
         "tx99": (dims, tx99), "tn90": (dims, tn90)},
        coords=coords,
    )
    for v in ("tx90", "tx95", "tx99", "tn90"):
        out_ds[v].attrs["units"] = "degC"
    tn90_status = ("computed from " + ",".join(map(str, sorted(tmin_years)))
                   if tmin_years else "MISSING - Tmin not yet downloaded (all NaN)")
    out_ds.attrs.update(
        title="Ukraine ERA5-Land calendar-day heat thresholds",
        source_dataset="derived-era5-land-daily-statistics (CDS)",
        source_note="ERA5-Land reanalysis (~9 km). Not ground truth / not station data.",
        baseline_status=baseline_status,                 # provisional | complete
        baseline_years=",".join(map(str, baseline)),
        expected_baseline="1991-2020",
        provisional="false" if baseline_status == "complete" else "true",
        tmin_years_present=",".join(map(str, sorted(tmin_years))) or "none",
        tn90_status=tn90_status,
        window_days=WINDOW,
        percentile_method="numpy linear (type 7)",
        calendar="fixed 365-day; Feb 29 folded into Feb 28",
        tmax_unit_conversion=tmax_conv,
        tmin_unit_conversion=tmin_conv,
        created_utc=datetime.now(timezone.utc).isoformat(),
        note="Compact climatology for runtime use; app does not process raw years live.",
    )
    if baseline_status == "provisional":
        out_ds.attrs["WARNING_partial_baseline"] = (
            f"PROVISIONAL: baseline years present = {baseline}; "
            "NOT the full 1991-2020 climatology. Pipeline sanity check only."
        )

    comp = {v: {"zlib": True, "complevel": 4} for v in out_ds.data_vars}
    # Write to temp, validate, then atomically promote (never expose a partial file).
    tmp = out_path.with_suffix(".nc.tmp")
    out_ds.to_netcdf(tmp, encoding=comp)
    out_ds.close()
    _validate_written(tmp)
    os.replace(tmp, out_path)
    size = out_path.stat().st_size
    print(f"\nWrote {out_path} ({size/1e6:.2f} MB) baseline_status={baseline_status}")
    print(f"Baseline years used: {baseline}")
    print(f"Grid: {len(lat)} lat x {len(lon)} lon")
    if baseline_status == "provisional":
        print("WARNING:", out_ds.attrs["WARNING_partial_baseline"])
    return 0


def _validate_written(path: Path) -> None:
    """Reopen the just-written file and assert it is structurally sound."""
    ds = xr.open_dataset(path)
    try:
        assert set(("tx90", "tx95", "tx99", "tn90")).issubset(ds.data_vars), "vars missing"
        assert ds.sizes["dayofyear"] == 365, "dayofyear != 365"
        assert ds.sizes["lat"] > 0 and ds.sizes["lon"] > 0, "empty grid"
    finally:
        ds.close()


if __name__ == "__main__":
    sys.exit(main())
