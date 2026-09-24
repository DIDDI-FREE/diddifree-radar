import base64
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.db import execute, init_db
from app.main import app


def fake_jwt(claims: dict) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.sig"


class AuthRouteTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_users")
        self.client = TestClient(app)

    def test_config_is_public(self):
        response = self.client.get("/api/pilotage/auth/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "diddifreeid_otp")

    def test_dashboard_page_is_served(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("DiddiFree Pilotage", response.text)

    def test_otp_request_requires_email_for_email_channel(self):
        response = self.client.post("/api/pilotage/auth/otp/request", json={"channel": "email"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["error"]["code"], "email_required")

    def test_otp_verify_requires_code(self):
        response = self.client.post("/api/pilotage/auth/otp/verify", json={"email": "dg@diddifree.com"})
        self.assertEqual(response.status_code, 400)

    def test_otp_verify_provisions_bootstrap_email(self):
        token = fake_jwt({"sub": "user-dg-1", "status": "active", "role": "user"})
        with patch.dict(os.environ, {"PILOTAGE_BOOTSTRAP_DG_EMAILS": "dg@diddifree.com"}), patch(
            "app.api.auth_routes._post_identity", new=AsyncMock(return_value={"access_token": token, "expires_in": 900})
        ):
            response = self.client.post(
                "/api/pilotage/auth/otp/verify", json={"email": "DG@diddifree.com", "code": "123456"}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["access_token"], token)
        self.assertEqual(body["session"]["role"], "dg_global")
        self.assertEqual(body["session"]["modules"], ["global"])

    def test_otp_verify_rejects_unprovisioned_user(self):
        token = fake_jwt({"sub": "user-unknown", "status": "active"})
        with patch("app.api.auth_routes._post_identity", new=AsyncMock(return_value={"access_token": token})):
            response = self.client.post(
                "/api/pilotage/auth/otp/verify", json={"email": "someone@diddifree.com", "code": "123456"}
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"]["code"], "not_provisioned")

    def test_otp_verify_rejects_inactive_identity(self):
        token = fake_jwt({"sub": "user-x", "status": "suspended"})
        with patch("app.api.auth_routes._post_identity", new=AsyncMock(return_value={"access_token": token})):
            response = self.client.post(
                "/api/pilotage/auth/otp/verify", json={"email": "x@diddifree.com", "code": "123456"}
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"]["error"]["code"], "identity_inactive")


if __name__ == "__main__":
    unittest.main()
