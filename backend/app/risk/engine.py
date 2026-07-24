"""Deterministic personal heat-risk rule engine.

Produces a category (low/moderate/high/critical) with explicit reasons. It never
produces a probability/percentage. Control flow mirrors config/risk_rules.yaml;
recommendation text is loaded from config/recommendation_rules.yaml (versioned,
source-controlled). Emergency red flags override everything.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from app.risk.models import ProfileRiskRequest

RULE_ENGINE_VERSION = "0.1.0"
CONFIG = Path(__file__).resolve().parents[3] / "config"

CATEGORIES = ["low", "moderate", "high", "critical"]


def _clamp(i: int) -> int:
    return max(0, min(3, i))


@lru_cache(maxsize=1)
def _recommendations_cfg() -> dict:
    return yaml.safe_load((CONFIG / "recommendation_rules.yaml").read_text())


def _major_vulnerabilities(v) -> list[str]:
    out = []
    if v.age_band == "75_plus":
        out.append("age 75+")
    if v.age_band == "under_5":
        out.append("young child")
    if v.cardiovascular:
        out.append("cardiovascular disease")
    if v.heart_failure:
        out.append("heart failure")
    if v.ckd:
        out.append("chronic kidney disease")
    if v.pregnancy:
        out.append("pregnancy")
    return out


def _vulnerability_count(v) -> int:
    flags = ["pregnancy", "cardiovascular", "heart_failure", "hypertension", "ckd",
             "diabetes", "chronic_respiratory", "obesity",
             "thermoregulation_medication", "limited_mobility"]
    n = sum(1 for f in flags if getattr(v, f))
    if v.age_band in ("65_74", "75_plus", "under_5"):
        n += 1
    return n


def _emergency_result(req: ProfileRiskRequest, env) -> dict:
    cfg = _recommendations_cfg()
    rec = next((r for r in cfg["recommendations"] if r["id"] == "REC-EMERGENCY-103"), {})
    return {
        "category": "critical",
        "category_index": 3,
        "is_emergency": True,
        "confidence": "emergency override (symptom-based, not hazard-based)",
        "top_reasons": [
            {"factor": "emergency_symptom", "detail": f"Reported: {s.replace('_', ' ')}"}
            for s in req.symptoms.triggered()[:3]
        ],
        "protective_factors": [],
        "protection_applied": False,
        "recommendations": [_ser_rec(rec)] if rec else [],
        "guardrails": [],
        "emergency": {
            "active": True,
            "symptoms": req.symptoms.triggered(),
            "message_uk": rec.get("uk", "").strip(),
            "message_en": rec.get("en", "").strip(),
            "call": "103",
        },
        "disclaimer_uk": cfg["global_disclaimer"]["uk"].strip(),
        "disclaimer_en": cfg["global_disclaimer"]["en"].strip(),
        "rule_engine_version": RULE_ENGINE_VERSION,
        "environment_used": env.model_dump(),
    }


def _ser_rec(r: dict) -> dict:
    return {
        "id": r.get("id"),
        "uk": r.get("uk", "").strip(),
        "en": r.get("en", "").strip(),
        "source_org": r.get("source_org"),
        "source_date": r.get("source_date"),
        "review_date": r.get("review_date"),
    }


def assess(req: ProfileRiskRequest) -> dict:
    env = req.environment
    if env is None:
        raise ValueError("environment context required (endpoint fills it)")
    cfg = _recommendations_cfg()
    v, e, p, s = req.vulnerability, req.exposure, req.protection, req.symptoms

    # RULE 0 — emergency override (beats all scoring).
    if s.any_flag():
        return _emergency_result(req, env)

    # 1) Base category from hazard alone.
    reasons: list[dict] = []
    if env.exceeds_tx99:
        base = 3
        reasons.append({"factor": "extreme_hazard", "weight": 100,
                        "detail": "Forecast exceeds the local TX99 extreme threshold."})
    elif env.in_primary_event and env.event_duration_days >= 3:
        base = 2
        reasons.append({"factor": "heatwave_event", "weight": 90,
                        "detail": f"Inside a {env.event_duration_days}-day heatwave "
                                  "(Tmax > local TX95)."})
    elif env.exceeds_tx90 or (env.heat_index_max is not None and env.heat_index_max >= 32):
        base = 1
        detail = ("Tmax above the local TX90 early-warning threshold."
                  if env.exceeds_tx90 else
                  f"Heat Index reaches {env.heat_index_max} degC.")
        reasons.append({"factor": "elevated_hazard", "weight": 50, "detail": detail})
    else:
        base = 0

    # 2) Escalations (stack; clamped later).
    esc = 0
    majors = _major_vulnerabilities(v)
    if base >= 2 and majors:
        esc += 1
        reasons.append({"factor": "vulnerability_overlap", "weight": 60,
                        "detail": f"Strong heat overlaps major vulnerability: {', '.join(majors)}."})
    if env.tropical_night:
        esc += 1
        reasons.append({"factor": "tropical_night", "weight": 70,
                        "detail": "Warm night (Tmin ≥ 20 °C or > local TN90) removes overnight recovery."})
    prolonged = e.outdoor_work or (e.hours_outside >= 4 and e.direct_sun)
    if prolonged:
        esc += 1
        reasons.append({"factor": "prolonged_exposure", "weight": 65,
                        "detail": "Prolonged outdoor exposure (outdoor work or long time in direct sun)."})
    no_cooling = not (p.air_conditioning or p.access_to_cooler_place)
    if no_cooling and not p.reliable_water:
        esc += 1
        reasons.append({"factor": "no_cooling_or_water", "weight": 55,
                        "detail": "No access to cooling and no reliable water."})
    vcount = _vulnerability_count(v)
    if vcount >= 3:
        esc += 1
        reasons.append({"factor": "multiple_vulnerabilities", "weight": 40,
                        "detail": f"Several vulnerability factors present ({vcount})."})

    cat = _clamp(base + esc)

    # Critical is reserved for EXTREME hazard (TX99) or emergency symptoms.
    # Vulnerability/exposure stacking in ordinary heat caps at 'high' — this keeps
    # 'critical' meaningful and avoids over-alarming.
    if not env.exceeds_tx99:
        cat = min(cat, 2)

    # 3) Protection may reduce a NON-EXTREME category by at most one level, and
    #    never below 'moderate' when a night/exposure escalation is active.
    protective = [f for f in ("air_conditioning", "access_to_cooler_place",
                              "reliable_water", "social_support", "can_change_schedule",
                              "reliable_electricity") if getattr(p, f)]
    protection_applied = False
    if base < 3 and cat > 0 and len(protective) >= 2:
        floor = 1 if (env.tropical_night or prolonged) else 0
        new_cat = max(cat - 1, floor)
        if new_cat < cat:
            cat = new_cat
            protection_applied = True

    # 4) Extreme-hazard floor (protection can't drop it below 'high').
    if env.exceeds_tx99:
        cat = max(cat, 2)

    # 5) Confidence label.
    if env.exceeds_tx99 or (env.in_primary_event and env.observed_confirmation):
        confidence = "strong environmental signal"
    elif env.in_primary_event or env.exceeds_tx95:
        confidence = "moderate environmental signal"
    else:
        confidence = "limited environmental signal"

    top = sorted(reasons, key=lambda r: r["weight"], reverse=True)[:3]

    # 6) Recommendations (source-controlled) + guardrails.
    recs: list[dict] = []
    for r in cfg["recommendations"]:
        if r["id"] == "REC-EMERGENCY-103":
            continue
        if _rec_matches(r, cat, v, e):
            recs.append(_ser_rec(r))
    guardrails = _guardrails(v)

    return {
        "category": CATEGORIES[cat],
        "category_index": cat,
        "is_emergency": False,
        "confidence": confidence,
        "top_reasons": [{"factor": r["factor"], "detail": r["detail"]} for r in top],
        "protective_factors": protective,
        "protection_applied": protection_applied,
        "recommendations": recs,
        "guardrails": guardrails,
        "emergency": None,
        "disclaimer_uk": cfg["global_disclaimer"]["uk"].strip(),
        "disclaimer_en": cfg["global_disclaimer"]["en"].strip(),
        "rule_engine_version": RULE_ENGINE_VERSION,
        "environment_used": env.model_dump(),
    }


def _rec_matches(r: dict, cat: int, v, e) -> bool:
    trig = r.get("triggers", {})
    if "min_category" in trig:
        if cat < CATEGORIES.index(trig["min_category"]):
            return False
    if "any_of" in trig:
        present = set()
        for name in ("heart_failure", "ckd", "diabetes", "cardiovascular",
                     "thermoregulation_medication"):
            if getattr(v, name, False):
                present.add(name)
        if getattr(v, "fluid_restriction", False):
            present.add("fluid_restriction")
        for name in ("outdoor_work", "intense_outdoor_sport"):
            if getattr(e, name, False):
                present.add(name)
        if not (set(trig["any_of"]) & present):
            return False
    return True


def _guardrails(v) -> list[dict]:
    """Explicit safety guardrails independent of category."""
    out = []
    if v.heart_failure or v.ckd or v.fluid_restriction:
        out.append({
            "id": "fluid_restriction",
            "en": "You reported heart failure, CKD or a fluid restriction. Do NOT use a "
                  "universal water amount — follow your clinician's fluid plan and discuss "
                  "a hot-weather plan with them.",
            "uk": "Дотримуйтесь плану вживання рідини від лікаря; не орієнтуйтесь на "
                  "універсальну кількість води.",
        })
    if v.thermoregulation_medication:
        out.append({
            "id": "medication",
            "en": "Some medicines affect hydration, blood pressure or thermoregulation. Do "
                  "NOT stop or change medication without professional advice.",
            "uk": "Не припиняйте і не змінюйте прийом ліків без поради фахівця.",
        })
    return out
