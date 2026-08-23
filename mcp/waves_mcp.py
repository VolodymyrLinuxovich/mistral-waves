"""MCP tools for the deployed Waves heat-risk API.

This server deliberately contains no risk or recommendation logic. It validates
inputs with the backend's existing Pydantic models and forwards only the
privacy-safe fields accepted by the deployed API.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from mcp.server import MCPServer

# Allow this standalone script to reuse the backend's canonical models without
# making ``backend`` an installed package.
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.risk.models import Exposure, ProfileRiskRequest, Protection, Vulnerability  # noqa: E402
from app.services.cities import CITIES  # noqa: E402
from app.services.mistral_action_plan import (  # noqa: E402
    ActionPlanRequest,
    ActionPlanResponse,
    Guardrail,
    Recommendation,
    RiskReason,
)

WAVES_API_BASE_URL = "https://waves-nine-gold.vercel.app"
REQUEST_TIMEOUT_SECONDS = 30.0

mcp = MCPServer(
    name="waves",
    instructions=(
        "Use Waves to calculate deterministic heat risk and turn an existing "
        "Waves result into a 12-hour action plan. Never provide names, symptoms, "
        "or an unfiltered raw health profile to these tools."
    ),
)


def _make_client() -> httpx.AsyncClient:
    """Construct the API client (kept separate so tests can inject MockTransport)."""
    return httpx.AsyncClient(
        base_url=WAVES_API_BASE_URL,
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
        headers={"User-Agent": "waves-mcp/1.0"},
    )


async def _post(path: str, payload: dict[str, Any]) -> Any:
    try:
        async with _make_client() as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException as exc:
        raise RuntimeError("The Waves API timed out; try again shortly.") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"The Waves API returned HTTP {exc.response.status_code}."
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        raise RuntimeError("The Waves API could not be reached or returned invalid JSON.") from exc


def _coordinates_for_city(city: str) -> tuple[float, float]:
    normalized = city.strip().casefold()
    match = next(
        (
            item
            for item in CITIES
            if normalized
            in {item.id.casefold(), item.name_en.casefold(), item.name_uk.casefold()}
        ),
        None,
    )
    if match is None:
        supported = ", ".join(item.name_en for item in CITIES)
        raise ValueError(f"Unknown city. Supported cities: {supported}")
    return match.lat, match.lon


@mcp.tool()
async def get_heat_risk(
    on: date,
    city: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    vulnerability: Vulnerability | None = None,
    exposure: Exposure | None = None,
    protection: Protection | None = None,
) -> dict[str, Any]:
    """Calculate Waves heat risk for a supported city or coordinate pair.

    Supply either ``city`` or both ``latitude`` and ``longitude``. Profile input
    is intentionally limited to vulnerability, exposure, and protection; this
    tool does not accept names, symptoms, or a raw health profile.
    """
    has_city = city is not None and bool(city.strip())
    has_any_coordinate = latitude is not None or longitude is not None
    has_both_coordinates = latitude is not None and longitude is not None

    if has_city and has_any_coordinate:
        raise ValueError("Provide either city or coordinates, not both.")
    if not has_city and not has_both_coordinates:
        raise ValueError("Provide a city or both latitude and longitude.")

    if has_city:
        latitude, longitude = _coordinates_for_city(city or "")

    request = ProfileRiskRequest(
        vulnerability=vulnerability or Vulnerability(),
        exposure=exposure or Exposure(),
        protection=protection or Protection(),
        latitude=latitude,
        longitude=longitude,
        date=on.isoformat(),
    )
    # Symptoms and direct environment injection are intentionally never sent.
    payload = request.model_dump(
        mode="json",
        exclude={"symptoms", "environment"},
        exclude_defaults=True,
        exclude_none=True,
    )
    result = await _post("/api/profile-risk", payload)
    if not isinstance(result, dict):
        raise RuntimeError("The Waves API returned an unexpected risk result.")
    return result


@mcp.tool()
async def get_action_plan(
    risk_category: Literal["low", "moderate", "high", "critical"],
    confidence: str,
    top_reasons: list[RiskReason],
    protective_factors: list[str],
    recommendations: list[Recommendation],
    guardrails: list[Guardrail],
    context_label: str,
    on: date,
    language: Literal["en", "uk"] = "en",
) -> dict[str, Any]:
    """Build a Mistral 12-hour plan from a privacy-safe Waves result subset."""
    request = ActionPlanRequest(
        risk_category=risk_category,
        confidence=confidence,
        top_reasons=top_reasons,
        protective_factors=protective_factors,
        recommendations=recommendations,
        guardrails=guardrails,
        context_label=context_label,
        date=on,
        preferred_language=language,
    )
    raw_response = await _post(
        "/api/mistral-action-plan", request.model_dump(mode="json")
    )
    # Validate against the exact backend response schema before returning it.
    response = ActionPlanResponse.model_validate(raw_response)
    if response.risk_category != request.risk_category:
        raise RuntimeError("The action plan response changed the Waves risk category.")
    return response.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run()
