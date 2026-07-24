"""Coarse Ukraine forecast grid -> continuous heat field (GeoJSON cells).

Fetches a coarse lat/lon grid of daily Tmax/Tmin from Open-Meteo in batched
multi-coordinate requests (not thousands of per-point calls), compares each cell
to its local ERA5-Land threshold, and returns GeoJSON grid-cell polygons the
frontend renders as a filled field. The whole grid is cached per (spacing, days)
so repeat requests are instant.

Still hazard only; still respects provisional baseline.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path

import httpx

from app.services.thresholds_store import get_store

_CACHE_ROOT = Path(os.environ.get("WAVES_CACHE_DIR",
                                  Path(__file__).resolve().parents[3] / "data" / "cache"))
CACHE_DIR = _CACHE_ROOT / "grid"
BASE_URL = "https://api.open-meteo.com/v1/forecast"
UA = {"north": 53, "west": 22, "south": 44, "east": 41}
CACHE_TTL = 3 * 3600
BATCH = 100  # coords per Open-Meteo request


def _grid_points(spacing: float):
    pts = []
    lat = UA["south"] + spacing / 2
    while lat < UA["north"]:
        lon = UA["west"] + spacing / 2
        while lon < UA["east"]:
            pts.append((round(lat, 3), round(lon, 3)))
            lon += spacing
        lat += spacing
    return pts


def _fetch_grid_daily(points, forecast_days: int) -> list[dict]:
    """Batched multi-coordinate Open-Meteo daily fetch."""
    out: list[dict] = []
    for i in range(0, len(points), BATCH):
        chunk = points[i:i + BATCH]
        params = {
            "latitude": ",".join(str(p[0]) for p in chunk),
            "longitude": ",".join(str(p[1]) for p in chunk),
            "daily": "temperature_2m_max,temperature_2m_min",
            "timezone": "UTC",
            "forecast_days": forecast_days,
        }
        r = httpx.get(BASE_URL, params=params, timeout=40)
        r.raise_for_status()
        data = r.json()
        out.extend(data if isinstance(data, list) else [data])
    return out


def _cache_path(spacing: float, days: int) -> Path:
    return CACHE_DIR / f"grid_{spacing}_{days}.json"


def forecast_grid(on: str, layer: str = "tx95_exceedance",
                  spacing: float = 1.0, forecast_days: int = 14) -> dict:
    """Return a GeoJSON FeatureCollection of grid cells with the layer value."""
    d = date.fromisoformat(on)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    points = _grid_points(spacing)
    cache = _cache_path(spacing, forecast_days)

    raw = None
    from_cache = False
    if cache.exists() and (time.time() - cache.stat().st_mtime) < CACHE_TTL:
        raw = json.loads(cache.read_text()); from_cache = True
    if raw is None:
        try:
            results = _fetch_grid_daily(points, forecast_days)
            raw = {"points": [list(p) for p in points], "results": results}
            cache.write_text(json.dumps(raw))
        except Exception as e:  # noqa: BLE001
            if cache.exists():
                raw = json.loads(cache.read_text()); from_cache = True
            else:
                raise

    store = get_store()
    feats = []
    half = spacing / 2
    for (lat, lon), res in zip([tuple(p) for p in raw["points"]], raw["results"]):
        daily = res.get("daily", {})
        times = daily.get("time", [])
        try:
            di = times.index(on)
        except ValueError:
            continue
        tmax = daily.get("temperature_2m_max", [None] * len(times))[di]
        tmin = daily.get("temperature_2m_min", [None] * len(times))[di]
        th = store.at_point(lat, lon, d)["thresholds"] if store.is_available() else {}
        tx95, tx90, tn90 = th.get("tx95"), th.get("tx90"), th.get("tn90")
        if layer == "tx90_exceedance":
            value = (tmax - tx90) if (tmax is not None and tx90 is not None) else None
        elif layer == "nighttime":
            value = 1 if (tmin is not None and (tmin >= 20 or (tn90 is not None and tmin > tn90))) else 0
        else:  # tx95_exceedance
            value = (tmax - tx95) if (tmax is not None and tx95 is not None) else None
        feats.append({
            "type": "Feature",
            "properties": {"value": None if value is None else round(value, 2),
                           "tmax": tmax, "tx95": tx95, "lat": lat, "lon": lon},
            "geometry": {"type": "Polygon", "coordinates": [[
                [lon - half, lat - half], [lon + half, lat - half],
                [lon + half, lat + half], [lon - half, lat + half],
                [lon - half, lat - half]]]},
        })
    binfo = store.baseline_info() if store.is_available() else {}
    return {
        "type": "FeatureCollection",
        "layer": layer, "date": on, "spacing_deg": spacing,
        "cells": len(feats), "from_cache": from_cache,
        "baseline_status": binfo.get("baseline_status", "unavailable"),
        "provisional": binfo.get("provisional", True),
        "disclaimer": "Coarse forecast field (hazard only); ~1° cells, not street-level.",
        "features": feats,
    }
