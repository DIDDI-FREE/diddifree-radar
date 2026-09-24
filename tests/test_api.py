import asyncio
import unittest

from fastapi.testclient import TestClient

from app.collector.collector import collect_daily_summary
from app.core.db import execute, init_db
from app.main import app
from tests.test_collector import FakeClient
from tests.test_contracts import GUIDE_EXAMPLE

DG_HEADERS = {"X-User-Id": "dg-1", "X-Role": "dg_global"}
MODULE_MANAGER_HEADERS = {"X-User-Id": "mm-1", "X-Role": "module_manager", "X-Modules": "diddigo"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_source_state")
        self.client = TestClient(app)

    def _collect_diddigo(self):
        asyncio.run(collect_daily_summary("diddigo", client=FakeClient(result=GUIDE_EXAMPLE)))

    def test_health_needs_no_auth(self):
        self.assertEqual(self.client.get("/api/pilotage/health").status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_overview_requires_auth(self):
        response = self.client.get("/api/pilotage/overview")
        self.assertEqual(response.status_code, 401)

    def test_overview_returns_module_blocks_with_freshness(self):
        self._collect_diddigo()
        response = self.client.get("/api/pilotage/overview", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["contract_version"], "pilotage.v1")
        blocks = {block["module"]: block for block in body["modules"]}
        self.assertEqual(blocks["diddigo"]["freshness"]["status"], "fresh")
        self.assertEqual(blocks["diddigo"]["summary"]["metrics"][0]["value"], 1000)
        self.assertEqual(blocks["diddisend"]["freshness"]["status"], "unavailable")
        self.assertIsNone(blocks["diddisend"]["summary"])

    def test_module_manager_sees_only_their_module(self):
        response = self.client.get("/api/pilotage/overview", headers=MODULE_MANAGER_HEADERS)
        modules = [block["module"] for block in response.json()["modules"]]
        self.assertEqual(modules, ["diddigo"])
        denied = self.client.get("/api/pilotage/modules/diddipay/daily-summary", headers=MODULE_MANAGER_HEADERS)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["detail"]["error"]["code"], "permission_denied")

    def test_module_summary_by_date(self):
        self._collect_diddigo()
        response = self.client.get("/api/pilotage/modules/diddigo/daily-summary?date=2026-09-23", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["date"], "2026-09-23")
        missing = self.client.get("/api/pilotage/modules/diddigo/daily-summary?date=2020-01-01", headers=DG_HEADERS)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"]["error"]["code"], "summary_unavailable")

    def test_unknown_module_is_404(self):
        response = self.client.get("/api/pilotage/modules/notamodule/daily-summary", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["error"]["code"], "unknown_module")

    def test_sources_lists_collection_state(self):
        self._collect_diddigo()
        response = self.client.get("/api/pilotage/sources", headers=DG_HEADERS)
        items = {item["module"]: item for item in response.json()["items"]}
        self.assertEqual(items["diddigo"]["freshness"]["status"], "fresh")
        self.assertEqual(items["diddipay"]["consecutive_failures"], 0)

    def test_collect_trigger_requires_role(self):
        audit_headers = {"X-User-Id": "aud-1", "X-Role": "audit_read"}
        response = self.client.post("/api/pilotage/sources/diddigo/collect", headers=audit_headers)
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
