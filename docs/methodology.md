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

## Heatwave severity scale (authoritative engine — `severity.py`)
One implementation classifies every grid cell / location / district / historical
cell. Levels (public-facing):

| Level | Label | Trigger (any) |
|---|---|---|
| 0 | No heatwave | no local TX90 exceedance / no event |
| 1 | Heatwave watch | 1 day Tmax > TX90, or a 2-day sequence forecast to begin |
| 2 | Confirmed heatwave | ≥2 consecutive days Tmax > TX90 (team's 2-day sensitivity, operational confirm) |
| 3 | Severe heatwave | ≥3 days > TX95, or ≥4-day TX90 event with strong cumulative exceedance, or confirmed event + ≥2 tropical nights, or Heat Index ≥ danger (41 °C) |
| 4 | Extreme heatwave | Tmax > TX99 during an active event, or Heat Index ≥ extreme (54 °C) |

Palette (CVD-aware, always paired with **number + label**, never colour alone):
`0 #6b8fa8 · 1 #f4c430 · 2 #e8862e · 3 #a9481c · 4 #c0161c`.

**Warm-season floor (WARM_FLOOR_C = 25 °C).** A percentile exceedance only counts
toward a heat-*health* heatwave when Tmax is also hot in absolute terms. Without
this, a mild winter day (e.g. 17 °C) exceeds the low local winter TX99 and would
be mislabelled "extreme". WHO/WMO heat-health warnings are warm-season concepts.
Comparisons remain strict (`>`); missing values break runs and are flagged.

## Event footprint (`heatwave.py`)
The "Heat hazard" layer is the **event footprint**, not a temperature gradient:
every cell is classified, then adjacent cells of level ≥ 2 are grouped into
connected components (4-neighbour) to form footprints that cross administrative
borders naturally. Oblast boundaries are a reference overlay only.

## Adaptive provisional climatology (`rebuild_provisional_baseline.py`)
While ERA5-Land downloads, thresholds are rebuilt from **every validated
Tmax/Tmin year-pair** (only complete pairs). The product
`ukraine_heat_thresholds_provisional.npz` carries `baseline_status: provisional`,
`baseline_years`, `baseline_year_count`, `expected_year_count: 30`. The
`*_1991_2020.*` name is created only when all 60 files validate. Provisional
percentiles from few years are statistically incomplete and labelled as such.

## Historical replay (`build_event_catalogue.py` + `historical.py`)
Real observed events are detected by running the same severity engine over the
downloaded ERA5-Land daily fields (not synthetic). The catalogue + per-event
daily footprints are precomputed offline and served read-only. Levels use the
current provisional baseline and are recomputed when the full baseline is promoted.

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
