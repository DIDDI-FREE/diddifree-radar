import unittest

from app.contracts.pilotage import PilotageSummary

GUIDE_EXAMPLE = {
    "contract_version": "pilotage.v1",
    "module": "diddigo",
    "date": "2026-09-23",
    "timezone": "Africa/Abidjan",
    "is_final": False,
    "metrics": [
        {"name": "rides_requested", "value": 1000, "unit": "count"},
        {"name": "rides_completed", "value": 720, "unit": "count"},
        {"name": "completed_fare_total_xof", "value": 4850000, "unit": "XOF"},
    ],
    "calculated_at": "2026-09-23T14:32:10Z",
    "sources": [{"module": "diddigo", "record_type": "ride-summary"}],
    "deep_links": [{"label": "Open rides in Backoffice", "href": "/backoffice/#diddigo-rides"}],
}


class ContractTests(unittest.TestCase):
    def test_guide_example_parses(self):
        summary = PilotageSummary.model_validate(GUIDE_EXAMPLE)
        self.assertEqual(summary.module, "diddigo")
        self.assertEqual(summary.contract_version, "pilotage.v1")
        self.assertFalse(summary.is_final)
        self.assertEqual(len(summary.metrics), 3)

    def test_missing_optional_envelope_fields_get_defaults(self):
        payload = {key: value for key, value in GUIDE_EXAMPLE.items() if key not in {"contract_version", "is_final"}}
        summary = PilotageSummary.model_validate(payload)
        self.assertEqual(summary.contract_version, "pilotage.v1")
        self.assertFalse(summary.is_final)

    def test_consumer_tolerates_additive_fields(self):
        payload = {**GUIDE_EXAMPLE, "experimental_field": {"anything": 1}}
        summary = PilotageSummary.model_validate(payload)
        self.assertEqual(summary.module, "diddigo")

    def test_rejects_summary_without_metrics(self):
        payload = {key: value for key, value in GUIDE_EXAMPLE.items() if key != "metrics"}
        with self.assertRaises(Exception):
            PilotageSummary.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
