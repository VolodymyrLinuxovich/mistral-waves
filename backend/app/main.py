"""FastAPI backend for the Ukraine heat-health MVP (Day 2 slice).

Endpoints implemented so far:
    GET /api/health         - status + build version
    GET /api/data-status    - per-provider availability, period, missingness
    GET /api/forecast       - Open-Meteo forecast for a point (cached server-side)
    GET /api/thresholds     - TX90/95/99, TN90 for a point + date

Later slices add /api/risk-map, /api/location-risk, POST /api/profile-risk,
GET /api/health-analysis/summary.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.risk.engine import assess as assess_profile
from app.risk.models import EnvironmentContext, ProfileRiskRequest
from app.services.assessment import assess_city_points, assess_location
from app.services.cities import CITIES, search as city_search
from app.services.forecast import ForecastError, fetch_forecast
from app.services.thresholds_store import get_store

BUILD_VERSION = "0.2.0-day2"

app = FastAPI(title="Waves — Ukraine heat-health API", version=BUILD_VERSION)
app.add_middleware(
    CORSMiddleware,
    # Local dev/demo: any localhost port (Next.js :3000, static demo :8080, ...).
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Ukraine bounding box (matches the ERA5 download).
UA_BBOX = {"north": 53, "west": 22, "south": 44, "east": 41}


def _in_ukraine(lat: float, lon: float) -> bool:
    return (UA_BBOX["south"] <= lat <= UA_BBOX["north"]
            and UA_BBOX["west"] <= lon <= UA_BBOX["east"])


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "build": BUILD_VERSION,
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/data-status")
def data_status():
    store = get_store()
    return {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "providers": {
            "climatology_era5_land": {
                "available": store.is_available(),
                "detail": store.metadata(),
            },
            "forecast_open_meteo": {
                "available": True,
                "provider": "Open-Meteo",
                "note": "single provider; not a multi-model ensemble",
                "cache_ttl_seconds": 3600,
            },
        },
    }


@app.get("/api/forecast")
def forecast(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    forecast_days: int = Query(14, ge=1, le=16),
    scenario: str = Query("", description="'heatwave' for the labelled demo scenario"),
):
    try:
        r = fetch_forecast(latitude, longitude, forecast_days=forecast_days,
                           scenario=scenario or None)
    except ForecastError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "provider": r.provider,
        "location": {"latitude": r.latitude, "longitude": r.longitude,
                     "timezone": r.timezone},
        "fetched_utc": r.fetched_utc,
        "from_cache": r.from_cache,
        "units": r.units,
        "daily": r.daily,
        "hourly": r.hourly,
        "provenance": r.provenance,
        "warnings": r.warnings,
    }


@app.get("/api/thresholds")
def thresholds(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    on: str = Query(..., description="date YYYY-MM-DD"),
):
    store = get_store()
    if not store.is_available():
        raise HTTPException(
            status_code=503,
            detail="threshold climatology not built yet; run scripts/compute_thresholds.py",
        )
    try:
        d = date.fromisoformat(on)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date; use YYYY-MM-DD")
    if not _in_ukraine(latitude, longitude):
        raise HTTPException(status_code=422, detail="point outside Ukraine bbox")
    result = store.at_point(latitude, longitude, d)
    return result


@app.get("/api/location-risk")
def location_risk(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    forecast_days: int = Query(14, ge=1, le=16),
    scenario: str = Query("", description="'heatwave' for the labelled demo scenario"),
):
    """Environmental heat HAZARD + area context for one point (not health risk)."""
    try:
        return assess_location(latitude, longitude, forecast_days=forecast_days,
                               scenario=scenario or None)
    except ForecastError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/risk-map")
def risk_map(
    on: str = Query(..., description="date YYYY-MM-DD"),
    layer: str = Query("tx95_exceedance",
                       description="tx90_exceedance|tx95_exceedance|nighttime|heat_index"),
    scenario: str = Query("", description="'heatwave' demo scenario"),
):
    """National overview: forecast exceedance at major cities for `on` (hazard)."""
    try:
        date.fromisoformat(on)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date; use YYYY-MM-DD")
    allowed = {"tx90_exceedance", "tx95_exceedance", "nighttime", "heat_index"}
    if layer not in allowed:
        raise HTTPException(status_code=422, detail=f"layer must be one of {sorted(allowed)}")
    return assess_city_points(on, layer=layer, scenario=scenario or None)


def _env_from_location(lat: float, lon: float, on: str,
                       scenario: str | None = None) -> EnvironmentContext:
    """Derive environmental HAZARD context for a location+date from the forecast."""
    a = assess_location(lat, lon, forecast_days=14, scenario=scenario)
    day = next((d for d in a["days"] if d["date"] == on), None)
    if day is None:
        # Out of forecast range: fall back to the first available day, flagged.
        day = a["days"][0] if a["days"] else None
    if day is None:
        raise ForecastError("no forecast days available")
    th = day["thresholds"]
    exceeds_tx99 = (th.get("tx99") is not None and day["tmax"] is not None
                    and day["tmax"] > th["tx99"])
    duration = 0
    for ev in a["events"]["primary_tx95_3day"]:
        if ev["start"] <= on <= ev["end"]:
            duration = ev["duration_days"]
    return EnvironmentContext(
        exceeds_tx90=bool(day["exceeds_tx90"]),
        exceeds_tx95=bool(day["exceeds_tx95"]),
        exceeds_tx99=bool(exceeds_tx99),
        in_primary_event=bool(day["in_primary_event"]),
        event_duration_days=duration,
        tropical_night=bool(day["tropical_night"]),
        heat_index_max=day["heat_index_max"],
        baseline_status=a["baseline_status"],
        observed_confirmation=False,
        source=f"open-meteo forecast + era5 thresholds ({a['baseline_status']})",
    )


@app.post("/api/profile-risk")
def profile_risk(req: ProfileRiskRequest,
                 scenario: str = Query("", description="'heatwave' demo scenario")):
    """Deterministic personal risk. Emergency symptoms override all scoring."""
    # Emergency symptoms don't need environment — handled first by the engine.
    if req.environment is None and not req.symptoms.any_flag():
        if req.latitude is None or req.longitude is None or req.date is None:
            raise HTTPException(status_code=422,
                                detail="provide environment, or latitude+longitude+date")
        try:
            req.environment = _env_from_location(req.latitude, req.longitude, req.date,
                                                 scenario=scenario or None)
        except ForecastError as ex:
            raise HTTPException(status_code=502,
                                detail=f"could not derive environment: {ex}")
    if req.environment is None:
        # Emergency-only request with no environment: supply a neutral context.
        req.environment = EnvironmentContext()
    return assess_profile(req)


@app.get("/api/heatwave-summary")
def heatwave_summary(
    on: str = Query(..., alias="date", description="YYYY-MM-DD"),
    mode: str = Query("live", description="live|historical|synthetic"),
    event_id: str = Query(""),
    spacing: float = Query(1.0, ge=0.5, le=2.0),
):
    try:
        date.fromisoformat(on)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date; use YYYY-MM-DD")
    if mode == "historical":
        from app.services import historical
        eid = event_id or historical.default_event_id()
        if not eid:
            raise HTTPException(status_code=404, detail="no historical events available")
        res = historical.event_summary(eid, on)
        if res is None:
            raise HTTPException(status_code=404, detail=f"unknown event {eid}")
        return res
    from app.services.heatwave import summary
    scen = "heatwave" if mode == "synthetic" else None
    return summary(on, mode=mode, spacing=spacing, scenario=scen)


@app.get("/api/heatwave-footprint")
def heatwave_footprint(
    on: str = Query(..., alias="date", description="YYYY-MM-DD"),
    mode: str = Query("live", description="live|historical|synthetic"),
    event_id: str = Query(""),
    spacing: float = Query(1.0, ge=0.5, le=2.0),
):
    try:
        date.fromisoformat(on)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date; use YYYY-MM-DD")
    if mode == "historical":
        from app.services import historical
        eid = event_id or historical.default_event_id()
        if not eid:
            raise HTTPException(status_code=404, detail="no historical events available")
        res = historical.event_footprint(eid, on)
        if res is None:
            raise HTTPException(status_code=404, detail=f"unknown event {eid}")
        return res
    from app.services.heatwave import footprint
    scen = "heatwave" if mode == "synthetic" else None
    return footprint(on, mode=mode, spacing=spacing, scenario=scen)


@app.get("/api/historical-events")
def historical_events(year: int = Query(None), minimum_level: int = Query(0, ge=0, le=4),
                      limit: int = Query(50, ge=1, le=200)):
    from app.services import historical
    if not historical.available():
        raise HTTPException(status_code=404, detail="historical catalogue not built")
    return historical.list_events(year=year, minimum_level=minimum_level, limit=limit)


@app.get("/api/historical-event/{event_id}")
def historical_event(event_id: str):
    from app.services import historical
    res = historical.event_detail(event_id)
    if res is None:
        raise HTTPException(status_code=404, detail=f"unknown event {event_id}")
    return res


@app.get("/api/city-regions")
def city_regions(city: str = Query("kyiv")):
    """District polygons + city boundary/metadata for a city (validated OSM)."""
    from app.services.city import get_city_regions
    try:
        return get_city_regions(city.lower())
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(status_code=404,
                            detail=f"district detail unavailable for '{city}': {e}")


@app.get("/api/city-risk-map")
def city_risk_map(
    city: str = Query("kyiv"),
    date_: str = Query(..., alias="date", description="YYYY-MM-DD"),
    layer: str = Query("hazard"),
    scenario: str = Query(""),
):
    """Per-district heat hazard (spatial mean/max/p90) with reasons."""
    try:
        date.fromisoformat(date_)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date; use YYYY-MM-DD")
    from app.services.city import get_city_risk_map
    try:
        return get_city_risk_map(city.lower(), date_, layer=layer,
                                 scenario=scenario or None)
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(status_code=404,
                            detail=f"district detail unavailable for '{city}': {e}")


@app.get("/api/cities-available")
def cities_available():
    from app.services.city import available_cities
    return {"cities": available_cities()}


@app.get("/api/forecast-grid")
def forecast_grid_endpoint(
    on: str = Query(..., description="date YYYY-MM-DD"),
    layer: str = Query("tx95_exceedance"),
    spacing: float = Query(1.0, ge=0.5, le=2.0),
):
    """Coarse continuous forecast heat field over Ukraine (GeoJSON grid cells)."""
    try:
        date.fromisoformat(on)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date; use YYYY-MM-DD")
    from app.services.grid import forecast_grid
    try:
        return forecast_grid(on, layer=layer, spacing=spacing)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"grid fetch failed: {e}")


@app.get("/api/cities")
def cities(q: str = Query("", description="search query (en/uk)")):
    matches = city_search(q)
    return {"count": len(matches), "cities": [
        {"id": c.id, "name_en": c.name_en, "name_uk": c.name_uk,
         "lat": c.lat, "lon": c.lon, "oblast_en": c.oblast_en}
        for c in matches]}
