# Methodology

Status: living document. Version 0.1.0 (2026-07-23, Day 1).

## Four conceptually separate layers (never conflated)

| Layer | What it measures | What it does NOT claim |
|---|---|---|
| **A. Hazard** | How hot/humid/persistent/unusual conditions are | That anyone became ill |
| **B. Exposure** | How many people are in affected areas + conditions they experience | Individual medical outcome |
| **C. Vulnerability** | Characteristics that can raise susceptibility | A diagnosis |
| **D. Health outcome** | Observed aggregated events (103 calls, strokes, MI, deaths) | Causation from correlation |

Conceptual model:
`population risk = hazard × exposure × vulnerability, modified by protective capacity`.

A grid cell exceeding a threshold **detects heat hazard only**. It is not a patient.

## Heatwave definitions

Baseline: **ERA5-Land 1991–2020** (a gridded *reanalysis*, not ground truth — source
metadata, resolution, and units are preserved). Thresholds are **local and
calendar-day-specific**, computed on a **±15-day window** per calendar day, using
linear-interpolation percentiles (numpy type-7 equivalent). Feb 29 borrows the
Feb 28 window. See `backend/app/services/heat/thresholds.py`.

| Definition | Rule | Role |
|---|---|---|
| Primary | ≥3 consecutive days Tmax > TX95 | primary health definition |
| Early signal | ≥3 consecutive days Tmax > TX90 | early warning |
| Extreme | Tmax > TX99 / UTCI very-strong–extreme / extreme EHF | emergency |
| Nighttime | Tmin ≥ 20 °C or Tmin > TN90 | loss of overnight recovery (shown separately) |
| Sensitivity | ≥2 consecutive days Tmax > TX90 (team's original) | **sensitivity mode only**, never the sole health definition |

Comparison is **strict** (`>`); a value equal to the threshold does not exceed.
Detection uses run-length encoding (`detection.py`) and reports start, end,
duration, max/mean/cumulative exceedance, tropical nights, and recovery period.
Missing daily values **break runs and are flagged** — never coerced to "cool".

## Indices (`indices.py`)
Each returns value + unit + validity flag + source; no silent extrapolation.
- **Heat Index** — NWS Rothfusz 1990 (shade apparent temp; valid ~T≥26.7 °C, RH≥40%).
- **Humidex** — Environment Canada.
- **EHF** — Nairn & Fawcett 2015 (needs 32-day lead-in).
- **Tropical night** — WMO/ETCCDI (≥20 °C) + local TN90.
- **UTCI / shaded-UTCI approximation, WBGT** — scheduled Day 5; will be labelled
  explicitly as shade/approximation and only computed when inputs are in range.

LST (satellite) is **surface** temperature and is never labelled as 2 m air temperature.

## Exposure aggregation (Day 6)
Population-weighted mean per admin unit:
`E[a,t] = Σ_i pop_weight[i,a]·metric[i,t] / Σ_i pop_weight[i,a]`, plus max and the
90th/95th spatial percentile (a citywide mean hides dangerous neighbourhoods).

## Epidemiology (exploratory, Day 10)
Daily-count time-series design (quasi-Poisson / negative binomial), DLNM where
practical, `offset(log(population))`, lag 0–7 primary (0–3 / 0–10 sensitivity),
controlling for long-term trend, seasonality, day-of-week, holidays, humidity,
and PM2.5/O₃/NO₂ where complete. Baseline = warm-season non-heat / matched days,
**not** all non-heatwave days. If data are too short/inconsistent, we produce
descriptive overlays and say so — no forced regression. **Association ≠ causation.**
