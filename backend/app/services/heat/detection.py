"""Heatwave event detection via run-length encoding.

Given a daily series of (date, Tmax, per-day threshold) plus optional night
information, identify maximal runs of consecutive qualifying days and summarise
each event. Implements the configurable definitions from spec section 2:

    PRIMARY   : >=3 consecutive days Tmax > TX95
    EARLY     : >=3 consecutive days Tmax > TX90
    EXTREME   : Tmax > TX99 (or other explicit emergency trigger)
    SENSITIVITY (team's original): >=2 consecutive days Tmax > TX90

Rules that are tested explicitly (acceptance criteria + section 2 test list):
    * Comparison is STRICT: Tmax exactly equal to threshold does NOT qualify.
    * A missing Tmax (None) or missing threshold BREAKS the run and is flagged;
      missing is never coerced to "not hot" silently beyond breaking the run.
    * Runs are counted purely by consecutive calendar records in input order;
      the caller is responsible for passing a gap-free daily series (gaps should
      appear as explicit None records so they break runs and are flagged).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Optional, Sequence


@dataclass(frozen=True)
class DayRecord:
    """One day of input to the detector."""

    day: date
    tmax: Optional[float]
    threshold: Optional[float]
    tmin: Optional[float] = None
    tn_threshold: Optional[float] = None  # TN90 for tropical-night classification


@dataclass
class HeatwaveEvent:
    definition: str
    start: date
    end: date
    duration_days: int
    max_exceedance: float          # peak (Tmax - threshold), degC
    cumulative_exceedance: float   # sum of daily exceedances, degC-days
    mean_exceedance: float         # intensity, degC
    tropical_nights: int
    recovery_days: Optional[int] = None  # cool days until next event (None if series end)
    had_missing_in_gap: bool = False
    day_count_flagged_missing: int = 0


@dataclass
class DetectionResult:
    definition: str
    min_duration: int
    events: List[HeatwaveEvent] = field(default_factory=list)
    n_days_total: int = 0
    n_days_missing: int = 0
    n_days_qualifying: int = 0
    warnings: List[str] = field(default_factory=list)


def _tropical_night(rec: DayRecord, absolute_c: float = 20.0) -> Optional[bool]:
    if rec.tmin is None:
        return None
    if rec.tmin >= absolute_c:
        return True
    if rec.tn_threshold is not None and rec.tmin > rec.tn_threshold:
        return True
    return False


def detect_events(
    records: Sequence[DayRecord],
    min_duration: int = 3,
    definition: str = "primary_tx95",
    tropical_absolute_c: float = 20.0,
) -> DetectionResult:
    """Detect heatwave events by run-length encoding of qualifying days.

    A day *qualifies* when both tmax and threshold are present and
    ``tmax > threshold`` (strict). A maximal run of qualifying days whose length
    is >= ``min_duration`` becomes an event.
    """
    result = DetectionResult(definition=definition, min_duration=min_duration,
                             n_days_total=len(records))

    def qualifies(rec: DayRecord) -> Optional[bool]:
        if rec.tmax is None or rec.threshold is None:
            return None
        return rec.tmax > rec.threshold

    # First pass: qualification + missing accounting.
    quals: List[Optional[bool]] = []
    for rec in records:
        q = qualifies(rec)
        quals.append(q)
        if q is None:
            result.n_days_missing += 1
        elif q:
            result.n_days_qualifying += 1

    # Second pass: run-length encoding of True runs (None breaks a run).
    i = 0
    n = len(records)
    runs: List[tuple] = []  # (start_idx, end_idx_inclusive)
    while i < n:
        if quals[i] is True:
            j = i
            while j + 1 < n and quals[j + 1] is True:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1

    events: List[HeatwaveEvent] = []
    for (s, e) in runs:
        length = e - s + 1
        if length < min_duration:
            continue
        exceedances = [records[k].tmax - records[k].threshold for k in range(s, e + 1)]
        trop = 0
        flagged_missing = 0
        for k in range(s, e + 1):
            tn = _tropical_night(records[k], tropical_absolute_c)
            if tn is True:
                trop += 1
            elif tn is None:
                flagged_missing += 1
        events.append(
            HeatwaveEvent(
                definition=definition,
                start=records[s].day,
                end=records[e].day,
                duration_days=length,
                max_exceedance=round(max(exceedances), 3),
                cumulative_exceedance=round(sum(exceedances), 3),
                mean_exceedance=round(sum(exceedances) / length, 3),
                tropical_nights=trop,
                day_count_flagged_missing=flagged_missing,
            )
        )

    # Recovery period: qualifying-free days between the end of one event and the
    # start of the next qualifying day (or None if the series ends first).
    for idx, ev in enumerate(events):
        end_idx = next(k for k in range(n) if records[k].day == ev.end)
        recovery = 0
        had_missing = False
        k = end_idx + 1
        while k < n and quals[k] is not True:
            recovery += 1
            if quals[k] is None:
                had_missing = True
            k += 1
        ev.recovery_days = recovery if k < n else None
        ev.had_missing_in_gap = had_missing

    result.events = events
    if result.n_days_missing:
        result.warnings.append(
            f"{result.n_days_missing} day(s) had missing Tmax or threshold; "
            "these broke runs and are flagged, not treated as cool days."
        )
    return result


# Convenience presets matching the documented definitions (spec section 2).
def detect_primary(records: Sequence[DayRecord]) -> DetectionResult:
    """>=3 consecutive days Tmax > TX95 (primary health definition)."""
    return detect_events(records, min_duration=3, definition="primary_tx95")


def detect_early_signal(records: Sequence[DayRecord]) -> DetectionResult:
    """>=3 consecutive days Tmax > TX90 (early warning)."""
    return detect_events(records, min_duration=3, definition="early_tx90")


def detect_sensitivity_2day(records: Sequence[DayRecord]) -> DetectionResult:
    """Team's original: >=2 consecutive days Tmax > TX90 (sensitivity mode only)."""
    return detect_events(records, min_duration=2, definition="sensitivity_tx90_2day")
