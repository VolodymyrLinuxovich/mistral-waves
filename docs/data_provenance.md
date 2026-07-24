# Data provenance

Version 0.1.0 (2026-07-23). Machine-readable registry: `config/data_sources.yaml`.

Every adapter must implement: **fetch, validate, normalize, cache, provenance
metadata, missing-data handling, last-successful-update status, graceful failure.**
No API response is ever fabricated; if a live source is unavailable we use a
clearly-labelled cached real-data snapshot.

## Source matrix

| Layer | Source | Credential | Status | Key caveats |
|---|---|---|---|---|
| Climatology (reference) | ERA5-Land via CDS | `CDSAPI_KEY` | adapter stub | native ~9 km; run once offline |
| Climatology (pragmatic) | ERA5-Land via Open-Meteo | none | planned working | credential-free path |
| Forecast (working) | Open-Meteo | none | planned working | single model — not an ensemble |
| Forecast (alt) | ECMWF Open Data | none | adapter stub | second adapter only |
| Health | Kyiv daily reports | none | **unverified** | scrape defensively; may be descriptive-only |
| Air quality | Open-Meteo AQ / Kyiv API | none | planned | PM2.5, O₃, NO₂ prioritised |
| Population | WorldPop / GHS-POP | none | planned | show year; displacement caveat |
| Boundaries (national/oblast) | geoBoundaries gbOpen | none | done | CC-BY 4.0 |
| Boundaries (Kyiv districts) | OpenStreetMap via Overpass | none | done | ODbL; 10 raiony, admin_level=10; retrieved 2026-07-24; see kyiv_districts.provenance.json |
| Urban overheat | Sentinel-3/MODIS LST + NDVI | none | optional | LST = surface temp, not air temp |

## Health-report audit checklist (Day 9, before any inference)
first/last available date · missing dates · format changes · duplicated reports ·
label changes · occurrence-date vs publication-date · daily vs other interval ·
consistent Kyiv geography · retrospective corrections.

Scraper persists per report: source URL, publication timestamp, parsed report
date, raw text snapshot/checksum, extraction status, parser version, extracted
variables, warnings.
