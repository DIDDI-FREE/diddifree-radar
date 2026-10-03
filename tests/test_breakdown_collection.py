import asyncio
import unittest

from fastapi.testclient import TestClient

from app.collector.collector import collect_breakdown
from app.core.db import execute, init_db
from app.main import app
from tests.test_api import DG_HEADERS, MODULE_MANAGER_HEADERS
from tests.test_breakdown_contract import VALID


class FakeBreakdownClient:
    async def breakdown(self, date, dimension, metric):
        return {**VALID, "date": date, "dimension": dimension, "metric": metric}


class BreakdownCollectionTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        self.client = TestClient(app)

    def test_collect_and_read_breakdown(self):
        result = asyncio.run(collect_breakdown("diddigo", date="2026-10-03", dimension="payment_method", metric="rides_completed", client=FakeBreakdownClient()))
        self.assertEqual(result["status"], "collected")
        response = self.client.get("/api/pilotage/modules/diddigo/breakdown?date=2026-10-03&dimension=payment_method&metric=rides_completed", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["breakdown"]["total"], 10)

    def test_breakdown_respects_module_scope(self):
        response = self.client.get("/api/pilotage/modules/diddisend/breakdown?date=2026-10-03&dimension=payment_method&metric=rides_completed", headers=MODULE_MANAGER_HEADERS)
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
