import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from app.collector import store
from app.collector.collector import DAILY_KIND, collect_daily_summary
from app.core.db import execute, init_db
from app.sources.gateway import SourceRejected, SourceUnavailable
from tests.test_contracts import GUIDE_EXAMPLE


class FakeClient:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.requested_dates = []

    async def daily_summary(self, date):
        self.requested_dates.append(date)
        if self._error:
            raise self._error
        return self._result


def run(coro):
    return asyncio.run(coro)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        execute("DELETE FROM pilotage_source_state")

    def test_successful_collection_stores_summary_and_fresh_state(self):
        result = run(collect_daily_summary("diddigo", client=FakeClient(result=GUIDE_EXAMPLE)))
        self.assertEqual(result["status"], "collected")
        record = store.latest_summary("diddigo", DAILY_KIND)
        self.assertEqual(record["summary_date"], "2026-09-23")
        self.assertEqual(record["payload"]["metrics"][0]["name"], "rides_requested")
        freshness = store.compute_freshness("diddigo", DAILY_KIND)
        self.assertEqual(freshness.status, "fresh")

    def test_failure_keeps_last_value_and_reports_error(self):
        run(collect_daily_summary("diddigo", client=FakeClient(result=GUIDE_EXAMPLE)))
        error = SourceRejected("diddigo", "route_missing", "source does not expose this Pilotage route yet", status_code=404)
        result = run(collect_daily_summary("diddigo", client=FakeClient(error=error)))
        self.assertEqual(result["status"], "failed")
        record = store.latest_summary("diddigo", DAILY_KIND)
        self.assertIsNotNone(record, "a failed source must never erase the last valid value")
        self.assertEqual(record["payload"]["metrics"][0]["value"], 1000)
        state = store.source_state("diddigo", DAILY_KIND)
        self.assertEqual(state["last_error_code"], "route_missing")
        self.assertEqual(state["consecutive_failures"], 1)

    def test_never_successful_source_is_unavailable(self):
        error = SourceUnavailable("diddisend", "timeout", "source unavailable")
        run(collect_daily_summary("diddisend", client=FakeClient(error=error)))
        freshness = store.compute_freshness("diddisend", DAILY_KIND)
        self.assertEqual(freshness.status, "unavailable")
        self.assertIsNone(store.latest_summary("diddisend", DAILY_KIND))

    def test_old_success_becomes_stale(self):
        run(collect_daily_summary("diddigo", client=FakeClient(result=GUIDE_EXAMPLE)))
        old = (datetime.now(timezone.utc) - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%SZ")
        execute("UPDATE pilotage_source_state SET last_success_at = ? WHERE module = ?", (old, "diddigo"))
        freshness = store.compute_freshness("diddigo", DAILY_KIND)
        self.assertEqual(freshness.status, "stale")

    def test_invalid_contract_is_rejected_without_storing(self):
        result = run(collect_daily_summary("diddigo", client=FakeClient(result={"module": "diddigo"})))
        self.assertEqual(result["code"], "contract_invalid")
        self.assertIsNone(store.latest_summary("diddigo", DAILY_KIND))


if __name__ == "__main__":
    unittest.main()
