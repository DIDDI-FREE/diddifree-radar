import asyncio
import csv
import io
import unittest

from fastapi.testclient import TestClient

from app.collector.collector import collect_daily_summary
from app.core.db import execute, init_db
from app.main import app
from tests.test_api import DG_HEADERS, OPERATIONS_HEADERS
from tests.test_collector import FakeClient
from tests.test_contracts import GUIDE_EXAMPLE


class ReportTests(unittest.TestCase):
    def setUp(self):
        init_db()
        for table in ("pilotage_summaries", "pilotage_objectives", "pilotage_alert_events", "pilotage_alerts", "pilotage_source_state", "pilotage_financial_access_log"):
            execute(f"DELETE FROM {table}")
        self.client = TestClient(app)
        payload = {
            **GUIDE_EXAMPLE,
            "metrics": [
                {"name": "rides_requested", "label": "Demandées", "value": 1000, "unit": "count", "aggregation": "sum"},
                {"name": "completed_fare_total_xof", "label": "Montant", "value": 24000, "unit": "XOF", "aggregation": "sum"},
            ],
        }
        asyncio.run(collect_daily_summary("diddigo", client=FakeClient(result=payload)))

    def test_daily_json_report_masks_finance_for_operations(self):
        response = self.client.get("/api/pilotage/reports/day?anchor=2026-09-23", headers=OPERATIONS_HEADERS)
        self.assertEqual(response.status_code, 200)
        diddigo = next(block for block in response.json()["modules"] if block["module"] == "diddigo")
        self.assertEqual([metric["name"] for metric in diddigo["metrics"]], ["rides_requested"])

    def test_csv_report_contains_finance_for_dg_and_is_audited(self):
        response = self.client.get("/api/pilotage/reports/day?anchor=2026-09-23&format=csv", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        records = list(csv.DictReader(io.StringIO(response.text)))
        self.assertIn("completed_fare_total_xof", {record["metric"] for record in records})
        audit = self.client.get("/api/pilotage/audit/financial-access", headers=DG_HEADERS).json()["items"]
        self.assertEqual(audit[0]["resource"], "report-csv")

    def test_unknown_report_period_is_rejected(self):
        response = self.client.get("/api/pilotage/reports/year?anchor=2026-09-23", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
