import asyncio
import unittest
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.collector import store
from app.collector.collector import DAILY_KIND, backfill_module, business_today
from app.core.db import execute, init_db
from app.main import app
from app.sources.gateway import SourceRejected
from tests.test_api import DG_HEADERS
from tests.test_contracts import GUIDE_EXAMPLE


class BackfillClient:
    """Returns a valid summary for every requested date."""

    def __init__(self, fail_dates: set[str] | None = None):
        self.requested_dates = []
        self.fail_dates = fail_dates or set()

    async def daily_summary(self, requested_date):
        self.requested_dates.append(requested_date)
        if requested_date in self.fail_dates:
            raise SourceRejected("diddigo", "route_missing", "not yet", status_code=404)
        return {**GUIDE_EXAMPLE, "date": requested_date, "is_final": True}


class AlwaysFailingClient:
    def __init__(self):
        self.requested_dates = []

    async def daily_summary(self, requested_date):
        self.requested_dates.append(requested_date)
        raise SourceRejected("diddigo", "route_missing", "not yet", status_code=404)


class BackfillTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_source_state")

    def test_backfill_collects_each_past_day_oldest_first(self):
        client = BackfillClient()
        result = asyncio.run(backfill_module("diddigo", days=5, client=client))
        self.assertEqual(result["collected"], 5)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(len(client.requested_dates), 5)
        self.assertEqual(client.requested_dates, sorted(client.requested_dates))
        self.assertNotIn(business_today(), client.requested_dates)
        today = date.fromisoformat(business_today())
        stored = store.summaries_range("diddigo", DAILY_KIND, (today - timedelta(days=5)).isoformat(), today.isoformat())
        self.assertEqual(len(stored), 5)
        self.assertTrue(all(record["is_final"] for record in stored))

    def test_backfill_does_not_touch_live_source_state(self):
        asyncio.run(backfill_module("diddigo", days=3, client=AlwaysFailingClient()))
        self.assertIsNone(store.source_state("diddigo", DAILY_KIND))

    def test_backfill_stops_early_when_module_never_answers(self):
        client = AlwaysFailingClient()
        result = asyncio.run(backfill_module("diddigo", days=30, client=client))
        self.assertEqual(result["collected"], 0)
        self.assertEqual(result["failed"], 3)
        self.assertEqual(result["last_error_code"], "route_missing")

    def test_backfill_survives_scattered_failures(self):
        today = date.fromisoformat(business_today())
        failing = {(today - timedelta(days=2)).isoformat()}
        result = asyncio.run(backfill_module("diddigo", days=4, client=BackfillClient(fail_dates=failing)))
        self.assertEqual(result["collected"], 3)
        self.assertEqual(result["failed"], 1)


class HistoryApiTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_source_state")
        self.client = TestClient(app)
        asyncio.run(backfill_module("diddigo", days=10, client=BackfillClient()))

    def test_history_returns_series_within_range(self):
        response = self.client.get("/api/pilotage/modules/diddigo/history?days=7", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["items"]), 6)  # 7-day window includes today, which has no row
        dates = [item["date"] for item in body["items"]]
        self.assertEqual(dates, sorted(dates))
        self.assertTrue(all(item["is_final"] for item in body["items"]))
        self.assertEqual(body["items"][0]["metrics"][0]["name"], "rides_requested")

    def test_history_enforces_module_access(self):
        headers = {"X-User-Id": "mm-1", "X-Role": "module_manager", "X-Modules": "diddisend"}
        response = self.client.get("/api/pilotage/modules/diddigo/history", headers=headers)
        self.assertEqual(response.status_code, 403)

    def test_history_rejects_out_of_range_days(self):
        response = self.client.get("/api/pilotage/modules/diddigo/history?days=365", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 422)

    def test_backfill_endpoint_requires_collect_role(self):
        response = self.client.post(
            "/api/pilotage/sources/diddigo/backfill?days=5",
            headers={"X-User-Id": "aud-1", "X-Role": "audit_read"},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
