import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_ready_when_database_answers(self):
        self.assertEqual(self.client.get("/ready").status_code, 200)

    def test_not_ready_when_database_is_unavailable(self):
        with patch("app.main.is_ready", return_value=False):
            response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"]["error"]["code"], "database_unavailable")


if __name__ == "__main__":
    unittest.main()
