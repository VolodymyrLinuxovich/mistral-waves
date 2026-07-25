"""Runtime access to the precomputed historical event catalogue (real ERA5-Land).

Serves events + per-event daily footprints built offline by
scripts/build_event_catalogue.py. No heavy computation at request time.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.services.severity import summarize_levels

PROCESSED = Path(__file__).resolve().parents[3] / "data" / "processed"
CATALOGUE = PROCESSED / "historical_events.json"
FP_DIR = PROCESSED / "historical_footprints"


def available() -> bool:
    return CATALOGUE.exists()


@lru_cache(maxsize=1)
def _catalogue() -> dict:
    if not CATALOGUE.exists():
        return {"events": [], "event_count": 0}
    return json.loads(CATALOGUE.read_text())


def list_events(year: Optional[int] = None, minimum_level: int = 0,
                limit: int = 50) -> dict:
    cat = _catalogue()
    evs = cat.get("events", [])
    if year is not None:
        evs = [e for e in evs if e.get("year") == year]
    evs = [e for e in evs if e.get("maximum_severity_level", 0) >= minimum_level]
    return {
        "event_count": len(evs), "returned": min(len(evs), limit),
        "generated_years": cat.get("generated_years", []),
        "baseline_status": cat.get("baseline_status"),
        "baseline_years": cat.get("baseline_years"),
        "algorithm_version": cat.get("algorithm_version"),
        "default_event_id": evs[0]["event_id"] if evs else None,
        "events": evs[:limit],
    }


def default_event_id() -> Optional[str]:
    evs = _catalogue().get("events", [])
    return evs[0]["event_id"] if evs else None


@lru_cache(maxsize=8)
def _event_file(eid: str) -> Optional[dict]:
    p = FP_DIR / f"{eid}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def event_detail(eid: str) -> Optional[dict]:
    data = _event_file(eid)
    if data is None:
        return None
    # per-date timeline of the max level (compact; full cells via footprint endpoint)
    timeline = []
    for d in data["dates"]:
        feats = data["footprints"].get(d, {}).get("features", [])
        lvls = [f["properties"]["severity_level"] for f in feats]
        timeline.append({"date": d, "max_level": max(lvls) if lvls else 0,
                         "cells": len(feats)})
    return {"event": data["event"], "dates": data["dates"], "timeline": timeline,
            "provisional_warning": (
                "Classification uses the current provisional baseline; event levels "
                "will be recomputed when the full 1991–2020 climatology is promoted."),
            "data_provenance": {"source": "ERA5-Land reanalysis (observed)",
                                "resolution": data["event"].get("data_resolution")}}


def event_footprint(eid: str, on: str) -> Optional[dict]:
    data = _event_file(eid)
    if data is None:
        return None
    fc = data["footprints"].get(on)
    if fc is None:
        # date outside event range: return empty footprint but valid structure
        fc = {"type": "FeatureCollection", "date": on, "features": []}
    fc = dict(fc)
    fc.update({"mode": "historical", "event_id": eid,
               "available_dates": data["dates"],
               "resolution_note": "Observed ERA5-Land; ~1.0deg analysis grid."})
    return fc


def event_summary(eid: str, on: str) -> Optional[dict]:
    data = _event_file(eid)
    if data is None:
        return None
    feats = data["footprints"].get(on, {}).get("features", [])
    levels = [f["properties"]["severity_level"] for f in feats]
    s = summarize_levels(levels + [0])  # level-0 cells omitted from footprint files
    ev = data["event"]
    return {
        "mode": "historical", "event_id": eid, "date": on,
        "status": "confirmed" if levels else "no_event",
        "headline": (f"Observed heatwave {ev['start_date']}→{ev['end_date']} "
                     f"(max level {ev['maximum_severity_level']}, {ev['duration_days']} days)."),
        "counts_by_level": s["counts_by_level"],
        "footprint_count": 1 if levels else 0,
        "available_dates": data["dates"],
        "event": ev,
        "baseline_status": ev.get("baseline_status"),
        "baseline_years": ev.get("baseline_years"),
    }
