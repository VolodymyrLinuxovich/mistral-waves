#!/usr/bin/env python3
"""Detect REAL historical heatwave events from downloaded ERA5-Land daily data.

For every year with a validated Tmax/Tmin pair, sample the observed daily fields
onto the coarse analysis grid, classify every cell/day with the authoritative
severity engine, group consecutive national event-days (any cell level >= 2) into
events, and write a catalogue + compact per-event daily footprints.

Outputs (bundled into the Vercel deploy):
  data/processed/historical_events.json
  data/processed/historical_footprints/{event_id}.json

Uses the current provisional baseline thresholds. Re-run after the baseline
rebuilds or is promoted to recompute classifications. Not synthetic data.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "backend"))
from era5_common import RAW_DIR, validate_netcdf  # noqa: E402
from compute_thresholds import _to_celsius  # noqa: E402
from app.services import grid as gridmod  # noqa: E402
from app.services.severity import ALGORITHM_VERSION, classify_series  # noqa: E402
from app.services.thresholds_store import get_store  # noqa: E402

PROCESSED = REPO / "data" / "processed"
FP_DIR = PROCESSED / "historical_footprints"
SPACING = 1.0
EXPECTED = list(range(1991, 2021))


def _open_year(tag: str, year: int):
    ds = xr.open_dataset(RAW_DIR / f"{tag}_{year}.nc", engine="netcdf4")
    v = max(ds.data_vars, key=lambda x: ds[x].size)
    da = ds[v]
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
    da = da.rename(ren)
    da, _ = _to_celsius(da)   # after rename so isel(time=0) works
    return da


def valid_years():
    ys = []
    for y in EXPECTED:
        if (RAW_DIR / f"tmax_{y}.nc").exists() and (RAW_DIR / f"tmin_{y}.nc").exists():
            if validate_netcdf(RAW_DIR / f"tmax_{y}.nc", y)[0] and validate_netcdf(RAW_DIR / f"tmin_{y}.nc", y)[0]:
                ys.append(y)
    return ys


def main() -> int:
    years = valid_years()
    if not years:
        print("No valid ERA5 year-pairs; no catalogue built.")
        return 0
    store = get_store()
    binfo = store.baseline_info()
    points = gridmod._grid_points(SPACING)
    FP_DIR.mkdir(parents=True, exist_ok=True)
    catalogue = []
    ev_counter = 0

    for year in years:
        print(f"Scanning ERA5-Land {year} for events…", flush=True)
        tmax = _open_year("tmax", year); tmin = _open_year("tmin", year)
        lats = tmax["lat"].values; lons = tmax["lon"].values
        times = pd.DatetimeIndex(tmax["time"].values)
        tmax_v = tmax.transpose("time", "lat", "lon").values
        tmin_v = tmin.transpose("time", "lat", "lon").values
        dates = [t.date().isoformat() for t in times]

        # classify every coarse grid cell over the whole year
        cell_class = {}   # (lat,lon) -> list of per-day dicts
        for (plat, plon) in points:
            li = int(np.abs(lats - plat).argmin()); oi = int(np.abs(lons - plon).argmin())
            series = []
            for i, dt in enumerate(dates):
                th = store.at_point(plat, plon, date.fromisoformat(dt))["thresholds"]
                tv = float(tmax_v[i, li, oi]); nv = float(tmin_v[i, li, oi])
                series.append({"date": dt,
                               "tmax": None if tv != tv else tv,
                               "tmin": None if nv != nv else nv,
                               "tx90": th.get("tx90"), "tx95": th.get("tx95"),
                               "tx99": th.get("tx99"), "tn90": th.get("tn90")})
            cell_class[(plat, plon)] = classify_series(series)

        # per-day: any cell level>=2 -> event day
        n = len(dates)
        event_day = [False] * n
        for i in range(n):
            event_day[i] = any(cell_class[p][i]["severity_level"] >= 2 for p in points)

        # group consecutive event days
        i = 0
        while i < n:
            if not event_day[i]:
                i += 1; continue
            j = i
            while j + 1 < n and event_day[j + 1]:
                j += 1
            # build event over [i, j]
            ev_counter += 1
            eid = f"era5-{year}-{ev_counter:03d}"
            max_level = 0; max90 = None; max95 = None; maxT = None; trop = 0; cum = 0.0
            affected = set()
            foot = {}   # date -> features (cells level>=1)
            for k in range(i, j + 1):
                dt = dates[k]; features = []
                for (plat, plon) in points:
                    c = cell_class[(plat, plon)][k]
                    if c["severity_level"] >= 1:
                        affected.add((plat, plon))
                        max_level = max(max_level, c["severity_level"])
                        if c["tx90_exceedance"] is not None:
                            max90 = c["tx90_exceedance"] if max90 is None else max(max90, c["tx90_exceedance"])
                        if c["tx95_exceedance"] is not None:
                            max95 = c["tx95_exceedance"] if max95 is None else max(max95, c["tx95_exceedance"])
                        if c["tmax"] is not None:
                            maxT = c["tmax"] if maxT is None else max(maxT, c["tmax"])
                        if c["tropical_night"] is True:
                            trop += 1
                        cum += max(0.0, c["tx95_exceedance"] or 0.0)
                        half = SPACING / 2
                        features.append({"type": "Feature", "properties": {
                            "severity_level": c["severity_level"], "severity_label": c["severity_label"],
                            "color": c["severity_color"], "tmax": c["tmax"], "tmin": c["tmin"],
                            "tx90_exceedance": c["tx90_exceedance"], "tx95_exceedance": c["tx95_exceedance"],
                            "tx90_run": c["current_tx90_run_length"], "tx95_run": c["current_tx95_run_length"],
                            "tropical_night": c["tropical_night"], "reasons": c["category_reasons"]},
                            "geometry": {"type": "Polygon", "coordinates": [[
                                [plon-half, plat-half], [plon+half, plat-half],
                                [plon+half, plat+half], [plon-half, plat+half], [plon-half, plat-half]]]}})
                foot[dt] = {"type": "FeatureCollection", "date": dt, "features": features}

            meta = {
                "event_id": eid, "source": "ERA5-Land", "observed_or_forecast": "observed",
                "year": year, "start_date": dates[i], "end_date": dates[j],
                "duration_days": j - i + 1, "affected_cell_count": len(affected),
                "approximate_affected_area_km2": int(len(affected) * (SPACING * 111) ** 2),
                "maximum_severity_level": max_level,
                "maximum_TX90_exceedance": round(max90, 2) if max90 is not None else None,
                "maximum_TX95_exceedance": round(max95, 2) if max95 is not None else None,
                "maximum_temperature": round(maxT, 1) if maxT is not None else None,
                "tropical_night_count": trop, "cumulative_exceedance": round(cum, 1),
                "baseline_status": binfo.get("baseline_status"),
                "baseline_years": binfo.get("baseline_years"),
                "data_resolution": "~1.0deg analysis grid (downsampled from ERA5-Land ~9km)",
                "algorithm_version": ALGORITHM_VERSION,
            }
            meta["has_footprint"] = max_level >= 3
            catalogue.append(meta)
            # Only write per-event daily footprint files for significant (severe/
            # extreme) events — those are the selectable replay events; keeps the
            # deploy bundle lean across ~29 years of data.
            if max_level >= 3:
                (FP_DIR / f"{eid}.json").write_text(json.dumps(
                    {"event": meta, "dates": dates[i:j + 1], "footprints": foot}))
            i = j + 1

    # Rank by intensity (max temperature) within a level so genuine summer
    # heatwaves lead over long-but-mild shoulder-season spells.
    catalogue.sort(key=lambda e: (e["maximum_severity_level"],
                                  e.get("maximum_temperature") or -99,
                                  e["affected_cell_count"]), reverse=True)
    PROCESSED.joinpath("historical_events.json").write_text(json.dumps(
        {"generated_years": years, "algorithm_version": ALGORITHM_VERSION,
         "baseline_status": binfo.get("baseline_status"),
         "baseline_years": binfo.get("baseline_years"),
         "event_count": len(catalogue), "events": catalogue}, indent=2))
    print(f"\n{len(catalogue)} event(s) across years {years}. "
          f"Top: {catalogue[0]['event_id'] if catalogue else 'none'} "
          f"L{catalogue[0]['maximum_severity_level'] if catalogue else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
