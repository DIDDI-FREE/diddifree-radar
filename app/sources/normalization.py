"""Consumer-side enrichment for module-owned Pilotage summaries."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation


IDENTITY_AGGREGATIONS = {
    "users_total": "last",
    "users_registered": "sum",
    "users_verified": "last",
    "users_active": "last",
    "daily_active_users": "last",
    "monthly_active_users": "last",
}

DERIVED_METRICS = {
    "identity": [
        {
            "name": "verification_rate",
            "label": "Taux de comptes vérifiés",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "users_verified",
            "denominator": "users_total",
            "scale": 100,
        }
    ],
    "diddigo": [
        {
            "name": "ride_completion_rate",
            "label": "Taux de courses terminées",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "rides_completed",
            "denominator": "rides_requested",
            "scale": 100,
        },
        {
            "name": "average_completed_fare_xof",
            "label": "Montant moyen par course terminée",
            "unit": "XOF",
            "aggregation": "weighted_average",
            "numerator": "completed_fare_total_xof",
            "denominator": "rides_completed",
        },
    ],
    "diddisend": [
        {
            "name": "delivery_completion_rate",
            "label": "Taux de livraisons terminées",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "deliveries_completed",
            "denominator": "deliveries_requested",
            "scale": 100,
        },
        {
            "name": "average_completed_delivery_value_xof",
            "label": "Valeur moyenne par livraison terminée",
            "unit": "XOF",
            "aggregation": "weighted_average",
            "numerator": "completed_delivery_value",
            "denominator": "deliveries_completed",
        },
    ],
    "diddipay": [
        {
            "name": "refund_event_rate",
            "label": "Taux d'événements de remboursement",
            "unit": "percent",
            "aggregation": "ratio",
            "numerator": "confirmed_refunds_count",
            "denominator": "confirmed_payments_count",
            "scale": 100,
        }
    ],
}


def _decimal(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _derived_metric(spec: dict, values: dict[str, object]) -> dict | None:
    numerator = _decimal(values.get(spec["numerator"]))
    denominator = _decimal(values.get(spec["denominator"]))
    if numerator is None or denominator is None or denominator == 0:
        return None
    value = numerator / denominator * Decimal(str(spec.get("scale", 1)))
    serialized_value: float | str
    if spec["unit"] == "XOF":
        serialized_value = format(value.quantize(Decimal("0.01")), "f")
    else:
        serialized_value = float(value.quantize(Decimal("0.01")))
    return {**spec, "value": serialized_value}


def normalize_daily_summary(module: str, payload: dict) -> dict:
    """Add consumer metadata without changing a module's business values."""
    normalized = deepcopy(payload)
    metrics = normalized.get("metrics")
    if not isinstance(metrics, list):
        return normalized

    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = metric.get("name")
        if module == "identity":
            metric.setdefault("aggregation", IDENTITY_AGGREGATIONS.get(name, "last"))
        else:
            metric.setdefault("aggregation", "sum")
    values = {metric.get("name"): metric.get("value") for metric in metrics if isinstance(metric, dict)}
    existing_names = set(values)
    for spec in DERIVED_METRICS.get(module, []):
        if spec["name"] in existing_names:
            continue
        derived = _derived_metric(spec, values)
        if derived is not None:
            metrics.append(derived)
    return normalized
