"""Week/month rollups computed locally from stored daily summaries.

Each metric declares how it behaves across days. Additive flows are summed,
snapshots keep the last value, and extrema keep their minimum or maximum.
Ratios and weighted averages remain excluded until their components are
available; adding already-computed rates would be mathematically wrong.
The source modules are never called here — rollups read the local store.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.collector import store
from app.collector.collector import DAILY_KIND

SUPPORTED_AGGREGATIONS = {"sum", "last", "min", "max"}


def _decimal_value(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    return None


def _serialized_value(value: Decimal, *, string_value: bool, integral_value: bool):
    if string_value:
        return format(value, "f")
    if integral_value and value == value.to_integral_value():
        return int(value)
    return float(value)


def _accumulate(totals: dict[str, dict], metric: dict) -> None:
    aggregation = metric.get("aggregation", "sum")
    if aggregation not in SUPPORTED_AGGREGATIONS:
        return
    value = _decimal_value(metric.get("value"))
    if value is None:
        return

    name = metric.get("name")
    if not name:
        return
    entry = totals.get(name)
    if entry is None:
        totals[name] = {
            "name": name,
            "label": metric.get("label") or name,
            "unit": metric.get("unit"),
            "aggregation": aggregation,
            "_value": value,
            "_string_value": isinstance(metric.get("value"), str),
            "_integral_value": isinstance(metric.get("value"), int) and not isinstance(metric.get("value"), bool),
        }
        return
    if entry["aggregation"] != aggregation:
        return
    entry["label"] = metric.get("label") or entry["label"]
    entry["_string_value"] = entry["_string_value"] or isinstance(metric.get("value"), str)
    entry["_integral_value"] = entry["_integral_value"] and isinstance(metric.get("value"), int)

    if aggregation == "sum":
        entry["_value"] += value
    elif aggregation == "last":
        entry["_value"] = value
    elif aggregation == "min":
        entry["_value"] = min(entry["_value"], value)
    elif aggregation == "max":
        entry["_value"] = max(entry["_value"], value)


def _public_metrics(totals: dict[str, dict], derived: dict[str, dict]) -> list[dict]:
    metrics = []
    for entry in totals.values():
        metrics.append(
            {
                "name": entry["name"],
                "label": entry["label"],
                "unit": entry["unit"],
                "aggregation": entry["aggregation"],
                "value": _serialized_value(
                    entry["_value"],
                    string_value=entry["_string_value"],
                    integral_value=entry["_integral_value"],
                ),
            }
        )
    for spec in derived.values():
        numerator = totals.get(spec.get("numerator"))
        denominator = totals.get(spec.get("denominator"))
        if not numerator or not denominator or denominator["_value"] == 0:
            continue
        value = numerator["_value"] / denominator["_value"] * Decimal(str(spec.get("scale", 1)))
        metrics.append(
            {
                "name": spec["name"],
                "label": spec.get("label") or spec["name"],
                "unit": spec.get("unit"),
                "aggregation": spec["aggregation"],
                "numerator": spec.get("numerator"),
                "denominator": spec.get("denominator"),
                "scale": spec.get("scale", 1),
                "value": format(value.quantize(Decimal("0.01")), "f") if str(spec.get("unit", "")).lower() == "xof" else float(value.quantize(Decimal("0.01"))),
            }
        )
    return metrics


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def month_start(day: date) -> date:
    return day.replace(day=1)


def _bucket_bounds(period: str, anchor: date, offset: int) -> tuple[date, date, str]:
    """Start, end (inclusive) and key of the bucket ``offset`` periods before anchor's."""
    if period == "week":
        start = week_start(anchor) - timedelta(weeks=offset)
        end = start + timedelta(days=6)
        iso = start.isocalendar()
        return start, end, f"{iso.year}-S{iso.week:02d}"
    start = month_start(anchor)
    for _ in range(offset):
        start = month_start(start - timedelta(days=1))
    end = start.replace(day=calendar.monthrange(start.year, start.month)[1])
    return start, end, start.strftime("%Y-%m")


def aggregate_periods(module: str, *, period: str, count: int, today: date, kind: str = DAILY_KIND) -> list[dict]:
    """Return the last ``count`` buckets (oldest first), current one partial."""
    if period not in {"week", "month"}:
        raise ValueError("period must be week or month")
    count = max(1, min(count, 12))
    oldest_start, _, _ = _bucket_bounds(period, today, count - 1)
    records = store.summaries_range(module, kind, oldest_start.isoformat(), today.isoformat())
    by_date = {record["summary_date"]: record for record in records}

    buckets: list[dict] = []
    for offset in range(count - 1, -1, -1):
        start, end, key = _bucket_bounds(period, today, offset)
        totals: dict[str, dict] = {}
        derived: dict[str, dict] = {}
        days_with_data = 0
        day = start
        while day <= min(end, today):
            record = by_date.get(day.isoformat())
            if record:
                days_with_data += 1
                for metric in record["payload"].get("metrics", []):
                    if metric.get("aggregation") in {"ratio", "weighted_average"}:
                        derived.setdefault(metric.get("name", ""), metric)
                    else:
                        _accumulate(totals, metric)
            day += timedelta(days=1)
        expected_days = (end - start).days + 1
        buckets.append(
            {
                "key": key,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "days_with_data": days_with_data,
                "expected_days": expected_days,
                "is_complete": end < today and days_with_data == expected_days,
                "metrics": _public_metrics(totals, derived),
            }
        )
    return buckets
