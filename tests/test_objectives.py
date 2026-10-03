import asyncio
import unittest

from fastapi.testclient import TestClient

from app.collector.collector import collect_daily_summary
from app.core.db import execute, init_db
from app.main import app
from tests.test_api import DG_HEADERS, OPERATIONS_HEADERS
from tests.test_collector import FakeClient
from tests.test_contracts import GUIDE_EXAMPLE


class ObjectiveTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_objectives")
        self.client = TestClient(app)

    def test_objective_reports_actual_gap_progress_and_history(self):
        asyncio.run(collect_daily_summary("diddigo", client=FakeClient(result=GUIDE_EXAMPLE)))
        path = "/api/pilotage/objectives/diddigo/rides_requested"
        first = self.client.put(path, headers=DG_HEADERS, json={"period": "day", "period_start": "2026-09-23", "target_value": 2000, "unit": "count"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["objective"]["actual_value"], "1000")
        self.assertEqual(first.json()["objective"]["progress_percent"], 50.0)
        self.client.put(path, headers=DG_HEADERS, json={"period": "day", "period_start": "2026-09-23", "target_value": 2500, "unit": "count"})
        history = self.client.get(path + "/history?period=day&period_start=2026-09-23", headers=DG_HEADERS)
        self.assertEqual([item["revision"] for item in history.json()["items"]], [2, 1])

    def test_operations_cannot_write_financial_objective(self):
        response = self.client.put(
            "/api/pilotage/objectives/diddigo/completed_fare_total_xof",
            headers=OPERATIONS_HEADERS,
            json={"period": "month", "period_start": "2026-10-01", "target_value": 1000000, "unit": "XOF"},
        )
        self.assertEqual(response.status_code, 403)

    def test_monthly_objective_requires_first_day(self):
        response = self.client.put(
            "/api/pilotage/objectives/diddigo/rides_requested",
            headers=DG_HEADERS,
            json={"period": "month", "period_start": "2026-10-02", "target_value": 100, "unit": "count"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["error"]["code"], "invalid_period_start")


if __name__ == "__main__":
    unittest.main()
