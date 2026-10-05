import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from app.sources.catalog import enabled_modules, get_source
from app.sources.client import PilotageSourceClient
from app.sources.normalization import normalize_daily_summary


def run(coro):
    return asyncio.run(coro)


class SourceCatalogTests(unittest.TestCase):
    def test_ready_modules_are_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PILOTAGE_MODULES", None)
            self.assertEqual(enabled_modules(), ["identity", "diddigo", "diddisend", "diddipay", "diddifood"])

    def test_current_module_contracts_are_configured(self):
        diddigo = get_source("diddigo")
        self.assertEqual(diddigo.daily_summary_path(), "/internal/pilotage/daily-summary")
        self.assertEqual(diddigo.scope(), "ride-summary:read")
        self.assertEqual(diddigo.audience(), "diddigo")

        diddisend = get_source("diddisend")
        self.assertEqual(diddisend.daily_summary_path(), "/internal/pilotage/daily-summary")
        self.assertEqual(diddisend.scope(), "delivery-summary:read")

        identity = get_source("identity")
        self.assertEqual(identity.daily_summary_path(), "/internal/pilotage/identity-summary")
        self.assertEqual(identity.audience(), "diddifree-id")
        self.assertEqual(identity.scope(), "identity:reporting:read")

        diddifood = get_source("diddifood")
        self.assertEqual(diddifood.daily_summary_path(), "/food/v1/internal/pilotage/daily-summary")
        self.assertEqual(diddifood.scope(), "food:pilotage:read")

    def test_daily_path_can_be_overridden(self):
        with patch.dict(os.environ, {"PILOTAGE_DIDDIGO_DAILY_SUMMARY_PATH": "/custom/summary"}):
            self.assertEqual(get_source("diddigo").daily_summary_path(), "/custom/summary")

    def test_client_uses_declared_daily_path(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["path"] = request.url.path
            seen["date"] = request.url.params["date"]
            return httpx.Response(200, json={"ok": True})

        source = get_source("identity")
        source_without_auth = type(source)(
            source.key,
            source.display_name,
            source.base_url_env,
            source.default_base_url,
            source.default_summary_base,
            False,
            source.default_scope,
            source.default_daily_summary_path,
            source.default_audience,
        )
        client = PilotageSourceClient(source_without_auth, transport=httpx.MockTransport(handler))
        self.assertEqual(run(client.daily_summary("2026-10-01")), {"ok": True})
        self.assertEqual(
            seen,
            {"path": "/identity/v1/internal/pilotage/identity-summary", "date": "2026-10-01"},
        )


class SourceNormalizationTests(unittest.TestCase):
    def test_identity_snapshots_are_not_marked_additive(self):
        payload = {
            "metrics": [
                {"name": "users_total", "value": 100, "unit": "count"},
                {"name": "users_registered", "value": 3, "unit": "count"},
                {"name": "daily_active_users", "value": 20, "unit": "count"},
            ]
        }
        normalized = normalize_daily_summary("identity", payload)
        aggregations = {metric["name"]: metric["aggregation"] for metric in normalized["metrics"]}
        self.assertEqual(aggregations["users_total"], "last")
        self.assertEqual(aggregations["users_registered"], "sum")
        self.assertEqual(aggregations["daily_active_users"], "last")
        self.assertNotIn("aggregation", payload["metrics"][0], "normalization must not mutate source payloads")

    def test_operational_metrics_default_to_sum(self):
        payload = {"metrics": [{"name": "rides_completed", "value": 8, "unit": "count"}]}
        normalized = normalize_daily_summary("diddigo", payload)
        self.assertEqual(normalized["metrics"][0]["aggregation"], "sum")

    def test_daily_ratios_and_weighted_averages_use_source_components(self):
        payload = {"metrics": [
            {"name": "rides_requested", "value": 12, "unit": "count"},
            {"name": "rides_completed", "value": 8, "unit": "count"},
            {"name": "completed_fare_total_xof", "value": 24000, "unit": "XOF"},
        ]}
        metrics = {metric["name"]: metric for metric in normalize_daily_summary("diddigo", payload)["metrics"]}
        self.assertEqual(metrics["ride_completion_rate"]["value"], 66.67)
        self.assertEqual(metrics["average_completed_fare_xof"]["value"], "3000.00")
        self.assertEqual(metrics["ride_completion_rate"]["denominator"], "rides_requested")

    def test_derived_metric_is_omitted_when_denominator_is_zero(self):
        payload = {"metrics": [
            {"name": "rides_requested", "value": 0, "unit": "count"},
            {"name": "rides_completed", "value": 0, "unit": "count"},
            {"name": "completed_fare_total_xof", "value": 0, "unit": "XOF"},
        ]}
        names = {metric["name"] for metric in normalize_daily_summary("diddigo", payload)["metrics"]}
        self.assertNotIn("ride_completion_rate", names)
        self.assertNotIn("average_completed_fare_xof", names)


if __name__ == "__main__":
    unittest.main()
