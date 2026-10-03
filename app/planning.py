from __future__ import annotations

from decimal import Decimal

from app.collector import store
from app.core.db import execute, row, rows, utc_now_iso


def set_objective(*, module: str, metric: str, period: str, period_start: str, target_value: Decimal, unit: str, changed_by: str) -> dict:
    latest = row(
        "SELECT MAX(revision) AS revision FROM pilotage_objectives WHERE module = ? AND metric = ? AND period = ? AND period_start = ?",
        (module, metric, period, period_start),
    )
    revision = int((latest or {}).get("revision") or 0) + 1
    execute(
        "INSERT INTO pilotage_objectives (module, metric, period, period_start, target_value, unit, revision, changed_by, changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (module, metric, period, period_start, format(target_value, "f"), unit, revision, changed_by, utc_now_iso()),
    )
    return objective(module, metric, period, period_start)


def objective(module: str, metric: str, period: str, period_start: str) -> dict | None:
    item = row(
        "SELECT module, metric, period, period_start, target_value, unit, revision, changed_by, changed_at FROM pilotage_objectives WHERE module = ? AND metric = ? AND period = ? AND period_start = ? ORDER BY revision DESC LIMIT 1",
        (module, metric, period, period_start),
    )
    return _with_progress(item) if item else None


def list_objectives(module: str | None = None) -> list[dict]:
    params = (module,) if module else ()
    where = "WHERE module = ?" if module else ""
    items = rows(
        f"SELECT o.module, o.metric, o.period, o.period_start, o.target_value, o.unit, o.revision, o.changed_by, o.changed_at FROM pilotage_objectives o JOIN (SELECT module, metric, period, period_start, MAX(revision) revision FROM pilotage_objectives GROUP BY module, metric, period, period_start) latest ON o.module=latest.module AND o.metric=latest.metric AND o.period=latest.period AND o.period_start=latest.period_start AND o.revision=latest.revision {where} ORDER BY o.period_start DESC, o.module, o.metric",
        params,
    )
    return [_with_progress(item) for item in items]


def objective_history(module: str, metric: str, period: str, period_start: str) -> list[dict]:
    return rows(
        "SELECT module, metric, period, period_start, target_value, unit, revision, changed_by, changed_at FROM pilotage_objectives WHERE module = ? AND metric = ? AND period = ? AND period_start = ? ORDER BY revision DESC",
        (module, metric, period, period_start),
    )


def _with_progress(item: dict) -> dict:
    result = dict(item)
    start = result["period_start"]
    end = start if result["period"] == "day" else start[:7] + "-31"
    records = store.summaries_range(result["module"], "daily", start, end)
    actual = Decimal("0")
    found = False
    for record in records:
        for metric in record["payload"].get("metrics", []):
            if metric.get("name") == result["metric"]:
                actual += Decimal(str(metric.get("value", 0)))
                found = True
    target = Decimal(result["target_value"])
    result["actual_value"] = format(actual, "f") if found else None
    result["progress_percent"] = float((actual / target * 100).quantize(Decimal("0.01"))) if found and target else None
    result["gap_value"] = format(actual - target, "f") if found else None
    return result
