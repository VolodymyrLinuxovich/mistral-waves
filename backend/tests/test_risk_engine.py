"""Persona tests for the deterministic personal-risk engine (spec section 17)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.risk.engine import assess  # noqa: E402
from app.risk.models import (  # noqa: E402
    EnvironmentContext,
    Exposure,
    ProfileRiskRequest,
    Protection,
    Symptoms,
    Vulnerability,
)


def req(**kw):
    return ProfileRiskRequest(**kw)


class TestPersonas(unittest.TestCase):
    def test_persona_A_healthy_indoor_cooled_moderate(self):
        r = assess(req(
            vulnerability=Vulnerability(age_band="18_64"),
            exposure=Exposure(outdoor_work=False, hours_outside=1),
            protection=Protection(air_conditioning=True, reliable_water=True),
            environment=EnvironmentContext(exceeds_tx90=True),  # moderate heat
        ))
        self.assertIn(r["category"], ("low", "moderate"))
        self.assertFalse(r["is_emergency"])
        self.assertNotIn("%", str(r))  # never a percentage

    def test_persona_B_older_cvd_tropical_night_no_cooling(self):
        r = assess(req(
            vulnerability=Vulnerability(age_band="75_plus", cardiovascular=True),
            exposure=Exposure(),
            protection=Protection(),  # no cooling
            environment=EnvironmentContext(
                exceeds_tx90=True, exceeds_tx95=True, in_primary_event=True,
                event_duration_days=3, tropical_night=True),
        ))
        self.assertEqual(r["category"], "high")
        factors = [x["factor"] for x in r["top_reasons"]]
        self.assertIn("tropical_night", factors)

    def test_persona_C_outdoor_worker_extreme(self):
        r = assess(req(
            vulnerability=Vulnerability(age_band="18_64"),
            exposure=Exposure(outdoor_work=True, direct_sun=True, hours_outside=8),
            protection=Protection(),
            environment=EnvironmentContext(
                exceeds_tx90=True, exceeds_tx95=True, exceeds_tx99=True,  # extreme
                in_primary_event=True, event_duration_days=4),
        ))
        self.assertIn(r["category"], ("high", "critical"))
        self.assertEqual(r["category"], "critical")  # extreme hazard
        ids = [rec["id"] for rec in r["recommendations"]]
        self.assertIn("REC-OUTDOOR-WORK", ids)

    def test_persona_D_ckd_fluid_restriction_no_fixed_volume(self):
        r = assess(req(
            vulnerability=Vulnerability(ckd=True, heart_failure=True, fluid_restriction=True),
            environment=EnvironmentContext(exceeds_tx95=True, in_primary_event=True,
                                           event_duration_days=3),
        ))
        guard_ids = [g["id"] for g in r["guardrails"]]
        self.assertIn("fluid_restriction", guard_ids)
        # No universal water quantity anywhere in the output.
        blob = str(r).lower()
        self.assertNotIn("litre", blob)
        self.assertNotIn("liters of water", blob)
        # Fluid recommendation says follow clinician plan.
        rec_ids = [rec["id"] for rec in r["recommendations"]]
        self.assertIn("REC-FLUID-RESTRICTED", rec_ids)

    def test_persona_E_emergency_overrides_everything(self):
        r = assess(req(
            vulnerability=Vulnerability(age_band="18_64"),
            protection=Protection(air_conditioning=True, reliable_water=True,
                                  social_support=True, reliable_electricity=True),
            symptoms=Symptoms(confusion=True),
            environment=EnvironmentContext(),  # mild environment
        ))
        self.assertEqual(r["category"], "critical")
        self.assertTrue(r["is_emergency"])
        self.assertEqual(r["emergency"]["call"], "103")

    def test_medication_never_advises_stopping(self):
        r = assess(req(
            vulnerability=Vulnerability(thermoregulation_medication=True),
            environment=EnvironmentContext(exceeds_tx90=True),
        ))
        blob = (str(r["guardrails"]) + str(r["recommendations"])).lower()
        self.assertIn("do not stop", blob)
        self.assertNotIn("stop taking", blob)

    def test_protection_cannot_downgrade_extreme(self):
        # Extreme hazard + lots of protection must stay critical (no downgrade).
        r = assess(req(
            protection=Protection(air_conditioning=True, reliable_water=True,
                                  social_support=True, can_change_schedule=True),
            environment=EnvironmentContext(exceeds_tx99=True, in_primary_event=True,
                                           event_duration_days=3),
        ))
        self.assertEqual(r["category"], "critical")
        self.assertFalse(r["protection_applied"])

    def test_no_percentage_in_any_output(self):
        r = assess(req(environment=EnvironmentContext(exceeds_tx95=True,
                                                      in_primary_event=True,
                                                      event_duration_days=3)))
        self.assertNotIn("%", str(r))


if __name__ == "__main__":
    unittest.main()
