"""Tests for the ephemeral family check-in loop."""
import os
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app  # noqa: E402
from app.services import checkin  # noqa: E402


class TestCheckin(unittest.TestCase):
    def setUp(self):
        checkin.clear_sessions()
        self.client = TestClient(app)

    def _create(self, risk_level="high", language="en") -> str:
        response = self.client.post(
            "/api/checkin/create",
            json={"risk_level": risk_level, "language": language},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"id"})
        return response.json()["id"]

    def test_create_is_pending_and_rejects_private_extra_fields(self):
        session_id = self._create()
        self.assertEqual(
            self.client.get(f"/api/checkin/{session_id}/status").json(),
            {"status": "pending"},
        )
        invalid = self.client.post(
            "/api/checkin/create",
            json={"risk_level": "high", "language": "en", "name": "Private"},
        )
        self.assertEqual(invalid.status_code, 422)

    def test_mobile_page_contains_risk_and_response_buttons(self):
        session_id = self._create(risk_level="critical")
        response = self.client.get(f"/checkin/{session_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CRITICAL", response.text)
        self.assertIn("I'm OK ✅", response.text)
        self.assertIn("Need help ⚠️", response.text)

    def test_response_flips_status_and_sessions_expire_after_one_hour(self):
        session_id = self._create()
        response = self.client.post(
            f"/api/checkin/{session_id}/respond", json={"status": "help"}
        )
        self.assertEqual(response.json(), {"status": "help"})
        self.assertEqual(
            self.client.get(f"/api/checkin/{session_id}/status").json(),
            {"status": "help"},
        )
        with checkin._lock:
            checkin._sessions[session_id]["created_at"] -= checkin.CHECKIN_TTL_SECONDS
        self.assertEqual(
            self.client.get(f"/api/checkin/{session_id}/status").status_code, 404
        )
