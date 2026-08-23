from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import date
from pathlib import Path

import httpx
import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "waves_mcp.py"
SPEC = importlib.util.spec_from_file_location("waves_mcp_server", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
waves_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(waves_mcp)


def _install_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        waves_mcp,
        "_make_client",
        lambda: httpx.AsyncClient(
            base_url=waves_mcp.WAVES_API_BASE_URL,
            transport=transport,
        ),
    )


def test_get_heat_risk_for_coordinates_sends_only_safe_profile_fields(monkeypatch):
    expected = {"risk_category": "high", "confidence": "high", "emergency": {"active": False}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/profile-risk"
        body = json.loads(request.content)
        assert body["latitude"] == 50.45
        assert body["longitude"] == 30.52
        assert body["date"] == "2026-08-22"
        assert body["vulnerability"] == {"age_band": "75_plus", "living_alone": True}
        assert body["exposure"] == {"hours_outside": 3.0}
        assert body["protection"] == {"social_support": True}
        assert "symptoms" not in body
        assert "environment" not in body
        assert "name" not in body
        return httpx.Response(200, json=expected)

    _install_transport(monkeypatch, handler)
    result = asyncio.run(
        waves_mcp.get_heat_risk(
            on=date(2026, 8, 22),
            latitude=50.45,
            longitude=30.52,
            vulnerability=waves_mcp.Vulnerability(age_band="75_plus", living_alone=True),
            exposure=waves_mcp.Exposure(hours_outside=3),
            protection=waves_mcp.Protection(social_support=True),
        )
    )
    assert result == expected


def test_get_heat_risk_resolves_supported_city(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert (body["latitude"], body["longitude"]) == (50.4501, 30.5234)
        return httpx.Response(200, json={"risk_category": "moderate"})

    _install_transport(monkeypatch, handler)
    result = asyncio.run(waves_mcp.get_heat_risk(on=date(2026, 8, 22), city="Kyiv"))
    assert result["risk_category"] == "moderate"


def test_get_action_plan_uses_exact_safe_subset_and_preserves_risk(monkeypatch):
    returned_risk = "high"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/mistral-action-plan"
        body = json.loads(request.content)
        assert set(body) == {
            "risk_category",
            "confidence",
            "top_reasons",
            "protective_factors",
            "recommendations",
            "guardrails",
            "context_label",
            "date",
            "preferred_language",
        }
        assert body["risk_category"] == "high"
        assert body["preferred_language"] == "uk"
        return httpx.Response(
            200,
            json={
                "risk_category": returned_risk,
                "generated_by": "Mistral Medium 3.5",
                "plan": {
                    "headline": "План на 12 годин",
                    "immediate_actions": ["Перейдіть у прохолодніше місце."],
                    "next_six_hours": ["Перевірте прогноз."],
                    "tonight": ["Підготуйте прохолодне місце для сну."],
                    "avoid": ["Уникайте прямого сонця."],
                    "check_in_message": "Напишіть мені через дві години.",
                    "safety_note": "Дотримуйтеся наявних обмежень.",
                },
            },
        )

    _install_transport(monkeypatch, handler)
    result = asyncio.run(
        waves_mcp.get_action_plan(
            risk_category="high",
            confidence="high",
            top_reasons=[waves_mcp.RiskReason(factor="heat", detail="Severe heat")],
            protective_factors=["Social support"],
            recommendations=[
                waves_mcp.Recommendation(
                    id="cool-place",
                    en="Move to a cooler place.",
                    uk="Перейдіть у прохолодніше місце.",
                )
            ],
            guardrails=[
                waves_mcp.Guardrail(
                    id="fluid-restriction",
                    en="Follow your prescribed fluid restriction.",
                    uk="Дотримуйтеся призначеного обмеження рідини.",
                )
            ],
            context_label="Severe heatwave",
            on=date(2026, 8, 22),
            language="uk",
        )
    )
    assert result["risk_category"] == "high"
    assert result["plan"]["headline"] == "План на 12 годин"

    returned_risk = "critical"
    with pytest.raises(RuntimeError, match="changed the Waves risk category"):
        asyncio.run(
            waves_mcp.get_action_plan(
                risk_category="high",
                confidence="high",
                top_reasons=[],
                protective_factors=[],
                recommendations=[],
                guardrails=[],
                context_label="Severe heatwave",
                on=date(2026, 8, 22),
                language="uk",
            )
        )


def test_api_timeout_is_reported_without_leaking_payload(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow upstream", request=request)

    _install_transport(monkeypatch, handler)
    with pytest.raises(RuntimeError, match="Waves API timed out") as exc_info:
        asyncio.run(waves_mcp.get_heat_risk(on=date(2026, 8, 22), city="Kyiv"))
    assert "Kyiv" not in str(exc_info.value)
