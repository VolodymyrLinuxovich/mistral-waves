"""Ephemeral, privacy-minimal family check-in sessions for the demo."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

RiskLevel = Literal["low", "moderate", "high", "critical"]
Language = Literal["en", "uk"]
CheckinStatus = Literal["pending", "ok", "help"]

CHECKIN_TTL_SECONDS = 60 * 60


class CheckinCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: RiskLevel
    language: Language


class CheckinRespondRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "help"]


# No names, contact details, symptoms, plan text, or raw health data are stored.
# Status and timestamps are operational metadata required for polling and expiry.
_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def _purge_expired(now: float) -> None:
    expired = [
        session_id
        for session_id, session in _sessions.items()
        if now - session["created_at"] >= CHECKIN_TTL_SECONDS
    ]
    for session_id in expired:
        del _sessions[session_id]


def create_session(request: CheckinCreateRequest) -> str:
    now = time.time()
    session_id = uuid.uuid4().hex
    with _lock:
        _purge_expired(now)
        _sessions[session_id] = {
            "risk_level": request.risk_level,
            "language": request.language,
            "status": "pending",
            "created_at": now,
            "updated_at": None,
        }
    return session_id


def get_session(session_id: str) -> dict | None:
    now = time.time()
    with _lock:
        _purge_expired(now)
        session = _sessions.get(session_id)
        return dict(session) if session else None


def respond(session_id: str, status: Literal["ok", "help"]) -> dict | None:
    now = time.time()
    with _lock:
        _purge_expired(now)
        session = _sessions.get(session_id)
        if session is None:
            return None
        session["status"] = status
        session["updated_at"] = now
        return dict(session)


def clear_sessions() -> None:
    """Reset process-local state for isolated tests."""
    with _lock:
        _sessions.clear()
