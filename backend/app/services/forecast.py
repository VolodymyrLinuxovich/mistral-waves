"""Open-Meteo forecast adapter.

Implements the adapter contract (spec section 11): fetch, validate, normalize,
cache, provenance metadata, missing-data handling, last-successful-update status,
graceful failure. Requests go through the backend (never thousands of direct
browser calls); responses are cached on disk with a TTL.

Open-Meteo requires no API key for non-commercial use.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from app.services import demo

# Cache dir is env-configurable so serverless (read-only FS) can point at /tmp.
_CACHE_ROOT = Path(os.environ.get("WAVES_CACHE_DIR",
                                  Path(__file__).resolve().parents[3] / "data" / "cache"))
CACHE_DIR = _CACHE_ROOT / "forecast"
BASE_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 3600  # 1 hour; forecasts update a few times a day

HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "apparent_temperature", "wind_speed_10m", "wind_direction_10m",
    "surface_pressure",
]
DAILY_VARS = [
    "temperature_2m_max", "temperature_2m_min", "apparent_temperature_max",
]


@dataclass
class ForecastResult:
    provider: str
    latitude: float
    longitude: float
    timezone: str
    fetched_utc: str
    from_cache: bool
    daily: dict[str, Any]
    hourly: dict[str, Any]
    units: dict[str, str]
    provenance: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


class ForecastError(RuntimeError):
    pass


def _cache_key(lat: float, lon: float, days: int) -> Path:
    raw = f"{lat:.3f}_{lon:.3f}_{days}"
    h = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return CACHE_DIR / f"om_{h}.json"


def _validate(payload: dict) -> list[str]:
    """Return a list of warnings; raise ForecastError on fatal structural issues."""
    warnings: list[str] = []
    if "daily" not in payload or "time" not in payload.get("daily", {}):
        raise ForecastError("response missing 'daily.time'")
    for var in DAILY_VARS:
        series = payload["daily"].get(var)
        if series is None:
            warnings.append(f"daily variable missing: {var}")
        elif any(v is None for v in series):
            n = sum(1 for v in series if v is None)
            warnings.append(f"daily {var}: {n} missing value(s) (kept as null, not 0)")
    return warnings


def _result_from_payload(payload: dict, provider: str, from_cache: bool,
                         extra_warnings: list[str], license_note: str) -> ForecastResult:
    warnings = _validate(payload) + extra_warnings
    units = {}
    units.update(payload.get("hourly_units", {}))
    units.update(payload.get("daily_units", {}))
    return ForecastResult(
        provider=provider,
        latitude=payload.get("latitude", 0.0),
        longitude=payload.get("longitude", 0.0),
        timezone=payload.get("timezone", "Europe/Kyiv"),
        fetched_utc=datetime.now(timezone.utc).isoformat(),
        from_cache=from_cache,
        daily=payload.get("daily", {}),
        hourly=payload.get("hourly", {}),
        units=units,
        provenance={"source": provider, "license": license_note,
                    "model_note": "single provider; NOT a multi-model ensemble"},
        warnings=warnings,
    )


def fetch_forecast(
    latitude: float,
    longitude: float,
    forecast_days: int = 14,
    timezone_name: str = "Europe/Kyiv",
    use_cache: bool = True,
    client: Optional[httpx.Client] = None,
    scenario: Optional[str] = None,
) -> ForecastResult:
    """Fetch (or serve cached) an Open-Meteo forecast for one point.

    scenario="heatwave" returns the CLEARLY-LABELLED synthetic demo scenario
    (no network). On live failure with no cache, falls back to the bundled real
    Kyiv snapshot so the app never crashes offline.
    """
    if scenario == "heatwave":
        return _result_from_payload(
            demo.heatwave_scenario(), provider="demo_heatwave (SYNTHETIC)",
            from_cache=True, license_note="synthetic demonstration data",
            extra_warnings=["SYNTHETIC heatwave demo scenario — not a real forecast."])

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    forecast_days = max(1, min(forecast_days, 16))
    cache_path = _cache_key(latitude, longitude, forecast_days)

    # Serve fresh cache.
    if use_cache and cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            cached = json.loads(cache_path.read_text())
            cached["from_cache"] = True
            return ForecastResult(**cached)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "timezone": timezone_name,
        "forecast_days": forecast_days,
    }

    owns_client = client is None
    client = client or httpx.Client(timeout=20)
    try:
        resp = client.get(BASE_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:  # graceful failure -> stale cache, then offline snapshot
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            cached["from_cache"] = True
            result = ForecastResult(**cached)
            result.warnings.append(
                f"live fetch failed ({type(e).__name__}); served STALE cache."
            )
            return result
        snap = demo.offline_snapshot()
        if snap is not None:
            return _result_from_payload(
                snap, provider="open_meteo (OFFLINE SNAPSHOT)", from_cache=True,
                license_note="real Open-Meteo response cached for offline use",
                extra_warnings=[f"live fetch failed ({type(e).__name__}); served bundled "
                                "OFFLINE Kyiv snapshot (real but not current)."])
        raise ForecastError(f"live fetch failed and no cache/snapshot: {e}") from e
    finally:
        if owns_client:
            client.close()

    warnings = _validate(payload)
    fetched = datetime.now(timezone.utc).isoformat()
    units = {}
    units.update(payload.get("hourly_units", {}))
    units.update(payload.get("daily_units", {}))

    result_dict = dict(
        provider="open_meteo",
        latitude=payload.get("latitude", latitude),
        longitude=payload.get("longitude", longitude),
        timezone=payload.get("timezone", timezone_name),
        fetched_utc=fetched,
        from_cache=False,
        daily=payload.get("daily", {}),
        hourly=payload.get("hourly", {}),
        units=units,
        provenance={
            "source": "Open-Meteo Forecast API",
            "url": BASE_URL,
            "license": "non-commercial free tier",
            "model_note": "single provider; NOT a multi-model ensemble",
            "elevation_m": payload.get("elevation"),
            "utc_offset_seconds": payload.get("utc_offset_seconds"),
        },
        warnings=warnings,
    )
    cache_path.write_text(json.dumps(result_dict))
    return ForecastResult(**result_dict)
