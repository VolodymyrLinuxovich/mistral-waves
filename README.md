# Waves — Ukraine heat-health risk platform (MVP)

A scientifically defensible MVP for heatwave hazard and heat-health risk across
Ukraine, with a detailed Kyiv view. **Not a medical device.** It separates four
layers that are never conflated: **hazard · exposure · vulnerability · health
outcome** (see `docs/methodology.md`).

Sprint: 2026-07-23 → 2026-08-06. This repo is being built in vertical slices;
see `docs/backlog.md` for day-by-day status.

## What works today
**Scientific core** (dependency-free): calendar-day percentile climatology
(TX90/95/99, TN90, ±15-day window), heat-stress indices (Heat Index, Humidex,
EHF, tropical night) with citations/units/validity flags, and run-length
heatwave detection with all spec definitions (incl. the team's 2-day TX90 as a
labelled sensitivity mode).

**Real data pipelines + API + map:**
- ERA5-Land download (CDS `derived-era5-land-daily-statistics`): robust,
  resumable, per-year, manifest + NetCDF validation, bounded retries/backoff.
- Real thresholds served via `/api/thresholds` — currently **provisional
  (2020 only)** while the full 1991–2020 baseline downloads. Baseline state is
  exposed everywhere as `baseline_status` / `baseline_years` / `expected_baseline`.
- Open-Meteo forecast adapter (cached, graceful fallback) + forecast↔threshold
  comparison and heatwave detection in `/api/location-risk`, `/api/risk-map`.
- MapLibre SPA (`frontend/index.html`): Ukraine map, city hazard markers, date
  slider, layer selector, city search, click-to-explain, Kyiv detail, and a
  prominent **provisional-data banner**.

> The Kyiv-vs-Lviv threshold difference is a **pipeline sanity check** showing
> location-specific thresholds differ spatially — **not** a climatology. Final
> thresholds require the complete 1991–2020 baseline. The
> `ukraine_heat_thresholds_1991_2020.nc` file is created only once all 30 years
> download and validate.

### Run the tests (backend core needs no network)
```bash
.venv/bin/python -m unittest discover -s backend/tests -v   # 40 tests pass
```

### Run the app locally
```bash
PYTHONPATH=backend .venv/bin/python -m uvicorn app.main:app --port 8010   # API
python -m http.server 8080                                                # static frontend
# open http://127.0.0.1:8080/frontend/index.html
```

## Layout
```
backend/app/services/heat/   # thresholds.py, indices.py, detection.py (stdlib-only core)
backend/tests/               # unittest suite
config/                      # heatwave_definitions, risk_rules, recommendation_rules, data_sources
docs/                        # methodology, medical_safety, limitations, data_provenance, ADR, backlog
pipelines/                   # era5/, forecast/ (Day 2-4)
data/                        # sample/, metadata/
```

## Documentation
- `docs/methodology.md` — science + definitions
- `docs/medical_safety.md` — guardrails (fluid restriction, medication, emergencies)
- `docs/limitations.md` — what this does and does not claim
- `docs/data_provenance.md` — sources + adapter contract
- `docs/adr-0001-mvp-stack.md` — stack decisions

## Principles
No fabricated data or API responses. Missing values stay missing (never zeroed).
Association is not causation. No fake personal probabilities. Full disclosure of
timestamps, provenance, uncertainty, missingness, and limitations.
