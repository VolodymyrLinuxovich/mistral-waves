"""Authoritative 5-level heatwave severity engine.

ONE implementation used by every hazard surface (national grid, city, districts,
historical replay). Given a per-day series for a single location/cell, it returns
severity level 0-4 plus all components, run-lengths, event context and reasons.

Severity scale (public-facing, spec section 3):
  0 No heatwave      1 Heatwave watch    2 Confirmed heatwave
  3 Severe heatwave  4 Extreme heatwave

Comparisons are STRICT (>). Missing values break runs and are flagged, never
coerced to "not hot". Tropical night = Tmin >= 20 C OR Tmin > local TN90.
"""
from __future__ import annotations

from typing import Optional

ALGORITHM_VERSION = "severity-1.0.0"

LEVELS = {0: "No heatwave", 1: "Heatwave watch", 2: "Confirmed heatwave",
          3: "Severe heatwave", 4: "Extreme heatwave"}
# CVD-aware, ordered light->dark; always paired with number + label in the UI.
PALETTE = {0: "#6b8fa8", 1: "#f4c430", 2: "#e8862e", 3: "#a9481c", 4: "#c0161c"}

# Heat Index categories (degC): caution 27, extreme-caution 32, danger 41, extreme 54.
HI_DANGER = 41.0
HI_EXTREME = 54.0
# "strong cumulative exceedance" for a 4+ day TX90 event (degC-days over TX90).
STRONG_CUM_TX90 = 8.0
# Warm-season absolute floor: a percentile exceedance only counts toward a
# heat-HEALTH heatwave when Tmax is also hot in absolute terms. Without this, a
# mild winter day (e.g. 17 C) can exceed the low local winter TX99 and be
# mislabelled "extreme". WHO/WMO heat-health warnings are warm-season concepts;
# 25 C is a conservative, documented floor (configurable).
WARM_FLOOR_C = 25.0


def is_tropical_night(tmin: Optional[float], tn90: Optional[float]) -> Optional[bool]:
    if tmin is None:
        return None
    if tmin >= 20.0:
        return True
    if tn90 is not None and tmin > tn90:
        return True
    return False


def _exceed(v: Optional[float], thr: Optional[float]) -> Optional[bool]:
    """Heat exceedance: strictly above the local percentile AND above the
    warm-season absolute floor (so winter cold-anomalies aren't 'heatwaves')."""
    if v is None or thr is None:
        return None
    return (v > thr) and (v >= WARM_FLOOR_C)


