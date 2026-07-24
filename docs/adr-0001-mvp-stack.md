# ADR-0001: MVP technology stack

Date: 2026-07-23 · Status: accepted · Deciders: technical product lead + architect.

## Context
14-day sprint (Jul 23 → Aug 6) to ship a deployable, scientifically defensible
heat-health MVP for Ukraine (national + Kyiv detail). Must be reproducible and
transparent, not over-engineered. Starting point: a research brief + PDF generator
only — no existing application to preserve.

## Decision
- **Backend:** Python 3.12, FastAPI, Pydantic, xarray, pandas, NumPy, GeoPandas,
  rioxarray/Rasterio, statsmodels. Science core (thresholds/indices/detection)
  kept **standard-library-only** so it is testable before the geo stack installs.
- **Frontend:** Next.js + TypeScript + MapLibre GL JS, responsive, uk/en.
- **Storage:** Parquet (tables), GeoJSON/vector tiles (small admin layers), COG
  (raster map layers). SQLite only if a light store is needed.
- **Deployment:** Docker + Docker Compose, env template, `/api/health` check.
- **Adapters** isolate every data provider (fetch/validate/normalize/cache/
  provenance/missing/last-update/graceful-fail).

## Rejected (spec §12/§18)
TimescaleDB, PostGIS-as-default, Dask, Celery, Redis, TorchServe, distributed
infra, neural downscaling, and any trained personal/forecast model. These do not
solve a current blocker within 14 days. The brief mentioned Timescale/Dask; we
deliberately down-scope. Adapter interfaces keep the upgrade path open.

## Consequences
- Fast, reproducible local demo; low operational surface.
- Science core reviewable on Day 1 (done — 29 passing tests).
- Heavy geo/epi dependencies added per-slice, not up front.
- Running dev machine is Python 3.14; Docker pins 3.12 for parity. Core avoids
  version-sensitive deps by using stdlib only.
