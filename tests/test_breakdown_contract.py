import unittest

from pydantic import ValidationError

from app.contracts.breakdown import PilotageBreakdown


VALID = {
    "module": "diddigo",
    "date": "2026-10-03",
    "dimension": "payment_method",
    "metric": "rides_completed",
    "unit": "count",
    "total": 10,
    "items": [{"key": "cash", "label": "Espèces", "value": 6}, {"key": "wave", "label": "Wave", "value": 4}],
    "calculated_at": "2026-10-04T00:00:00Z",
}


class BreakdownContractTests(unittest.TestCase):
    def test_valid_breakdown(self):
        self.assertEqual(PilotageBreakdown.model_validate(VALID).contract_version, "pilotage.breakdown.v1")

    def test_items_must_match_total(self):
        with self.assertRaises(ValidationError):
            PilotageBreakdown.model_validate({**VALID, "total": 11})


if __name__ == "__main__":
    unittest.main()
