"""City drill-down: administrative-district heat distribution.

Loads validated district polygons (real OSM geometry — see
scripts/download_kyiv_districts.py), samples the forecast at multiple points per
district (never a single centroid when several model cells intersect), aggregates
spatial mean/max/p90, and classifies district hazard with reasons.

SCIENTIFIC LIMIT (stated in every response): forecast models are far coarser than
neighbourhoods. This is DISTRICT-LEVEL ESTIMATED heat distribution; it does not
represent street-level temperature. We do NOT fabricate fine variation.

Pure-numpy point-in-polygon (no shapely) keeps the serverless bundle small.
Designed for multiple cities; only Kyiv has validated districts today.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

from app.services import demo
from app.services.assessment import HAZARD_DISCLAIMER, assess_location
from app.services.forecast import DAILY_VARS, HOURLY_VARS, _result_from_payload
from app.services.thresholds_store import get_store

OM_URL = "https://api.open-meteo.com/v1/forecast"
OM_BATCH = 100

BOUNDARIES = Path(__file__).resolve().parents[3] / "data" / "boundaries"
_CACHE_ROOT = Path(os.environ.get("WAVES_CACHE_DIR",
                                  Path(__file__).resolve().parents[3] / "data" / "cache"))
CITY_CACHE = _CACHE_ROOT / "city"
CITY_CACHE_TTL = 3 * 3600

RESOLUTION_NOTE = ("District-level estimated heat distribution. Forecast resolution "
                   "does not represent street-level temperature.")
# ~0.08 deg (~9 km) ≈ the native model resolution — honest sampling, not sub-cell.
SAMPLE_SPACING = 0.08


class CityForecastError(RuntimeError):
    """The district forecast could not be produced for the selected date."""


# Multi-city ready; add entries as validated district polygons become available.
CITY_REGISTRY = {
    "kyiv": {
        "name_en": "Kyiv", "name_uk": "Київ",
        "districts_file": "kyiv_districts.geojson",
        "center": [50.4501, 30.5234], "zoom": 10, "default_zoom": 9.5,
        "region_type": "raion",
        "boundary_source": "OpenStreetMap via Overpass (ODbL)",
    },
}


def available_cities() -> list[dict]:
    out = []
    for cid, c in CITY_REGISTRY.items():
        has = (BOUNDARIES / c["districts_file"]).exists()
        out.append({
            "id": cid, "name_en": c["name_en"], "name_uk": c["name_uk"],
            "center": c["center"], "default_zoom": c.get("default_zoom", 9.5),
            "region_type": c.get("region_type"),
            "boundary_source": c.get("boundary_source"),
            "has_districts": has, "has_regions": has,
        })
    return out


@lru_cache(maxsize=4)
def _load_districts(city: str) -> dict:
    c = CITY_REGISTRY.get(city)
    if not c:
        raise KeyError(f"unknown city '{city}'")
    path = BOUNDARIES / c["districts_file"]
    if not path.exists():
        raise FileNotFoundError(f"no district polygons for {city} ({path.name})")
    fc = json.loads(path.read_text())
    prov_path = path.with_suffix(".provenance.json")
    prov = json.loads(prov_path.read_text()) if prov_path.exists() else {}
    return {"fc": fc, "provenance": prov}


# ---- geometry (pure numpy / python) ----
def _pip_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def _point_in_geom(lon: float, lat: float, geom: dict) -> bool:
    t = geom["type"]
    polys = [geom["coordinates"]] if t == "Polygon" else geom["coordinates"]
    for poly in polys:
        if not poly:
            continue
        if _pip_ring(lon, lat, poly[0]):
            if not any(_pip_ring(lon, lat, hole) for hole in poly[1:]):
                return True
    return False


def _geom_bbox(geom: dict):
    xs, ys = [], []
    t = geom["type"]
    polys = [geom["coordinates"]] if t == "Polygon" else geom["coordinates"]
    for poly in polys:
        for ring in poly:
            for x, y in ring:
                xs.append(x); ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def _centroid(geom: dict):
    t = geom["type"]
    poly = geom["coordinates"] if t == "Polygon" else geom["coordinates"][0]
    ring = poly[0]
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    return sum(xs) / len(xs), sum(ys) / len(ys)  # lon, lat


def get_city_regions(city: str) -> dict:
    data = _load_districts(city)
    fc = data["fc"]
    xmins, ymins, xmaxs, ymaxs = [], [], [], []
    regions = []
    for f in fc["features"]:
        p = f["properties"]
        x0, y0, x1, y1 = _geom_bbox(f["geometry"])
        xmins.append(x0); ymins.append(y0); xmaxs.append(x1); ymaxs.append(y1)
        regions.append({"id": p.get("id"), "name": p.get("name"),
                        "name_en": p.get("name_en")})
    bbox = [min(xmins), min(ymins), max(xmaxs), max(ymaxs)]  # [w,s,e,n]
    reg = CITY_REGISTRY[city]
    return {
        "city": city, "name_en": reg["name_en"], "name_uk": reg["name_uk"],
        "center": reg["center"], "zoom": reg["zoom"], "bbox": bbox,
        "n_regions": len(regions), "regions": regions,
        "geojson": fc,
        "source": data["provenance"],
        "resolution_note": RESOLUTION_NOTE,
    }


def _sample_points(features: list, spacing: float = SAMPLE_SPACING) -> dict:
    """Assign a grid of sample points to districts. Districts with no interior
    grid point fall back to their centroid (flagged)."""
    # City bbox.
    x0 = min(_geom_bbox(f["geometry"])[0] for f in features)
    y0 = min(_geom_bbox(f["geometry"])[1] for f in features)
    x1 = max(_geom_bbox(f["geometry"])[2] for f in features)
    y1 = max(_geom_bbox(f["geometry"])[3] for f in features)
    lons = np.arange(x0 + spacing / 2, x1, spacing)
    lats = np.arange(y0 + spacing / 2, y1, spacing)

    by_region: dict[str, list] = {f["properties"]["id"]: [] for f in features}
    for lat in lats:
        for lon in lons:
            for f in features:
                if _point_in_geom(float(lon), float(lat), f["geometry"]):
                    by_region[f["properties"]["id"]].append((float(lat), float(lon)))
                    break
    # Centroid fallback.
    centroid_flag = {}
    for f in features:
        rid = f["properties"]["id"]
        centroid_flag[rid] = False
        if not by_region[rid]:
            clon, clat = _centroid(f["geometry"])
            by_region[rid] = [(clat, clon)]
            centroid_flag[rid] = True
    return by_region, centroid_flag


def _classify(agg: dict) -> tuple[str, list[str]]:
    reasons = []
    hi = agg["heat_index_max"]
    if agg["extreme_tx99"]:
        reasons.append("Tmax exceeds the local TX99 extreme threshold.")
        return "critical", reasons
    high = False
    if agg["tx95_3day_event"]:
        reasons.append("Active/forecast 3-day heatwave (Tmax > local TX95)."); high = True
    if hi is not None and hi >= 41:
        reasons.append(f"Strong Heat Index ({hi} °C)."); high = True
    if agg["tropical_nights_ahead"] >= 2:
        reasons.append(f"Repeated tropical nights ({agg['tropical_nights_ahead']})."); high = True
    if high:
        return "high", reasons
    mod = False
    if agg["exceeds_tx90"]:
        reasons.append("Tmax above the local TX90 early-warning threshold."); mod = True
    if hi is not None and hi >= 32:
        reasons.append(f"Elevated Heat Index ({hi} °C)."); mod = True
    if agg["tropical_night"]:
        reasons.append("Tropical night (Tmin ≥ 20 °C or > local TN90)."); mod = True
    if mod:
        return "moderate", reasons
    reasons.append("Below local TX90; no tropical night; non-dangerous Heat Index.")
    return "low", reasons


def _fetch_points(points: list, scenario: Optional[str]) -> dict:
    """One batched multi-coord Open-Meteo fetch for ALL city sample points.

    Returns {(lat,lon): assessment_dict}. A live failure is surfaced to the
    caller instead of being converted into a zero-cell result from an outdated
    offline snapshot; uses the synthetic scenario if requested.
    """
    assessments: dict = {}
    if scenario == "heatwave":
        payload = demo.heatwave_scenario()
        for (lat, lon) in points:
            fr = _result_from_payload(payload, "demo_heatwave (SYNTHETIC)", True,
                                      ["SYNTHETIC heatwave demo scenario."], "synthetic")
            assessments[(lat, lon)] = assess_location(lat, lon, forecast_result=fr)
        return assessments

    results = None
    try:
        for i in range(0, len(points), OM_BATCH):
            chunk = points[i:i + OM_BATCH]
            params = {
                "latitude": ",".join(str(p[0]) for p in chunk),
                "longitude": ",".join(str(p[1]) for p in chunk),
                "hourly": ",".join(HOURLY_VARS), "daily": ",".join(DAILY_VARS),
                "timezone": "Europe/Kyiv", "forecast_days": 14,
                # National data can still include the previous Kyiv calendar
                # day around midnight. Keep district coverage aligned with it.
                "past_days": 1,
            }
            r = httpx.get(OM_URL, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
            batch = data if isinstance(data, list) else [data]
            results = (results or []) + batch
    except Exception as exc:
        raise CityForecastError("live district forecast fetch failed") from exc

    if results is None or len(results) != len(points):
        raise CityForecastError(
            f"district forecast returned {len(results or [])} of {len(points)} points"
        )

    for (lat, lon), res in zip(points, results):
        payload = {"latitude": lat, "longitude": lon, "timezone": "Europe/Kyiv",
                   "daily": res.get("daily", {}), "hourly": res.get("hourly", {}),
                   "daily_units": res.get("daily_units", {}),
                   "hourly_units": res.get("hourly_units", {})}
        fr = _result_from_payload(payload, "open_meteo", False, [], "Open-Meteo")
        assessments[(lat, lon)] = assess_location(lat, lon, forecast_result=fr)
    return assessments


def _aggregate_region(points: list, on: str, assessments: dict) -> dict:
    """Aggregate pre-computed point assessments for one district."""
    res = []
    for pt in points:
        a = assessments.get(pt)
        if a is None:
            continue
        day = next((d for d in a["days"] if d["date"] == on), None)
        if day is None:
            continue
        th = day["thresholds"]
        tx99 = th.get("tx99")
        idx = next((i for i, d in enumerate(a["days"]) if d["date"] == on), 0)
        trop_ahead = sum(1 for d in a["days"][idx:idx + 3] if d["tropical_night"])
        tx90_event = any(ev["start"] <= on <= ev["end"]
                         for ev in a["events"]["early_tx90_3day"])
        res.append({
            "tmax": day["tmax"], "tmin": day["tmin"], "th": th,
            "tx99_exc": (day["tmax"] is not None and tx99 is not None and day["tmax"] > tx99),
            "hi": day["heat_index_max"], "hx": day["humidex_max"],
            "trop": bool(day["tropical_night"]), "trop_ahead": trop_ahead,
            "tx95_event": bool(day["in_primary_event"]), "tx90_event": tx90_event,
            "sev": day.get("severity_level", 0), "sev_reasons": day.get("severity_reasons", []),
            "from_cache": a["forecast"]["from_cache"], "provider": a["forecast"]["provider"],
        })
    if not res:
        return None

    def arr(key):
        return np.array([r[key] for r in res if r[key] is not None], dtype="float64")

    tmax = arr("tmax"); tmin = arr("tmin")
    th_mean = {k: float(np.nanmean([r["th"].get(k) for r in res
                                    if r["th"].get(k) is not None]))
               if any(r["th"].get(k) is not None for r in res) else None
               for k in ("tx90", "tx95", "tx99", "tn90")}
    his = [r["hi"] for r in res if r["hi"] is not None]
    hxs = [r["hx"] for r in res if r["hx"] is not None]
    hi_max = round(max(his), 1) if his else None
    tmax_mean = float(np.mean(tmax)) if tmax.size else None
    exc95 = (tmax_mean - th_mean["tx95"]) if (tmax_mean is not None and th_mean["tx95"]) else None
    exc90 = (tmax_mean - th_mean["tx90"]) if (tmax_mean is not None and th_mean["tx90"]) else None
    hazard_vals = [(r["tmax"] - r["th"]["tx95"]) for r in res
                   if r["tmax"] is not None and r["th"].get("tx95") is not None]

    agg = {
        "n_cells": len(res),
        "tmax_mean": round(tmax_mean, 1) if tmax_mean is not None else None,
        "tmax_max": round(float(np.max(tmax)), 1) if tmax.size else None,
        "tmax_p90": round(float(np.percentile(tmax, 90)), 1) if tmax.size else None,
        "tmin_mean": round(float(np.mean(tmin)), 1) if tmin.size else None,
        "tmin_max": round(float(np.max(tmin)), 1) if tmin.size else None,
        "tx90": round(th_mean["tx90"], 2) if th_mean["tx90"] is not None else None,
        "tx95": round(th_mean["tx95"], 2) if th_mean["tx95"] is not None else None,
        "tx99": round(th_mean["tx99"], 2) if th_mean["tx99"] is not None else None,
        "tn90": round(th_mean["tn90"], 2) if th_mean["tn90"] is not None else None,
        "tmax_minus_tx90": round(exc90, 2) if exc90 is not None else None,
        "tmax_minus_tx95": round(exc95, 2) if exc95 is not None else None,
        "heat_index_max": hi_max,
        "humidex_max": round(max(hxs), 1) if hxs else None,
        "tropical_night": any(r["trop"] for r in res),
        "tropical_nights_ahead": max((r["trop_ahead"] for r in res), default=0),
        "tx95_3day_event": any(r["tx95_event"] for r in res),
        "tx90_3day_event": any(r["tx90_event"] for r in res),
        "extreme_tx99": any(r["tx99_exc"] for r in res),
        "exceeds_tx90": (exc90 is not None and exc90 > 0),
        "max_hazard_degC": round(max(hazard_vals), 2) if hazard_vals else None,
        "mean_hazard_degC": round(sum(hazard_vals) / len(hazard_vals), 2) if hazard_vals else None,
        "data_status": "synthetic" if any("SYNTHETIC" in r["provider"] for r in res)
                       else ("cached" if all(r["from_cache"] for r in res) else "live"),
    }

    # Severity aggregation (authoritative engine). Default district statistic is
    # the 90th-percentile "affected-area severity" — NOT one-cell-paints-all.
    from app.services.severity import LEVELS, PALETTE
    levels = np.array([r["sev"] for r in res], dtype="int32")
    max_sev = int(levels.max()); mean_sev = float(levels.mean())
    p90_sev = int(round(float(np.percentile(levels, 90))))
    pct = lambda t: round(100.0 * float((levels >= t).mean()), 1)
    max_reasons = next((r["sev_reasons"] for r in res if r["sev"] == max_sev), [])
    agg.update({
        "severity_level": p90_sev, "severity_label": LEVELS[p90_sev],
        "severity_color": PALETTE[p90_sev], "severity_statistic": "90th-percentile district hazard",
        "max_severity_level": max_sev, "max_severity_label": LEVELS[max_sev],
        "mean_severity_level": round(mean_sev, 2),
        "p90_severity_level": p90_sev,
        "pct_level1plus": pct(1), "pct_level2plus": pct(2),
        "pct_level3plus": pct(3), "pct_level4": pct(4),
        "hottest_cell_tmax": agg["tmax_max"],
        "category": LEVELS[p90_sev], "reasons": max_reasons,
    })
    return agg


def get_city_risk_map(city: str, on: str, layer: str = "hazard",
                      scenario: Optional[str] = None) -> dict:
    date.fromisoformat(on)  # validate
    CITY_CACHE.mkdir(parents=True, exist_ok=True)
    ck = CITY_CACHE / f"{city}_{on}_{layer}_{scenario or 'live'}.json"
    if ck.exists() and (time.time() - ck.stat().st_mtime) < CITY_CACHE_TTL:
        cached = json.loads(ck.read_text())
        # Older versions cached transient failures as a successful empty map.
        if cached.get("total_cells_sampled", 0) > 0:
            return cached

    data = _load_districts(city)
    features = data["fc"]["features"]
    by_region, centroid_flag = _sample_points(features)

    # One batched fetch for ALL unique sample points across the whole city.
    all_points = sorted({pt for pts in by_region.values() for pt in pts})
    assessments = _fetch_points(all_points, scenario)
    if not any(any(day.get("date") == on for day in item.get("days", []))
               for item in assessments.values()):
        raise CityForecastError("selected date is outside the district forecast window")

    regions_out = []
    total_cells = 0
    for f in features:
        p = f["properties"]
        rid = p["id"]
        pts = by_region[rid]
        agg = _aggregate_region(pts, on, assessments)
        if agg is None:
            regions_out.append({"id": rid, "name": p.get("name"),
                                "name_en": p.get("name_en"), "error": "forecast_unavailable"})
            continue
        total_cells += agg["n_cells"]
        clon, clat = _centroid(f["geometry"])
        agg.update({"id": rid, "name": p.get("name"), "name_en": p.get("name_en"),
                    "from_centroid": centroid_flag[rid],
                    "centroid": [round(clat, 4), round(clon, 4)]})
        regions_out.append(agg)

    if total_cells == 0:
        raise CityForecastError("district forecast contained no cells for the selected date")

    store = get_store()
    binfo = store.baseline_info() if store.is_available() else {}
    result = {
        "city": city, "date": on, "layer": layer,
        "disclaimer": HAZARD_DISCLAIMER,
        "resolution_note": RESOLUTION_NOTE,
        "forecast_resolution": "Open-Meteo point forecast (~1–11 km model grid)",
        "baseline_status": binfo.get("baseline_status", "unavailable"),
        "baseline_years": binfo.get("baseline_years", []),
        "provisional": binfo.get("provisional", True),
        "n_regions": len(regions_out),
        "total_cells_sampled": total_cells,
        "sample_spacing_deg": SAMPLE_SPACING,
        "regions": regions_out,
    }
    ck.write_text(json.dumps(result))
    return result
