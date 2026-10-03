from __future__ import annotations

import csv
import io
from datetime import date

from app.alerts import list_alerts
from app.collector import store
from app.collector.collector import DAILY_KIND
from app.collector.rollups import aggregate_periods
from app.planning import list_objectives
from app.sources.catalog import get_source


def build_report(*, period: str, anchor: date, modules: list[str], include_finance: bool) -> dict:
    blocks = []
    for module in modules:
        if period == "day":
            record = store.latest_summary(module, DAILY_KIND, summary_date=anchor.isoformat())
            metrics = record["payload"].get("metrics", []) if record else []
            coverage = {"days_with_data": int(bool(record)), "expected_days": 1, "is_complete": bool(record and record["is_final"])}
            start = end = anchor.isoformat()
        else:
            bucket = aggregate_periods(module, period=period, count=1, today=anchor)[0]
            metrics = bucket["metrics"]
            coverage = {key: bucket[key] for key in ("days_with_data", "expected_days", "is_complete")}
            start, end = bucket["start"], bucket["end"]
        if not include_finance:
            metrics = [metric for metric in metrics if str(metric.get("unit", "")).upper() != "XOF"]
        freshness = store.compute_freshness(module, DAILY_KIND).model_dump(mode="json")
        blocks.append({"module": module, "display_name": get_source(module).display_name, "from": start, "to": end, "coverage": coverage, "freshness": freshness, "metrics": metrics})
    objectives = [item for item in list_objectives() if item["module"] in modules and (include_finance or item["unit"].upper() != "XOF")]
    alerts = [item for item in list_alerts(status="open") if item["module"] in modules]
    return {
        "contract_version": "pilotage.report.v1",
        "period": period,
        "anchor": anchor.isoformat(),
        "modules": blocks,
        "objectives": objectives,
        "open_alerts": alerts,
    }


def report_csv(report: dict) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["period", "from", "to", "module", "metric", "label", "value", "unit", "days_with_data", "expected_days", "is_complete"])
    for block in report["modules"]:
        for metric in block["metrics"]:
            writer.writerow([
                report["period"], block["from"], block["to"], block["module"], metric.get("name"), metric.get("label") or metric.get("name"),
                metric.get("value"), metric.get("unit"), block["coverage"]["days_with_data"], block["coverage"]["expected_days"], block["coverage"]["is_complete"],
            ])
    return output.getvalue()
