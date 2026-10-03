import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class FrontendDecouplingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_api_only_mode_disables_root_frontend(self):
        with patch.dict(os.environ, {"PILOTAGE_SERVE_FRONTEND": "0"}):
            self.assertEqual(self.client.get("/").status_code, 404)
            self.assertEqual(self.client.get("/health").status_code, 200)
            self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_local_mode_can_serve_frontend(self):
        with patch.dict(os.environ, {"PILOTAGE_SERVE_FRONTEND": "1"}):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("DiddiFree Pilotage", response.text)


if __name__ == "__main__":
    unittest.main()
