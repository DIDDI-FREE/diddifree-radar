import asyncio
import unittest

from fastapi.testclient import TestClient

from app.collector.collector import collect_finance_summary
from app.core.db import execute, init_db
from app.main import app
from tests.test_api import DG_HEADERS, OPERATIONS_HEADERS


PAYLOAD = {
    "contract_version": "pilotage.v1",
    "module": "diddisend",
    "date": "2026-10-03",
    "timezone": "Africa/Abidjan",
    "is_final": True,
    "calculated_at": "2026-10-04T00:00:00Z",
    "metrics": [
        {"name": "gross_delivery_value", "value": "11000.00", "unit": "XOF"},
        {"name": "platform_commission", "value": "1000.00", "unit": "XOF"},
        {"name": "courier_earnings", "value": "10000.00", "unit": "XOF"},
    ],
}


class FakeFinanceClient:
    async def finance_summary(self, date: str) -> dict:
        return {**PAYLOAD, "date": date}


class FinanceSummaryTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_source_state")
        self.client = TestClient(app)

    def test_collect_and_read_diddisend_finance_summary(self):
        result = asyncio.run(collect_finance_summary("diddisend", date="2026-10-03", client=FakeFinanceClient()))
        self.assertEqual(result["status"], "collected")
        response = self.client.get(
            "/api/pilotage/modules/diddisend/finance-summary?date=2026-10-03",
            headers=DG_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["metrics"][1]["name"], "platform_commission")

    def test_operations_role_cannot_read_finance_summary(self):
        asyncio.run(collect_finance_summary("diddisend", date="2026-10-03", client=FakeFinanceClient()))
        response = self.client.get("/api/pilotage/modules/diddisend/finance-summary", headers=OPERATIONS_HEADERS)
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
