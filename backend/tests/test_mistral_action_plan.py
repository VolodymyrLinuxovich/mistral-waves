"""Tests for the Mistral action-plan endpoint."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app  # noqa: E402
from app.services.mistral_action_plan import ActionPlan  # noqa: E402


def request_payload(category="high"):
    return {
        "risk_category": category,
        "confidence": "moderate environmental signal",
        "top_reasons": [{"factor": "heatwave_event", "detail": "Inside a 4-day heatwave."}],
        "protective_factors": ["social_support"],
        "recommendations": [{
            "id": "REC-GENERAL",
            "en": "Move activity to a cooler time.",
            "uk": "Перенесіть активність на прохолодніший час.",
            "source_org": "WHO",
            "source_date": "2024",
            "review_date": None,
        }],
        "guardrails": [],
        "context_label": "Kyiv — synthetic severe heatwave",
        "date": "2026-08-22",
        "preferred_language": "en",
    }


def valid_plan():
    return ActionPlan(
        headline="Stay cool through tonight",
        immediate_actions=["Move activity to a cooler time."],
        next_six_hours=["Ask your support person to check in."],
        tonight=["Use the coolest available room."],
        avoid=["Avoid the hottest part of the day."],
        check_in_message="Please check in with me this evening.",
        safety_note="Follow the existing Waves safety notes.",
    )


class TestMistralActionPlan(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch("app.services.mistral_action_plan.Mistral")
    def test_valid_structured_plan(self, mistral_cls):
        mistral = MagicMock()
        mistral.chat.parse.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=valid_plan()))]
        )
        mistral_cls.return_value = mistral
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}):
            response = self.client.post("/api/mistral-action-plan", json=request_payload())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["risk_category"], "high")
        self.assertEqual(body["generated_by"], "Mistral Medium 3.5")
        self.assertEqual(body["plan"]["headline"], "Stay cool through tonight")
        call = mistral.chat.parse.call_args.kwargs
        self.assertEqual(call["model"], "mistral-medium-latest")
        self.assertIs(call["response_format"], ActionPlan)
        self.assertNotIn("vulnerability", call["messages"][1]["content"])
        self.assertNotIn("symptoms", call["messages"][1]["content"])

    def test_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.post("/api/mistral-action-plan", json=request_payload())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "mistral_unavailable")
        self.assertEqual(response.json()["risk_category"], "high")

    @patch("app.services.mistral_action_plan.Mistral")
    def test_mistral_timeout(self, mistral_cls):
        mistral = MagicMock()
        mistral.chat.parse.side_effect = httpx.ReadTimeout("timed out")
        mistral_cls.return_value = mistral
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}):
            response = self.client.post("/api/mistral-action-plan", json=request_payload())
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json()["error"], "mistral_timeout")
        self.assertEqual(response.json()["risk_category"], "high")

    @patch("app.services.mistral_action_plan.Mistral")
    def test_plan_cannot_modify_waves_risk_category(self, mistral_cls):
        mistral = MagicMock()
        mistral.chat.parse.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(parsed=valid_plan()))]
        )
        mistral_cls.return_value = mistral
        with patch.dict(os.environ, {"MISTRAL_API_KEY": "test-key"}):
            response = self.client.post(
                "/api/mistral-action-plan", json=request_payload(category="critical")
            )
        body = response.json()
        self.assertEqual(body["risk_category"], "critical")
        self.assertNotIn("risk_category", body["plan"])


if __name__ == "__main__":
    unittest.main()
