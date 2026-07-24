"""Calendar-day percentile climatology (TX90/TX95/TX99/TN90).

For every calendar day we take a +/-15-day window around that day across the
1991-2020 baseline and compute a percentile of daily Tmax (or Tmin for TN90).
This is the standard ETCCDI / WMO approach and gives *local, season-aware*
thresholds instead of a single fixed number (spec section 2).

Design notes
------------
* Pure standard library so it runs before any scientific stack is installed.
* Day-of-year is normalised onto a fixed 365-day calendar; Feb 29 borrows the
  Feb 28 window. This is documented and kept deterministic.
* Percentile uses the linear ("type 7") interpolation, matching numpy's default
  so results line up when we later vectorise with numpy/xarray.
* Optional circular smoothing of the resulting 365-day threshold curve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

# Cumulative days before the start of each month in a non-leap year.
_MONTH_CUMDAYS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def day_of_year_365(d: date) -> int:
    """Return a 0-based day index on a fixed 365-day calendar.

    Feb 29 maps to Feb 28's index (58) so leap days reuse the late-February
    window rather than shifting the whole climatology.
    """
    if d.month == 2 and d.day == 29:
        return 58  # Feb 28 (0-based)
    doy = _MONTH_CUMDAYS[d.month - 1] + (d.day - 1)
    # After Feb 29 in a leap year the naive ordinal is one too high; but because
    # we build the index from month/day directly, no correction is needed.
    return doy


def percentile_linear(sorted_values: Sequence[float], p: float) -> float:
    """Percentile with linear interpolation between closest ranks (numpy type 7)."""
    if not sorted_values:
        raise ValueError("cannot take percentile of empty sequence")
    if p <= 0:
        return float(sorted_values[0])
    if p >= 100:
        return float(sorted_values[-1])
    n = len(sorted_values)
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 >= n:
        return float(sorted_values[-1])
    return float(sorted_values[lo] + frac * (sorted_values[lo + 1] - sorted_values[lo]))


def _circular_window_indices(center: int, half: int, size: int = 365) -> List[int]:
    return [(center + k) % size for k in range(-half, half + 1)]


@dataclass
class ClimatologyThresholds:
    """365 per-calendar-day thresholds for one location and one percentile set."""

    percentile: float
    variable: str  # "tmax" or "tmin"
    window_days: int
    baseline_start: int
    baseline_end: int
    values: List[Optional[float]] = field(default_factory=lambda: [None] * 365)
    n_years_per_day: List[int] = field(default_factory=lambda: [0] * 365)

    def for_date(self, d: date) -> Optional[float]:
        return self.values[day_of_year_365(d)]


def compute_thresholds(
    observations: Sequence[Tuple[date, Optional[float]]],
    percentile: float,
    variable: str = "tmax",
    window_days: int = 15,
    min_samples: int = 30,
) -> ClimatologyThresholds:
    """Compute a +/-window_days calendar-day percentile climatology.

    Parameters
    ----------
    observations : (date, value) pairs across the baseline period. ``None``
        values are missing and excluded (never treated as 0).
    percentile : e.g. 90, 95, 99.
    variable : label only ("tmax"/"tmin"); the caller supplies the right series.
    window_days : half-width of the calendar-day window (default 15 -> 31 days).
    min_samples : minimum non-missing samples required to emit a threshold;
        below this the day's threshold is left ``None`` (flagged, not faked).
    """
    # Bucket observed values by fixed-calendar day-of-year.
    by_doy: Dict[int, List[float]] = {i: [] for i in range(365)}
    years_by_doy: Dict[int, set] = {i: set() for i in range(365)}
    for d, v in observations:
        if v is None:
            continue
        doy = day_of_year_365(d)
        by_doy[doy].append(v)
        years_by_doy[doy].add(d.year)

    baseline_years = sorted({d.year for d, v in observations if v is not None})
    result = ClimatologyThresholds(
        percentile=percentile,
        variable=variable,
        window_days=window_days,
        baseline_start=baseline_years[0] if baseline_years else 0,
        baseline_end=baseline_years[-1] if baseline_years else 0,
    )

    for center in range(365):
        pooled: List[float] = []
        years: set = set()
        for idx in _circular_window_indices(center, window_days):
            pooled.extend(by_doy[idx])
            years |= years_by_doy[idx]
        if len(pooled) < min_samples:
            result.values[center] = None
            result.n_years_per_day[center] = len(years)
            continue
        pooled.sort()
        result.values[center] = round(percentile_linear(pooled, percentile), 3)
        result.n_years_per_day[center] = len(years)
    return result


def smooth_circular(values: Sequence[Optional[float]], window: int = 5) -> List[Optional[float]]:
    """Optional circular moving-average smoothing of a 365-day threshold curve.

    Windows containing any missing value produce ``None`` at that position, so
    smoothing never invents a threshold where data were absent.
    """
    n = len(values)
    half = window // 2
    out: List[Optional[float]] = []
    for i in range(n):
        window_vals = [values[(i + k) % n] for k in range(-half, half + 1)]
        if any(v is None for v in window_vals):
            out.append(None)
        else:
            out.append(round(sum(window_vals) / len(window_vals), 3))
    return out
