import json
import unittest
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.collector.collector import business_today
from app.collector.rollups import aggregate_periods, week_start
from app.core.db import execute, init_db, utc_now_iso
from app.main import app
from tests.test_api import DG_HEADERS


def seed_day(module: str, day: str, rides: int, fare: int, *, is_final: bool = True) -> None:
    payload = {
        "contract_version": "pilotage.v1",
        "module": module,
        "date": day,
        "timezone": "Africa/Abidjan",
        "is_final": is_final,
        "metrics": [
            {"name": "rides_completed", "label": "Courses terminées", "value": rides, "unit": "count"},
            {"name": "fare_total_xof", "label": "CA", "value": fare, "unit": "XOF"},
            {"name": "completion_rate", "label": "Taux", "value": 85.0, "unit": "percent"},
        ],
        "calculated_at": utc_now_iso(),
    }
    execute(
        "INSERT INTO pilotage_summaries (module, kind, summary_date, payload, calculated_at, is_final, collected_at) VALUES (?, 'daily', ?, ?, ?, ?, ?) "
        "ON CONFLICT (module, kind, summary_date) DO UPDATE SET payload = excluded.payload, is_final = excluded.is_final",
        (module, day, json.dumps(payload), utc_now_iso(), int(is_final), utc_now_iso()),
    )


class RollupTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        self.today = date.fromisoformat(business_today())

    def _seed_days(self, count: int):
        for offset in range(count):
            day = (self.today - timedelta(days=offset)).isoformat()
            seed_day("diddigo", day, rides=10, fare=1000, is_final=offset > 0)

    def test_week_buckets_are_monday_to_sunday(self):
        self._seed_days(15)
        buckets = aggregate_periods("diddigo", period="week", count=3, today=self.today)
        self.assertEqual(len(buckets), 3)
        for bucket in buckets:
            start = date.fromisoformat(bucket["start"])
            end = date.fromisoformat(bucket["end"])
            self.assertEqual(start.weekday(), 0, "week must start on Monday")
            self.assertEqual((end - start).days, 6)
            self.assertEqual(bucket["expected_days"], 7)
        self.assertEqual(date.fromisoformat(buckets[-1]["start"]), week_start(self.today))

    def test_additive_metrics_are_summed_and_rates_excluded(self):
        self._seed_days(15)
        buckets = aggregate_periods("diddigo", period="week", count=3, today=self.today)
        full_week = next(b for b in buckets if b["is_complete"])
        metrics = {m["name"]: m for m in full_week["metrics"]}
        self.assertEqual(metrics["rides_completed"]["value"], 70)
        self.assertEqual(metrics["fare_total_xof"]["value"], 7000)
        self.assertNotIn("completion_rate", metrics, "percent metrics must not be summed")

    def test_current_week_is_partial(self):
        self._seed_days(15)
        buckets = aggregate_periods("diddigo", period="week", count=2, today=self.today)
        current = buckets[-1]
        self.assertFalse(current["is_complete"])
        self.assertEqual(current["days_with_data"], self.today.weekday() + 1)

    def test_month_bucket_key_and_bounds(self):
        self._seed_days(10)
        buckets = aggregate_periods("diddigo", period="month", count=2, today=self.today)
        self.assertEqual(len(buckets), 2)
        current = buckets[-1]
        self.assertEqual(current["key"], self.today.strftime("%Y-%m"))
        self.assertEqual(current["start"], self.today.replace(day=1).isoformat())

    def test_missing_days_reduce_days_with_data(self):
        seed_day("diddigo", (self.today - timedelta(days=1)).isoformat(), 5, 500)
        buckets = aggregate_periods("diddigo", period="week", count=4, today=self.today)
        total_days = sum(b["days_with_data"] for b in buckets)
        self.assertEqual(total_days, 1)


class AggregatesApiTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")
        self.client = TestClient(app)
        today = date.fromisoformat(business_today())
        for offset in range(10):
            seed_day("diddigo", (today - timedelta(days=offset)).isoformat(), 10, 1000, is_final=offset > 0)

    def test_aggregates_endpoint_returns_buckets(self):
        response = self.client.get("/api/pilotage/modules/diddigo/aggregates?period=week&count=3", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["period"], "week")
        self.assertEqual(len(body["buckets"]), 3)

    def test_aggregates_rejects_bad_period(self):
        response = self.client.get("/api/pilotage/modules/diddigo/aggregates?period=year", headers=DG_HEADERS)
        self.assertEqual(response.status_code, 422)

    def test_aggregates_enforces_module_access(self):
        headers = {"X-User-Id": "mm-1", "X-Role": "module_manager", "X-Modules": "diddisend"}
        response = self.client.get("/api/pilotage/modules/diddigo/aggregates", headers=headers)
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
