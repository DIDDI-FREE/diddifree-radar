import asyncio
import unittest
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.collector.collector import collect_daily_summary
from app.collector.collector import business_today
from app.collector import store
from app.core.db import execute, init_db
from app.main import app
from tests.test_api import DG_HEADERS, MODULE_MANAGER_HEADERS, OPERATIONS_HEADERS
from tests.test_collector import FakeClient
from tests.test_contracts import GUIDE_EXAMPLE


class AlertTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_alert_events")
        execute("DELETE FROM pilotage_alerts")
        execute("DELETE FROM pilotage_source_state")
        execute("DELETE FROM pilotage_summaries")
        self.client = TestClient(app)

    def test_source_alerts_are_deduplicated(self):
        first = self.client.get("/api/pilotage/alerts", headers=DG_HEADERS).json()["items"]
        second = self.client.get("/api/pilotage/alerts", headers=DG_HEADERS).json()["items"]
        self.assertEqual(len(first), len(second))
        self.assertEqual({item["id"] for item in first}, {item["id"] for item in second})

    def test_alert_can_be_assigned_acknowledged_and_audited(self):
        alert = self.client.get("/api/pilotage/alerts?module=diddigo", headers=DG_HEADERS).json()["items"][0]
        response = self.client.patch(
            f"/api/pilotage/alerts/{alert['id']}",
            headers=OPERATIONS_HEADERS,
            json={"status": "acknowledged", "owner_id": "ops-1", "due_at": "2026-10-04T12:00:00Z"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["alert"]["owner_id"], "ops-1")
        history = self.client.get(f"/api/pilotage/alerts/{alert['id']}/history", headers=DG_HEADERS).json()["items"]
        self.assertEqual([event["action"] for event in history], ["opened", "updated"])

    def test_healthy_source_alert_is_resolved_automatically(self):
        alert = self.client.get("/api/pilotage/alerts?module=diddigo", headers=DG_HEADERS).json()["items"][0]
        asyncio.run(collect_daily_summary("diddigo", client=FakeClient(result=GUIDE_EXAMPLE)))
        resolved = self.client.get("/api/pilotage/alerts?status=resolved&module=diddigo", headers=DG_HEADERS).json()["items"]
        self.assertEqual([item["id"] for item in resolved], [alert["id"]])

    def test_module_manager_sees_only_assigned_module_alerts(self):
        items = self.client.get("/api/pilotage/alerts", headers=MODULE_MANAGER_HEADERS).json()["items"]
        self.assertTrue(items)
        self.assertEqual({item["module"] for item in items}, {"diddigo"})

    def test_activity_drop_rule_uses_previous_available_days(self):
        today = date.fromisoformat(business_today())
        for offset in range(7, 0, -1):
            day = (today - timedelta(days=offset)).isoformat()
            store.save_summary("diddigo", "daily", day, {"metrics": [{"name": "rides_requested", "value": 100, "unit": "count"}]}, day + "T23:59:00Z", True)
        day = today.isoformat()
        store.save_summary("diddigo", "daily", day, {"metrics": [{"name": "rides_requested", "value": 50, "unit": "count"}]}, day + "T12:00:00Z", False)
        items = self.client.get("/api/pilotage/alerts?module=diddigo", headers=DG_HEADERS).json()["items"]
        self.assertIn("activity_drop", {item["alert_type"] for item in items})

    def test_cancellation_rule_reads_final_status_breakdown(self):
        day = business_today()
        store.save_summary(
            "diddigo", "breakdown:final_status:rides_requested", day,
            {"total": 100, "items": [{"key": "cancelled", "label": "Annulées", "value": 25}, {"key": "completed", "label": "Terminées", "value": 75}]},
            day + "T12:00:00Z", False,
        )
        items = self.client.get("/api/pilotage/alerts?module=diddigo", headers=DG_HEADERS).json()["items"]
        self.assertIn("cancellation_rate", {item["alert_type"] for item in items})


if __name__ == "__main__":
    unittest.main()
