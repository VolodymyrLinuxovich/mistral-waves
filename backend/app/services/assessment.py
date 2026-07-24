"""Environmental heat-HAZARD assessment for a location.

Combines the Open-Meteo forecast with the local ERA5-Land thresholds and the
detection/index engine to answer: how hot, how unusual, how persistent, and
how bad overnight — for a point, over the forecast window.

STRICT FRAMING: this is meteorological HAZARD only. It is NOT population health
outcome and NOT individual medical risk (those are separate layers). Every
response says so and carries the baseline_status (provisional vs complete).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

from app.services.forecast import fetch_forecast
from app.services.heat.detection import (
    DayRecord,
    detect_early_signal,
    detect_primary,
    detect_sensitivity_2day,
)
from app.services.heat.indices import heat_index, humidex, is_tropical_night
from app.services.thresholds_store import get_store

HAZARD_DISCLAIMER = (
    "Environmental heat HAZARD only (how hot/unusual/persistent the weather is). "
    "This is not population health outcome and not individual medical risk."
)


def _daily_index_maxes(hourly: dict) -> dict:
    """From hourly T/RH/dewpoint, compute each day's worst-case Heat Index and
    Humidex (max over the day). Missing hours are skipped, not zeroed."""
    times = hourly.get("time", [])
    temp = hourly.get("temperature_2m", [])
    rh = hourly.get("relative_humidity_2m", [])
    dew = hourly.get("dew_point_2m", [])
    hi_by_day: dict[str, float] = defaultdict(lambda: float("-inf"))
    hx_by_day: dict[str, float] = defaultdict(lambda: float("-inf"))
    for i, ts in enumerate(times):
        day = ts[:10]
        t = temp[i] if i < len(temp) else None
        if t is None:
            continue
        if i < len(rh) and rh[i] is not None:
            hi = heat_index(t, rh[i])
            if hi.value is not None:
                hi_by_day[day] = max(hi_by_day[day], hi.value)
        if i < len(dew) and dew[i] is not None:
            hx = humidex(t, dew[i])
            if hx.value is not None:
                hx_by_day[day] = max(hx_by_day[day], hx.value)
    finalize = lambda d: {k: (None if v == float("-inf") else round(v, 1))
                          for k, v in d.items()}
    return {"heat_index_max": finalize(hi_by_day), "humidex_max": finalize(hx_by_day)}


def _hazard_level(day_summaries: list[dict]) -> str:
    """Coarse hazard band for the window (hazard only, not health)."""
    level = "low"
    order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
    for d in day_summaries:
        lvl = "low"
        tx99 = d["thresholds"].get("tx99")
        if tx99 is not None and d["tmax"] is not None and d["tmax"] > tx99:
            lvl = "critical"
        elif d["in_primary_event"]:
            lvl = "high"
        elif d["exceeds_tx90"] or (d["heat_index_max"] or -99) >= 32:
            lvl = "moderate"
        if order[lvl] > order[level]:
            level = lvl
    return level


def assess_location(lat: float, lon: float, forecast_days: int = 14,
                    scenario: Optional[str] = None, forecast_result=None) -> dict:
    # forecast_result lets callers (e.g. the city batched fetch) supply an
    # already-fetched forecast so we don't do one network call per point.
    fc = forecast_result or fetch_forecast(lat, lon, forecast_days=forecast_days,
                                           scenario=scenario)
    store = get_store()
    days = fc.daily.get("time", [])
    tmax = fc.daily.get("temperature_2m_max", [])
    tmin = fc.daily.get("temperature_2m_min", [])
    app_max = fc.daily.get("apparent_temperature_max", [])

    # Per-day local thresholds.
    thr: list[dict] = []
    for ds in days:
        d = date.fromisoformat(ds)
        pt = store.at_point(lat, lon, d) if store.is_available() else None
        thr.append(pt["thresholds"] if pt else
                   {"tx90": None, "tx95": None, "tx99": None, "tn90": None})

    idx = _daily_index_maxes(fc.hourly)

    day_summaries: list[dict] = []
    for i, ds in enumerate(days):
        tx = tmax[i] if i < len(tmax) else None
        tn = tmin[i] if i < len(tmin) else None
        th = thr[i]
        trop = is_tropical_night(tn, th.get("tn90"))
        day_summaries.append({
            "date": ds,
            "tmax": tx,
            "tmin": tn,
            "apparent_tmax": app_max[i] if i < len(app_max) else None,
            "thresholds": th,
            "exceeds_tx90": (tx is not None and th.get("tx90") is not None and tx > th["tx90"]),
            "exceeds_tx95": (tx is not None and th.get("tx95") is not None and tx > th["tx95"]),
            "heat_index_max": idx["heat_index_max"].get(ds),
            "humidex_max": idx["humidex_max"].get(ds),
            "tropical_night": trop,
            "in_primary_event": False,  # filled after detection
        })

    # Detection with each definition (build records per threshold key).
    def records(key: str) -> list[DayRecord]:
        recs = []
        for i, ds in enumerate(days):
            recs.append(DayRecord(
                day=date.fromisoformat(ds),
                tmax=tmax[i] if i < len(tmax) else None,
                threshold=thr[i].get(key),
                tmin=tmin[i] if i < len(tmin) else None,
                tn_threshold=thr[i].get("tn90"),
            ))
        return recs

    primary = detect_primary(records("tx95"))
    early = detect_early_signal(records("tx90"))
    sensitivity = detect_sensitivity_2day(records("tx90"))

    # Mark days inside a primary event.
    for ev in primary.events:
        for d in day_summaries:
            if ev.start.isoformat() <= d["date"] <= ev.end.isoformat():
                d["in_primary_event"] = True

    def ser_events(res) -> list[dict]:
        return [{
            "definition": e.definition,
            "start": e.start.isoformat(), "end": e.end.isoformat(),
            "duration_days": e.duration_days,
            "max_exceedance_degC": e.max_exceedance,
            "cumulative_exceedance_degC_days": e.cumulative_exceedance,
            "mean_intensity_degC": e.mean_exceedance,
            "tropical_nights": e.tropical_nights,
        } for e in res.events]

    binfo = store.baseline_info() if store.is_available() else {
        "baseline_status": "unavailable", "baseline_years": [],
        "expected_baseline": "1991-2020", "provisional": True}

    return {
        "layer": "hazard",
        "disclaimer": HAZARD_DISCLAIMER,
        "location": {"latitude": fc.latitude, "longitude": fc.longitude,
                     "timezone": fc.timezone},
        "forecast": {"provider": fc.provider, "fetched_utc": fc.fetched_utc,
                     "from_cache": fc.from_cache, "days": len(days),
                     "resolution_note": "Open-Meteo point forecast; ~1-11 km model grid, "
                                        "no street-level precision implied."},
        "baseline_status": binfo["baseline_status"],
        "baseline_years": binfo["baseline_years"],
        "expected_baseline": binfo["expected_baseline"],
        "provisional": binfo["provisional"],
        "hazard_level": _hazard_level(day_summaries),
        "units": {"temperature": "degC", "heat_index": "degC", "humidex": "index"},
        "days": day_summaries,
        "events": {
            "primary_tx95_3day": ser_events(primary),
            "early_tx90_3day": ser_events(early),
            "sensitivity_tx90_2day": ser_events(sensitivity),
        },
        "warnings": fc.warnings,
    }


def assess_city_points(on: str, layer: str = "tx95_exceedance",
                       forecast_days: int = 14, scenario: Optional[str] = None) -> dict:
    """National overview: forecast exceedance at each major city for date `on`.

    Honest MVP choice: point forecasts at major cities (real forecast + real
    local thresholds), NOT a fabricated gridded field. Rendered as map markers.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.services.cities import CITIES

    d = date.fromisoformat(on)

    # Fetch all cities concurrently (each does a cached Open-Meteo call) so the
    # endpoint stays well inside serverless timeouts.
    def _one(c):
        try:
            return c, assess_location(c.lat, c.lon, forecast_days=forecast_days,
                                      scenario=scenario)
        except Exception:  # noqa: BLE001 — one city failing must not kill the map
            return c, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_one, CITIES))

    points = []
    for c, a in results:
        if a is None:
            points.append({"city": c.id, "name_en": c.name_en, "error": "forecast_unavailable"})
            continue
        day = next((x for x in a["days"] if x["date"] == on), None)
        if day is None:
            points.append({"city": c.id, "name_en": c.name_en, "error": "date_out_of_range"})
            continue
        th = day["thresholds"]
        value = {
            "tx90_exceedance": (day["tmax"] - th["tx90"]) if th.get("tx90") is not None and day["tmax"] is not None else None,
            "tx95_exceedance": (day["tmax"] - th["tx95"]) if th.get("tx95") is not None and day["tmax"] is not None else None,
            "nighttime": (1 if day["tropical_night"] else 0),
            "heat_index": day["heat_index_max"],
        }.get(layer)
        points.append({
            "city": c.id, "name_en": c.name_en, "name_uk": c.name_uk,
            "lat": c.lat, "lon": c.lon,
            "tmax": day["tmax"], "tmin": day["tmin"],
            "thresholds": th,
            "tropical_night": day["tropical_night"],
            "in_primary_event": day["in_primary_event"],
            "value": None if value is None else round(value, 2),
        })
    store = get_store()
    binfo = store.baseline_info() if store.is_available() else {}
    return {
        "layer": layer, "date": on, "disclaimer": HAZARD_DISCLAIMER,
        "baseline_status": binfo.get("baseline_status", "unavailable"),
        "baseline_years": binfo.get("baseline_years", []),
        "expected_baseline": binfo.get("expected_baseline", "1991-2020"),
        "provisional": binfo.get("provisional", True),
        "points": points,
    }
