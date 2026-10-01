"""Consumer-side enrichment for module-owned Pilotage summaries."""

from __future__ import annotations

from copy import deepcopy


IDENTITY_AGGREGATIONS = {
    "users_total": "last",
    "users_registered": "sum",
    "users_verified": "last",
    "users_active": "last",
    "daily_active_users": "last",
    "monthly_active_users": "last",
}


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
    return normalized
