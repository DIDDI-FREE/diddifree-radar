import asyncio
import unittest

from fastapi.testclient import TestClient

from app.collector.collector import collect_accounting_summary, collect_finance_summary
from app.collector import store
from app.core.db import execute, init_db
from app.main import app
from tests.test_api import DG_HEADERS, OPERATIONS_HEADERS


ACCOUNTING = {
    "contract_version": "pilotage.accounting-source.v1",
    "module": "diddipay",
    "date": "2026-10-05",
    "timezone": "Africa/Abidjan",
    "currency": "XOF",
    "is_final": True,
    "entries": [{
        "service": "diddigo",
        "processor": "cinetpay",
        "flow_type": "service_payment",
        "status": "succeeded",
        "transactions_count": 8,
        "gross_amount_xof": 24000,
        "refund_amount_xof": 1000,
        "processor_fees_xof": 480,
        "net_expected_xof": 22520,
        "settled_amount_xof": 20000,
        "outstanding_amount_xof": 2520,
    }],
    "calculated_at": "2026-10-06T00:01:00Z",
    "sources": [{"module": "diddipay", "record_type": "payment_intent"}],
}

GO_FINANCE = {
    "contract_version": "pilotage.v1",
    "module": "diddigo",
    "date": "2026-10-05",
    "timezone": "Africa/Abidjan",
    "is_final": True,
    "metrics": [
        {"name": "completed_fare_total_xof", "value": 24000, "unit": "XOF"},
        {"name": "driver_earnings_xof", "value": 19000, "unit": "XOF"},
    ],
    "calculated_at": "2026-10-06T00:00:00Z",
}


class FakeAccountingClient:
    async def accounting_summary(self, date: str) -> dict:
        return {**ACCOUNTING, "date": date}


class FakeGoFinanceClient:
    async def finance_summary(self, date: str) -> dict:
        return {**GO_FINANCE, "date": date}


class AccountingExportTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_source_state")
        execute("DELETE FROM pilotage_financial_access_log")
        self.client = TestClient(app)

    def test_export_preserves_exact_business_metrics_and_payment_dimensions(self):
        asyncio.run(collect_finance_summary("diddigo", date="2026-10-05", client=FakeGoFinanceClient()))
        result = asyncio.run(collect_accounting_summary(date="2026-10-05", client=FakeAccountingClient()))
        self.assertEqual(result["status"], "collected")

        response = self.client.get("/api/pilotage/accounting/daily-export?date=2026-10-05", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["contract_version"], "pilotage.accounting.v1")
        self.assertEqual(body["business_summaries"][0]["metrics"][0]["name"], "completed_fare_total_xof")
        self.assertEqual(body["payment_entries"][0]["flow_type"], "service_payment")
        self.assertEqual(body["payment_entries"][0]["processor_fees_xof"], 480)
        self.assertEqual(body["reconciliation"]["status"], "partial")
        self.assertIn("diddisend_finance_summary_missing", body["reconciliation"]["blockers"])

    def test_missing_sources_are_partial_not_zero(self):
        response = self.client.get("/api/pilotage/accounting/daily-export?date=2026-10-05", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["revision"]), 16)
        self.assertEqual(response.json()["source_revisions"], {})
        self.assertEqual(response.json()["payment_entries"], [])
        self.assertEqual(response.json()["reconciliation"]["status"], "partial")

    def test_operations_role_cannot_read_accounting_export(self):
        response = self.client.get("/api/pilotage/accounting/daily-export?date=2026-10-05", headers=OPERATIONS_HEADERS)
        self.assertEqual(response.status_code, 403)

    def test_invalid_accounting_source_contract_is_not_stored(self):
        invalid = FakeAccountingClient()
        invalid.accounting_summary = lambda date: None

        class WrongClient:
            async def accounting_summary(self, date: str) -> dict:
                return {**ACCOUNTING, "module": "wrong"}

        result = asyncio.run(collect_accounting_summary(date="2026-10-05", client=WrongClient()))
        self.assertEqual(result["code"], "contract_invalid")
        self.assertIsNone(store.latest_summary("diddipay", "accounting", "2026-10-05"))


if __name__ == "__main__":
    unittest.main()
