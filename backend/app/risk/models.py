"""Pydantic models for the personal-risk profile and environmental context.

We collect the minimum needed: no names, no medical-record numbers, no detailed
diagnoses. Most fields are booleans/enums with a 'prefer not to answer' option
represented simply by omission (None).
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

AgeBand = Literal["under_5", "5_17", "18_64", "65_74", "75_plus"]
YesNoUnsure = Literal["yes", "no", "unsure", "prefer_not"]


class Vulnerability(BaseModel):
    age_band: Optional[AgeBand] = None
    pregnancy: bool = False
    cardiovascular: bool = False
    heart_failure: bool = False
    hypertension: bool = False
    ckd: bool = False                    # chronic kidney disease
    diabetes: bool = False
    chronic_respiratory: bool = False
    obesity: bool = False
    thermoregulation_medication: bool = False  # meds affecting hydration/BP/thermoreg
    fluid_restriction: bool = False      # clinician-prescribed fluid limit
    limited_mobility: bool = False
    living_alone: bool = False


class Exposure(BaseModel):
    outdoor_work: bool = False
    intense_outdoor_sport: bool = False
    direct_sun: bool = False
    hot_transport: bool = False
    top_floor_or_overheated_home: bool = False
    nighttime_exposure: bool = False
    hours_outside: float = Field(0, ge=0, le=24)


class Protection(BaseModel):
    air_conditioning: bool = False
    access_to_cooler_place: bool = False
    reliable_water: bool = False
    social_support: bool = False
    can_change_schedule: bool = False
    reliable_electricity: bool = False


class Symptoms(BaseModel):
    """Emergency red flags. Any True forces a critical emergency screen."""
    confusion: bool = False
    loss_of_consciousness: bool = False   # fainting
    seizure: bool = False
    cannot_drink: bool = False
    severe_weakness: bool = False
    hot_skin_altered_mental_state: bool = False
    rapid_deterioration: bool = False
    severe_shortness_of_breath: bool = False
    chest_pain: bool = False
    stroke_like_symptoms: bool = False

    def any_flag(self) -> bool:
        return any(getattr(self, f) for f in self.model_fields)

    def triggered(self) -> list[str]:
        return [f for f in self.model_fields if getattr(self, f)]


class EnvironmentContext(BaseModel):
    """Environmental HAZARD inputs. Either supplied directly (demo/tests) or
    derived server-side from the forecast+thresholds for a location/date."""
    exceeds_tx90: bool = False
    exceeds_tx95: bool = False
    exceeds_tx99: bool = False           # extreme
    in_primary_event: bool = False       # inside a >=3-day TX95 run
    event_duration_days: int = 0
    tropical_night: bool = False
    heat_index_max: Optional[float] = None
    baseline_status: str = "provisional"
    observed_confirmation: bool = False  # observed (not forecast-only) signal
    source: str = "unspecified"


class ProfileRiskRequest(BaseModel):
    vulnerability: Vulnerability = Vulnerability()
    exposure: Exposure = Exposure()
    protection: Protection = Protection()
    symptoms: Symptoms = Symptoms()
    # Option 1: derive environment from a location/date.
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    date: Optional[str] = None           # YYYY-MM-DD
    # Option 2: supply environment directly (demo / offline / tests).
    environment: Optional[EnvironmentContext] = None
