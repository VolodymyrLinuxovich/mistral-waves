"""Heatwave FOOTPRINT + SUMMARY: the event-based hazard surface.

Classifies every forecast/observed grid cell with the authoritative severity
engine, groups adjacent cells (level >= 2) into connected footprints, and
summarises the national state (no_event / watch / confirmed). This is what the
"Heat hazard" layer renders — connected event zones, not a red temperature map.

Modes: live (Open-Meteo grid), synthetic (labelled demo), historical (served
from precomputed catalogue files, see historical.py).
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Optional

from app.services import demo, grid as gridmod
from app.services.severity import PALETTE, classify_series, summarize_levels
from app.services.thresholds_store import get_store

_CACHE_ROOT = Path(os.environ.get("WAVES_CACHE_DIR",
                                  Path(__file__).resolve().parents[3] / "data" / "cache"))
FP_CACHE = _CACHE_ROOT / "footprint"
FP_TTL = 3 * 3600
RES_NOTE = ("Approximately 9–13 km grid; classification is cell-based. Not "
            "street-level temperature.")


def _cells_for(on: str, spacing: float, scenario: Optional[str]) -> tuple[list, list]:
    """Return (cells, available_dates). Each cell: dict with lat/lon/row/col +
    classified severity for `on`."""
    points = gridmod._grid_points(spacing)
    store = get_store()

    if scenario == "heatwave":
        snap = demo.heatwave_scenario()
        results = [{"daily": snap["daily"]} for _ in points]  # uniform synthetic field
    else:
        results = gridmod._fetch_grid_daily(points, 14)  # batched multi-coord (live)

    # stable row/col from sorted unique lats/lons
    lats = sorted({round(p[0], 3) for p in points})
    lons = sorted({round(p[1], 3) for p in points})
    row_of = {v: i for i, v in enumerate(lats)}
    col_of = {v: i for i, v in enumerate(lons)}

    cells = []
    available = None
    for (lat, lon), res in zip(points, results):
        daily = res.get("daily", {})
        times = daily.get("time", [])
        if available is None:
            available = list(times)
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        series = []
        for i, dt in enumerate(times):
            th = store.at_point(lat, lon, date.fromisoformat(dt))["thresholds"] if store.is_available() else {}
            series.append({"date": dt,
                           "tmax": tmax[i] if i < len(tmax) else None,
                           "tmin": tmin[i] if i < len(tmin) else None,
                           "tx90": th.get("tx90"), "tx95": th.get("tx95"),
                           "tx99": th.get("tx99"), "tn90": th.get("tn90")})
        classified = classify_series(series)
        day = next((c for c in classified if c["date"] == on), None)
        if day is None:
            continue
        cells.append({"lat": lat, "lon": lon,
                      "row": row_of[round(lat, 3)], "col": col_of[round(lon, 3)], **day})
    return cells, (available or [])


def _connected_footprints(cells: list) -> dict:
    """4-neighbour connected components over cells with severity_level >= 2."""
    by_rc = {(c["row"], c["col"]): c for c in cells}
    seen = set()
    comp_of = {}
    comp_id = 0
    for c in cells:
        if c["severity_level"] < 2:
            continue
        key = (c["row"], c["col"])
        if key in seen:
            continue
        # BFS
        stack = [key]
        seen.add(key)
        members = []
        while stack:
            rc = stack.pop()
            members.append(rc)
            r, co = rc
            for nb in ((r + 1, co), (r - 1, co), (r, co + 1), (r, co - 1)):
                if nb in by_rc and nb not in seen and by_rc[nb]["severity_level"] >= 2:
                    seen.add(nb)
                    stack.append(nb)
        fid = f"fp{comp_id}"
        for rc in members:
            comp_of[rc] = fid
        comp_id += 1
    return comp_of


def _cache_path(on, mode, spacing, scenario):
    return FP_CACHE / f"{mode}_{on}_{spacing}_{scenario or 'live'}.json"


def footprint(on: str, mode: str = "live", spacing: float = 1.0,
              scenario: Optional[str] = None) -> dict:
    date.fromisoformat(on)
    FP_CACHE.mkdir(parents=True, exist_ok=True)
    ck = _cache_path(on, mode, spacing, scenario)
    if ck.exists() and (time.time() - ck.stat().st_mtime) < FP_TTL:
        return json.loads(ck.read_text())

    cells, available = _cells_for(on, spacing, scenario)
    comp_of = _connected_footprints(cells)
    half = spacing / 2
    feats = []
    for c in cells:
        fid = comp_of.get((c["row"], c["col"]))
        lat, lon = c["lat"], c["lon"]
        feats.append({
            "type": "Feature",
            "properties": {
                "severity_level": c["severity_level"], "severity_label": c["severity_label"],
                "color": c["severity_color"], "footprint_id": fid,
                "tmax": c["tmax"], "tmin": c["tmin"],
                "tx90": c["tx90"], "tx95": c["tx95"], "tx99": c["tx99"], "tn90": c["tn90"],
                "tx90_exceedance": c["tx90_exceedance"], "tx95_exceedance": c["tx95_exceedance"],
                "tx90_run": c["current_tx90_run_length"], "tx95_run": c["current_tx95_run_length"],
                "tropical_night": c["tropical_night"],
                "consecutive_tropical_nights": c["consecutive_tropical_nights"],
                "event_id": c["event_id"], "event_start": c["event_start"],
                "event_end": c["event_end"], "duration": c["forecast_event_duration"],
                "reasons": c["category_reasons"],
            },
            "geometry": {"type": "Polygon", "coordinates": [[
                [lon - half, lat - half], [lon + half, lat - half],
                [lon + half, lat + half], [lon - half, lat + half], [lon - half, lat - half]]]},
        })
    result = {
        "type": "FeatureCollection", "mode": mode, "date": on,
        "spacing_deg": spacing, "resolution_note": RES_NOTE,
        "cells": len(feats), "footprint_count": len(set(comp_of.values())),
        "available_dates": available, "features": feats,
    }
    ck.write_text(json.dumps(result))
    return result


def summary(on: str, mode: str = "live", spacing: float = 1.0,
            scenario: Optional[str] = None) -> dict:
    fp = footprint(on, mode=mode, spacing=spacing, scenario=scenario)
    levels = [f["properties"]["severity_level"] for f in fp["features"]]
    s = summarize_levels(levels)
    # footprint details
    fps = {}
    for f in fp["features"]:
        fid = f["properties"]["footprint_id"]
        if not fid:
            continue
        d = fps.setdefault(fid, {"id": fid, "cells": 0, "max_level": 0, "max_tx95_exc": None})
        d["cells"] += 1
        d["max_level"] = max(d["max_level"], f["properties"]["severity_level"])
        exc = f["properties"]["tx95_exceedance"]
        if exc is not None:
            d["max_tx95_exc"] = exc if d["max_tx95_exc"] is None else max(d["max_tx95_exc"], exc)
    footprints = sorted(fps.values(), key=lambda x: (x["max_level"], x["cells"]), reverse=True)
    store = get_store()
    binfo = store.baseline_info() if store.is_available() else {}
    watch = s["counts_by_level"].get(1, 0)
    if s["status"] == "no_event":
        headline = "No active heatwave detected in the available forecast period."
    elif s["status"] == "watch":
        headline = f"Unusual heat developing — {watch} area(s) under watch; persistence criteria not yet met."
    else:
        headline = f"{len(footprints)} confirmed heatwave footprint(s) detected."
    return {
        "mode": mode, "date": on, "status": s["status"], "headline": headline,
        "counts_by_level": s["counts_by_level"],
        "watch_cells": watch,
        "footprint_count": len(footprints),
        "highest_footprint": footprints[0] if footprints else None,
        "available_dates": fp["available_dates"],
        "resolution_note": RES_NOTE,
        "baseline_status": binfo.get("baseline_status"),
        "baseline_years": binfo.get("baseline_years", []),
        "baseline_year_count": binfo.get("baseline_year_count"),
        "expected_year_count": binfo.get("expected_year_count", 30),
        "threshold_version": binfo.get("threshold_version"),
        "palette": PALETTE,
    }
