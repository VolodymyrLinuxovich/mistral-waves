# Limitations

Version 0.1.0 (2026-07-23, Day 1).

## Meteorological
- ERA5-Land is a **reanalysis** (~9 km), not ground truth and not station data.
- Point queries use the containing grid cell; **no street-level air-temperature
  precision** is implied from a 9–25 km product.
- Forecast uses **one** provider (Open-Meteo working source). We do **not** claim a
  multi-model ensemble — only one model is ingested for the MVP.
- UTCI/WBGT are shade/approximation values (Day 5); not occupational limits.
- Satellite LST is **surface** temperature, shown as an urban-overheating layer,
  never as air temperature.

## Exposure / population
- Gridded population is a versioned estimate; **wartime displacement may make it
  inaccurate**. Population year is always shown.

## Health / epidemiology
- **Kyiv daily health-data availability is unverified** — the only genuine hard
  blocker. If the archive is too short/inconsistent, we present descriptive
  overlays and data-quality findings, not a forced regression.
- Missing values are represented as missing, never zero. No counts are invented.
- Any association shown is **exploratory and not causal proof**.
- No district-level health outcomes are fabricated if data exist only citywide.

## Personal risk
- Deterministic rule engine, **not** a validated clinical model and **not** a
  probability. It cannot predict an individual heart attack, stroke, or death.

## Provisional climatology (current state)
The served thresholds are computed from a **single year (2020)** of ERA5-Land
while the full 1991–2020 download runs. This is exposed everywhere as
`baseline_status: provisional`, `baseline_years: [2020]`,
`expected_baseline: 1991-2020`.

The Kyiv-vs-Lviv threshold difference (Kyiv TX95 ≈ 30.4 °C vs Lviv ≈ 27.2 °C) is
**a pipeline sanity check demonstrating that location-specific thresholds differ
spatially. Final climatological thresholds require the complete 1991–2020
baseline.** A single warm year is not a climatology.

The file `ukraine_heat_thresholds_1991_2020.nc` is **not created or served** until
all 30 baseline years have been downloaded and validated; until then only
`ukraine_heat_thresholds_2020_provisional.nc` exists.

## Data availability at Day 1
- No real meteorological or health data are ingested yet. The science core
  (thresholds/indices/detection) is validated on **clearly-labelled synthetic
  fixtures** (see `test_thresholds.py`), which are algorithm fixtures, **not**
  climate data. Real ERA5-Land/forecast ingestion begins Day 2–4.