def classify_series(series: list[dict]) -> list[dict]:
    """Classify each day in a chronological single-location series.

    Each input day: {date, tmax, tmin, tx90, tx95, tx99, tn90,
                     heat_index?, humidex?}. Returns a list of per-day dicts with
    severity_level/label and all section-4 components.
    """
    n = len(series)
    ex90 = [_exceed(d.get("tmax"), d.get("tx90")) for d in series]
    ex95 = [_exceed(d.get("tmax"), d.get("tx95")) for d in series]
    ex99 = [_exceed(d.get("tmax"), d.get("tx99")) for d in series]
    trop = [is_tropical_night(d.get("tmin"), d.get("tn90")) for d in series]

    # backward run lengths (consecutive True ending at i; None/False resets)
    run90 = [0] * n
    run95 = [0] * n
    runtrop = [0] * n
    for i in range(n):
        run90[i] = (run90[i - 1] + 1) if (i > 0 and ex90[i] is True and run90[i - 1] and ex90[i-1] is True) else (1 if ex90[i] is True else 0)
        run95[i] = (run95[i - 1] + 1) if (i > 0 and ex95[i] is True and run95[i - 1] and ex95[i-1] is True) else (1 if ex95[i] is True else 0)
        runtrop[i] = (runtrop[i - 1] + 1) if (i > 0 and trop[i] is True and runtrop[i - 1]) else (1 if trop[i] is True else 0)

    # contiguous TX90 blocks -> events (block is a "confirmed event" if len>=2)
    block_of = [None] * n          # index into blocks
    blocks = []                    # list of (start_idx, end_idx_inclusive)
    i = 0
    while i < n:
        if ex90[i] is True:
            j = i
            while j + 1 < n and ex90[j + 1] is True:
                j += 1
            bi = len(blocks)
            blocks.append((i, j))
            for k in range(i, j + 1):
                block_of[k] = bi
            i = j + 1
        else:
            i += 1

    out = []
    for i, d in enumerate(series):
        tmax, tmin = d.get("tmax"), d.get("tmin")
        hi = d.get("heat_index")
        bi = block_of[i]
        block = blocks[bi] if bi is not None else None
        block_len = (block[1] - block[0] + 1) if block else 0
        # cumulative exceedances over the current active block
        cum90 = cum95 = 0.0
        trop_in_event = 0
        if block:
            for k in range(block[0], i + 1):
                if series[k].get("tmax") is not None and series[k].get("tx90") is not None:
                    cum90 += max(0.0, series[k]["tmax"] - series[k]["tx90"])
                if series[k].get("tmax") is not None and series[k].get("tx95") is not None:
                    cum95 += max(0.0, series[k]["tmax"] - series[k]["tx95"])
                if trop[k] is True:
                    trop_in_event += 1

        # look-ahead watch: a 2+ day TX90 sequence forecast to begin tomorrow
        upcoming = (i + 2 < n) and ex90[i + 1] is True and ex90[i + 2] is True

        reasons = []
        level = 0
        active = run90[i] >= 2                       # confirmed active event today
        if active and ex99[i] is True:
            level = 4; reasons.append("Tmax exceeds the local TX99 extreme threshold during an active event.")
        elif hi is not None and hi >= HI_EXTREME:
            level = 4; reasons.append(f"Extreme Heat Index ({hi} degC).")
        elif run95[i] >= 3:
            level = 3; reasons.append(f"{run95[i]} consecutive days above local TX95.")
        elif run90[i] >= 4 and cum90 >= STRONG_CUM_TX90:
            level = 3; reasons.append(f"{run90[i]}-day TX90 event with strong cumulative exceedance ({round(cum90,1)} degC-days).")
        elif active and runtrop[i] >= 2:
            level = 3; reasons.append(f"Confirmed event with {runtrop[i]} consecutive tropical nights.")
        elif hi is not None and hi >= HI_DANGER:
            level = 3; reasons.append(f"Dangerous Heat Index ({hi} degC).")
        elif run90[i] >= 2:
            level = 2; reasons.append(f"{run90[i]} consecutive days above local TX90 (confirmed).")
        elif ex90[i] is True:
            level = 1; reasons.append("Tmax above local TX90 for one day (persistence not yet met).")
        elif upcoming:
            level = 1; reasons.append("A multi-day TX90 sequence is forecast to begin.")
        else:
            reasons.append("No local TX90 exceedance; no active event.")

        # tropical night escalates a borderline active event by one level (cap 4)
        if level == 2 and trop[i] is True and level < 3:
            pass  # single tropical night noted but does not alone push to severe
        if trop[i] is True:
            reasons.append("Tropical night (Tmin ≥ 20 °C or > local TN90).")

        out.append({
            "date": d.get("date"),
            "severity_level": level, "severity_label": LEVELS[level],
            "severity_color": PALETTE[level],
            "tmax": tmax, "tmin": tmin,
            "tx90": d.get("tx90"), "tx95": d.get("tx95"),
            "tx99": d.get("tx99"), "tn90": d.get("tn90"),
            "tx90_exceedance": round(tmax - d["tx90"], 2) if (tmax is not None and d.get("tx90") is not None) else None,
            "tx95_exceedance": round(tmax - d["tx95"], 2) if (tmax is not None and d.get("tx95") is not None) else None,
            "current_tx90_run_length": run90[i],
            "current_tx95_run_length": run95[i],
            "cumulative_tx90_exceedance": round(cum90, 2),
            "cumulative_tx95_exceedance": round(cum95, 2),
            "tropical_night": trop[i],
            "consecutive_tropical_nights": runtrop[i],
            "tropical_nights_in_event": trop_in_event,
            "heat_index": hi, "humidex": d.get("humidex"),
            "event_id": f"blk{bi}" if bi is not None else None,
            "event_start": series[block[0]]["date"] if block else None,
            "event_end": series[block[1]]["date"] if block else None,
            "event_duration_so_far": (i - block[0] + 1) if block else 0,
            "forecast_event_duration": block_len,
            "category_reasons": reasons,
            "data_quality_flag": "missing" if (tmax is None or d.get("tx90") is None) else "ok",
        })
    return out


def summarize_levels(cell_levels: list[int]) -> dict:
    """Counts by level + a status string for a set of classified cells."""
    counts = {lvl: 0 for lvl in range(5)}
    for lv in cell_levels:
        counts[lv] = counts.get(lv, 0) + 1
    if counts[4] or counts[3] or counts[2]:
        status = "confirmed"
    elif counts[1]:
        status = "watch"
    else:
        status = "no_event"
    return {"counts_by_level": counts, "status": status}
