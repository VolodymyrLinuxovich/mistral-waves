# 14-day implementation backlog (Jul 23 → Aug 6)

Vertical slices: data → processing → API → interface → tests → docs.
Legend: [x] done · [~] in progress · [ ] not started.

- **Day 1 (Jul 23)** — Inspect repo; freeze MVP; data-source registry; ADR;
  risk/medical decision log; acceptance tests.
  - [x] Repo inspected (research brief + PDF gen; no app code)
  - [x] `config/data_sources.yaml`, `heatwave_definitions.yaml`,
    `risk_rules.yaml`, `recommendation_rules.yaml`
  - [x] `docs/`: methodology, medical_safety, limitations, data_provenance, ADR
  - [x] **Science core + 29 passing unit tests** (thresholds, indices, detection)
- **Day 2 (Jul 24)** — ERA5-Land download/subset pipeline + real forecast + boundaries.
  - [x] `scripts/download_era5_land.py` (CDS `derived-era5-land-daily-statistics`,
    Ukraine bbox, split by year×stat, cached, restartable) — schema validated live
  - [x] `scripts/compute_thresholds.py` -> compact NetCDF (partial-baseline aware)
  - [x] Open-Meteo forecast adapter (fetch/validate/normalise/cache/provenance)
  - [x] `scripts/download_boundaries.py` -> real ukraine + 27 oblasts (geoBoundaries)
  - [~] Kyiv districts: Overpass flaky; ACTION REQUIRED note, not fabricated
  - [x] `.env` / `.env.example`
- **Day 3 (Jul 25)** — [x] TX90/95/99 + TN90 wired to REAL ERA5 (provisional 2020);
  served via `/api/thresholds` with baseline_status; robust resumable downloader
  (per-year, manifest, validation, bounded retries) running full 1991-2020.
- **Day 4 (Jul 26)** — [x] Forecast adapter live; normalised units; cached +
  stale-cache fallback; [x] forecast↔threshold comparison (`assessment.py`).
- **Day 5 (Jul 27)** — [x] Heat Index, Humidex, tropical night, EHF integrated into
  per-day assessment; [ ] UTCI (labelled) still pending.
- **Day 6 (partial)** — [x] real oblast boundaries; [ ] population-weighted aggregation.
- **Day 7 (Jul 29)** — [x] `/api/location-risk`, `/api/risk-map`, `/api/cities`,
  `/api/data-status` with provenance + baseline_status + provisional flags.
- **Frontend (Day 8 preview)** — [x] MapLibre Ukraine map, city hazard markers,
  date slider, layer selector, city search, click-to-explain, Kyiv detail,
  provisional banner (static SPA; Next.js/TS build still a later slice).
- **Day 5 (Jul 27)** — [~] Heat Index / tropical night / EHF (done); [ ] UTCI or
  labelled shaded-UTCI; numeric tests + assumptions.
- **Day 6 (Jul 28)** — [ ] Boundaries + population; area/pop-weighted aggregation;
  Ukraine + Kyiv layers; CRS validation.
- **Day 7 (Jul 29)** — [ ] FastAPI endpoints w/ timestamps/provenance/uncertainty;
  OpenAPI examples + error responses.
- **Day 8 (Jul 30)** — [ ] Ukraine map + Kyiv detail; timeline, legends, loading,
  data-status panel; mobile.
- **Day 9 (Jul 31)** — [ ] Kyiv health ingestion + archive audit; normalised daily
  table; NO inference until quality checks pass.
- **Day 10 (Aug 1)** — [ ] Exploratory epi notebook; descriptive plots; DLNM or
  labelled fallback; sensitivity analyses.
- **Day 11 (Aug 2)** — [~] Deterministic personal-risk rules (config drafted);
  [ ] engine + personas + explanations + emergency overrides.
- **Day 12 (Aug 3)** — [~] Source-controlled recommendations (config drafted);
  [ ] uk/en copy in UI, privacy controls, disclaimers, medical review.
- **Day 13 (Aug 4)** — [ ] Integrate FE/BE/data; degraded-mode tests; a11y; perf.
- **Day 14 (Aug 5)** — [ ] E2E tests; fix criticals; docs; demo snapshot; build;
  5-min demo script.
- **Aug 6** — [ ] Deploy; present real-data flow, one event, three personas,
  honest health-analysis limits, partnership/validation next steps.
