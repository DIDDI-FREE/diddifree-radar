import asyncio
import unittest

from fastapi.testclient import TestClient

from app.collector.collector import collect_daily_summary
from app.collector import store
from app.core.db import execute, init_db
from app.main import app
from tests.test_collector import FakeClient
from tests.test_contracts import GUIDE_EXAMPLE

DG_HEADERS = {"X-User-Id": "dg-1", "X-Role": "dg_global"}
MODULE_MANAGER_HEADERS = {"X-User-Id": "mm-1", "X-Role": "module_manager", "X-Modules": "diddigo"}
OPERATIONS_HEADERS = {"X-User-Id": "ops-1", "X-Role": "operations_manager", "X-Modules": "global"}


class ApiTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_source_state")
        execute("DELETE FROM pilotage_financial_access_log")
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

    def test_overview_includes_finance_and_breakdown_highlights_for_dg(self):
        self._collect_diddigo()
        store.save_summary("diddigo", "finance", "2026-09-23", {**GUIDE_EXAMPLE, "metrics": [{"name": "platform_commission", "value": 1200, "unit": "XOF"}]}, "2026-09-23T12:00:00Z", True)
        store.save_summary("diddigo", "breakdown:payment_method:rides_completed", "2026-09-23", {"module": "diddigo", "date": "2026-09-23", "dimension": "payment_method", "metric": "rides_completed", "unit": "count", "total": 8, "items": [{"key": "cash", "label": "Espèces", "value": 8}]}, "2026-09-23T12:00:00Z", True)
        block = next(item for item in self.client.get("/api/pilotage/overview", headers=DG_HEADERS).json()["modules"] if item["module"] == "diddigo")
        self.assertEqual(block["finance_summary"]["metrics"][0]["name"], "platform_commission")
        self.assertEqual(block["breakdown_highlights"][0]["dimension"], "payment_method")
        self.assertTrue(block["coverage"]["daily_available"])
        self.assertTrue(block["coverage"]["finance_available"])
        self.assertEqual(block["coverage"]["breakdowns_available"], 1)
        self.assertGreater(block["coverage"]["breakdowns_expected"], 1)
        self.assertFalse(block["coverage"]["complete"])

    def test_overview_hides_finance_from_operations(self):
        self._collect_diddigo()
        block = next(item for item in self.client.get("/api/pilotage/overview", headers=OPERATIONS_HEADERS).json()["modules"] if item["module"] == "diddigo")
        self.assertIsNone(block["finance_summary"])

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

    def test_sources_respects_assigned_modules(self):
        response = self.client.get("/api/pilotage/sources", headers=MODULE_MANAGER_HEADERS)
        self.assertEqual([item["module"] for item in response.json()["items"]], ["diddigo"])

    def test_financial_amounts_are_masked_outside_finance_roles(self):
        payload = {
            **GUIDE_EXAMPLE,
            "metrics": [
                {"name": "rides_completed", "value": 8, "unit": "count"},
                {"name": "completed_fare_total_xof", "value": 24000, "unit": "XOF"},
            ],
        }
        asyncio.run(collect_daily_summary("diddigo", client=FakeClient(result=payload)))
        operations = self.client.get("/api/pilotage/modules/diddigo/daily-summary", headers=OPERATIONS_HEADERS).json()
        self.assertEqual([metric["name"] for metric in operations["summary"]["metrics"]], ["rides_completed"])
        finance = self.client.get("/api/pilotage/modules/diddigo/daily-summary", headers=DG_HEADERS).json()
        self.assertIn("completed_fare_total_xof", [metric["name"] for metric in finance["summary"]["metrics"]])

    def test_collect_trigger_requires_role(self):
        audit_headers = {"X-User-Id": "aud-1", "X-Role": "audit_read"}
        response = self.client.post("/api/pilotage/sources/diddigo/collect", headers=audit_headers)
        self.assertEqual(response.status_code, 403)

    def test_financial_consultations_are_audited(self):
        self.client.get("/api/pilotage/overview", headers=DG_HEADERS)
        response = self.client.get("/api/pilotage/audit/financial-access", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["resource"], "overview")
        denied = self.client.get("/api/pilotage/audit/financial-access", headers=OPERATIONS_HEADERS)
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
