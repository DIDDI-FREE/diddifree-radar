import calendar
from datetime import date, timedelta
from decimal import Decimal

from app.collector import store
from app.collector.collector import breakdown_kind
from app.collector.rollups import month_start, week_start


def _bounds(period: str, anchor: date, offset: int):
    if period == "week":
        start = week_start(anchor) - timedelta(weeks=offset)
        return start, start + timedelta(days=6), f"{start.isocalendar().year}-S{start.isocalendar().week:02d}"
    start = month_start(anchor)
    for _ in range(offset):
        start = month_start(start - timedelta(days=1))
    return start, start.replace(day=calendar.monthrange(start.year, start.month)[1]), start.strftime("%Y-%m")


def aggregate_breakdowns(module: str, dimension: str, metric: str, *, period: str, count: int, today: date) -> list[dict]:
    if period not in {"week", "month"}:
        raise ValueError("period must be week or month")
    oldest, _, _ = _bounds(period, today, count - 1)
    records = store.summaries_range(module, breakdown_kind(dimension, metric), oldest.isoformat(), today.isoformat())
    by_date = {record["summary_date"]: record for record in records}
    buckets = []
    for offset in range(count - 1, -1, -1):
        start, end, key = _bounds(period, today, offset)
        values: dict[str, dict] = {}
        days = 0
        unit = None
        cursor = start
        while cursor <= min(end, today):
            record = by_date.get(cursor.isoformat())
            if record:
                days += 1
                payload = record["payload"]
                unit = unit or payload.get("unit")
                for item in payload.get("items", []):
                    entry = values.setdefault(item["key"], {"key": item["key"], "label": item.get("label") or item["key"], "value": Decimal("0"), "string": isinstance(item.get("value"), str)})
                    entry["value"] += Decimal(str(item["value"]))
                    entry["string"] = entry["string"] or isinstance(item.get("value"), str)
            cursor += timedelta(days=1)
        items = [{"key": item["key"], "label": item["label"], "value": format(item["value"], "f") if item["string"] else int(item["value"]) if item["value"] == item["value"].to_integral_value() else float(item["value"])} for item in values.values()]
        total = sum((Decimal(str(item["value"])) for item in items), Decimal("0"))
        buckets.append({"key": key, "start": start.isoformat(), "end": end.isoformat(), "days_with_data": days, "expected_days": (end - start).days + 1, "is_complete": end < today and days == (end - start).days + 1, "unit": unit, "total": format(total, "f") if any(isinstance(item["value"], str) for item in items) else int(total) if total == total.to_integral_value() else float(total), "items": items})
    return buckets
