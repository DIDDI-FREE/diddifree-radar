"""Week/month rollups computed locally from stored daily summaries.

Only additive metrics (unit ``count`` or ``XOF``) are summed; rates and
averages cannot be aggregated by addition and are deliberately excluded.
The source modules are never called here — rollups read the local store.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.collector import store
from app.collector.collector import DAILY_KIND

ADDITIVE_UNITS = {"count", "xof"}


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


def aggregate_periods(module: str, *, period: str, count: int, today: date) -> list[dict]:
    """Return the last ``count`` buckets (oldest first), current one partial."""
    if period not in {"week", "month"}:
        raise ValueError("period must be week or month")
    count = max(1, min(count, 12))
    oldest_start, _, _ = _bucket_bounds(period, today, count - 1)
    records = store.summaries_range(module, DAILY_KIND, oldest_start.isoformat(), today.isoformat())
    by_date = {record["summary_date"]: record for record in records}

    buckets: list[dict] = []
    for offset in range(count - 1, -1, -1):
        start, end, key = _bucket_bounds(period, today, offset)
        totals: dict[str, dict] = {}
        days_with_data = 0
        day = start
        while day <= min(end, today):
            record = by_date.get(day.isoformat())
            if record:
                days_with_data += 1
                for metric in record["payload"].get("metrics", []):
                    unit = str(metric.get("unit", "")).lower()
                    value = metric.get("value")
                    if unit in ADDITIVE_UNITS and isinstance(value, (int, float)):
                        entry = totals.setdefault(
                            metric["name"],
                            {"name": metric["name"], "label": metric.get("label") or metric["name"], "unit": metric.get("unit"), "value": 0},
                        )
                        entry["value"] += value
                        entry["label"] = metric.get("label") or entry["label"]
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
                "metrics": list(totals.values()),
            }
        )
    return buckets
