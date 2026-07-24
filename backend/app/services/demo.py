"""Cached demo mode + offline resilience.

Two things:
  1. offline_snapshot(): a REAL cached Open-Meteo response for Kyiv, used as a
     last-resort fallback so the app keeps working when Open-Meteo is unreachable.
  2. heatwave_scenario(): a CLEARLY-LABELLED SYNTHETIC forecast with a 4-day
     TX95+ heatwave and tropical nights, for demonstrating detection and high/
     critical personal risk. It is explicitly marked synthetic and must never be
     presented as a real forecast.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[3] / "data" / "demo"
SNAPSHOT = DEMO_DIR / "kyiv_forecast_snapshot.json"

KYIV = (50.4501, 30.5234)

_UNITS = {
    "temperature_2m": "°C", "relative_humidity_2m": "%", "dew_point_2m": "°C",
    "apparent_temperature": "°C", "wind_speed_10m": "km/h",
    "wind_direction_10m": "°", "surface_pressure": "hPa",
    "temperature_2m_max": "°C", "temperature_2m_min": "°C",
    "apparent_temperature_max": "°C",
}


def offline_snapshot() -> dict | None:
    """Return the real cached Open-Meteo Kyiv payload, or None if not bundled."""
    if not SNAPSHOT.exists():
        return None
    return json.loads(SNAPSHOT.read_text())


def _diurnal_hours(day: date, tmin: float, tmax: float, base_rh: float, dewpoint: float):
    """Generate 24 hourly rows with a simple diurnal temperature curve."""
    times, temp, rh, dew, app, wind, wdir, pres = [], [], [], [], [], [], [], []
    for h in range(24):
        # Peak ~15:00, trough ~05:00.
        frac = (math.sin((h - 9) / 24 * 2 * math.pi) + 1) / 2
        t = tmin + (tmax - tmin) * frac
        # RH roughly inverse to temperature.
        r = max(20.0, min(95.0, base_rh - (t - tmin) * 1.4))
        times.append(f"{day.isoformat()}T{h:02d}:00")
        temp.append(round(t, 1))
        rh.append(round(r, 0))
        dew.append(dewpoint)
        app.append(round(t + 1.0, 1))
        wind.append(8.0)
        wdir.append(180.0)
        pres.append(1013.0)
    return times, temp, rh, dew, app, wind, wdir, pres


def heatwave_scenario(base: date | None = None) -> dict:
    """Synthetic 14-day Kyiv forecast with a 4-day heatwave + tropical nights."""
    base = base or datetime.now(timezone.utc).date()
    # (tmax, tmin) per day: normal, then a 4-day heatwave (days 3-6), then cooling.
    profile = [
        (28, 16), (29, 17), (30, 18),      # ramp-up
        (36, 21), (37, 22), (38, 23), (37, 22),  # 4-day heatwave, tropical nights
        (32, 19), (30, 18), (29, 17), (28, 16), (27, 15), (26, 15), (25, 14),
    ]
    days = [base + timedelta(days=i) for i in range(len(profile))]
    daily = {"time": [d.isoformat() for d in days],
             "temperature_2m_max": [p[0] for p in profile],
             "temperature_2m_min": [p[1] for p in profile],
             "apparent_temperature_max": [p[0] + 2 for p in profile]}
    H = {k: [] for k in ("time", "temperature_2m", "relative_humidity_2m",
                         "dew_point_2m", "apparent_temperature", "wind_speed_10m",
                         "wind_direction_10m", "surface_pressure")}
    for i, d in enumerate(days):
        tmax, tmin = profile[i]
        dew = 19.0 if tmax >= 34 else 15.0
        t, temp, rh, dp, app, wind, wdir, pres = _diurnal_hours(d, tmin, tmax, 70, dew)
        H["time"] += t; H["temperature_2m"] += temp; H["relative_humidity_2m"] += rh
        H["dew_point_2m"] += dp; H["apparent_temperature"] += app
        H["wind_speed_10m"] += wind; H["wind_direction_10m"] += wdir
        H["surface_pressure"] += pres
    return {
        "latitude": KYIV[0], "longitude": KYIV[1], "timezone": "Europe/Kyiv",
        "daily": daily, "daily_units": _UNITS, "hourly": H, "hourly_units": _UNITS,
        "_scenario": "SYNTHETIC heatwave demonstration — NOT a real forecast",
    }
