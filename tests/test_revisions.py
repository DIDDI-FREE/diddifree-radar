import unittest

from app.collector.store import latest_summary, save_summary
from app.core.db import execute, init_db


class SummaryRevisionTests(unittest.TestCase):
    def setUp(self):
        init_db()
        execute("DELETE FROM pilotage_summaries")

    @staticmethod
    def payload(value: int, calculated_at: str) -> dict:
        return {
            "contract_version": "pilotage.v1",
            "module": "diddigo",
            "date": "2026-10-01",
            "timezone": "Africa/Abidjan",
            "is_final": True,
            "metrics": [{"name": "rides_completed", "value": value, "unit": "count", "aggregation": "sum"}],
            "calculated_at": calculated_at,
        }

    def test_refresh_without_business_change_keeps_revision(self):
        save_summary("diddigo", "daily", "2026-10-01", self.payload(8, "2026-10-01T12:00:00Z"), "2026-10-01T12:00:00Z", True)
        first = latest_summary("diddigo", "daily", "2026-10-01")
        save_summary("diddigo", "daily", "2026-10-01", self.payload(8, "2026-10-01T12:01:00Z"), "2026-10-01T12:01:00Z", True)
        refreshed = latest_summary("diddigo", "daily", "2026-10-01")
        self.assertEqual(refreshed["revision"], 1)
        self.assertEqual(refreshed["first_collected_at"], first["first_collected_at"])

    def test_business_change_increments_revision(self):
        save_summary("diddigo", "daily", "2026-10-01", self.payload(8, "2026-10-01T12:00:00Z"), "2026-10-01T12:00:00Z", True)
        save_summary("diddigo", "daily", "2026-10-01", self.payload(9, "2026-10-01T12:01:00Z"), "2026-10-01T12:01:00Z", True)
        corrected = latest_summary("diddigo", "daily", "2026-10-01")
        self.assertEqual(corrected["revision"], 2)


if __name__ == "__main__":
    unittest.main()
