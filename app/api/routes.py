from __future__ import annotations

import re
import os
import hashlib
import json
from urllib.parse import urljoin, urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from decimal import Decimal

from datetime import date as date_type, datetime, timedelta, timezone

from app.collector import store
from app.collector.collector import ACCOUNTING_KIND, BREAKDOWN_MATRIX, DAILY_KIND, FINANCE_KIND, FINANCE_MODULES, backfill_default_breakdowns, backfill_finance_module, backfill_module, breakdown_kind, business_timezone, business_today, collect_accounting_summary, collect_breakdown, collect_daily_summary, collect_default_breakdowns, collect_finance_summary
from app.collector.rollups import aggregate_periods
from app.collector.breakdown_rollups import aggregate_breakdowns
from app.core.auth import COLLECT_ROLES, FINANCE_ROLES, PilotagePrincipal, get_principal, require_module_access, require_role
from app.core.request_context import get_request_id
from app.sources.catalog import PILOTAGE_SOURCES, enabled_modules, get_source
from app.planning import list_objectives, objective_history, set_objective
from app.alerts import alert_history, list_alerts, reconcile_business_alerts, reconcile_source_alerts, update_alert
from app.reports import build_report, report_csv, report_pdf

router = APIRouter(prefix="/pilotage", tags=["pilotage"])

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")

OVERVIEW_BREAKDOWNS = {
    "diddigo": (("final_status", "rides_requested"), ("payment_method", "rides_completed"), ("service_type", "rides_completed")),
    "diddisend": (("final_status", "deliveries_requested"), ("payment_method", "deliveries_completed"), ("service_type", "deliveries_completed"), ("pickup_city", "deliveries_completed"), ("participant_category", "deliveries_completed")),
}


class ObjectiveInput(BaseModel):
    period: str = Field(pattern="^(day|month)$")
    period_start: date_type
    target_value: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)


class AlertUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|acknowledged|resolved)$")
    owner_id: str | None = Field(default=None, max_length=120)
    due_at: datetime | None = None


def _known_module(module: str) -> str:
    if module not in PILOTAGE_SOURCES:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "unknown_module", "message": "Module is not a Pilotage source", "request_id": get_request_id()}},
        )
    return module


def _visible_metrics(metrics: list[dict], principal: PilotagePrincipal) -> list[dict]:
    if principal.role in FINANCE_ROLES:
        return metrics
    return [metric for metric in metrics if str(metric.get("unit", "")).upper() != "XOF"]


def _visible_payload(payload: dict | None, principal: PilotagePrincipal) -> dict | None:
    if payload is None:
        return None
    visible = dict(payload)
    visible["metrics"] = _visible_metrics(payload.get("metrics", []), principal)
    visible["deep_links"] = [_absolute_backoffice_link(link) for link in payload.get("deep_links", [])]
    return visible


def _absolute_backoffice_link(link: dict) -> dict:
    visible = dict(link)
    href = str(link.get("href") or "").strip()
    if not href:
        return visible
    parsed = urlsplit(href)
    if parsed.scheme in {"http", "https"}:
        return visible
    base_url = os.getenv("PILOTAGE_BACKOFFICE_BASE_URL", "https://admin-staging.diddifree.com").rstrip("/") + "/"
    visible["href"] = urljoin(base_url, href.lstrip("/"))
    return visible


def _audit_financial_access(principal: PilotagePrincipal, resource: str, module: str | None = None) -> None:
    if principal.role in FINANCE_ROLES:
        store.record_financial_access(principal.user_id, principal.role, resource, module)


@router.put("/objectives/{module}/{metric}")
def write_objective(
    module: str,
    metric: str,
    payload: ObjectiveInput,
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_module_access(principal, module)
    require_role(principal, {"dg_global", "finance_admin", "operations_manager"})
    if payload.unit.upper() == "XOF":
        require_role(principal, FINANCE_ROLES)
        _audit_financial_access(principal, "objective-write", module)
    start = payload.period_start.isoformat()
    if payload.period == "month" and payload.period_start.day != 1:
        raise HTTPException(status_code=422, detail={"error": {"code": "invalid_period_start", "message": "A monthly objective must start on the first day of the month"}})
    return {"objective": set_objective(module=module, metric=metric, period=payload.period, period_start=start, target_value=payload.target_value, unit=payload.unit, changed_by=principal.user_id)}


@router.get("/objectives")
def read_objectives(
    module: str | None = None,
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    if module:
        _known_module(module)
        require_module_access(principal, module)
    items = [item for item in list_objectives(module) if principal.can_view(item["module"])]
    if principal.role not in FINANCE_ROLES:
        items = [item for item in items if item["unit"].upper() != "XOF"]
    else:
        _audit_financial_access(principal, "objectives", module)
    return {"items": items}


@router.get("/objectives/{module}/{metric}/history")
def read_objective_history(
    module: str,
    metric: str,
    period: str = Query(pattern="^(day|month)$"),
    period_start: date_type = Query(),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_module_access(principal, module)
    items = objective_history(module, metric, period, period_start.isoformat())
    if items and items[0]["unit"].upper() == "XOF":
        require_role(principal, FINANCE_ROLES)
        _audit_financial_access(principal, "objective-history", module)
    return {"items": items}


@router.get("/alerts")
def read_alerts(
    status: str | None = Query(default=None, pattern="^(open|acknowledged|resolved)$"),
    module: str | None = None,
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    if module:
        _known_module(module)
        require_module_access(principal, module)
    reconcile_source_alerts()
    items = reconcile_business_alerts(date_type.fromisoformat(business_today()))
    items = [item for item in items if principal.can_view(item["module"] or "global")]
    if status:
        items = [item for item in items if item["status"] == status]
    if module:
        items = [item for item in items if item["module"] == module]
    return {"items": items}


@router.patch("/alerts/{alert_id}")
def change_alert(
    alert_id: int,
    payload: AlertUpdate,
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    require_role(principal, {"dg_global", "operations_manager"})
    current = next((item for item in list_alerts() if item["id"] == alert_id), None)
    if not current:
        raise HTTPException(status_code=404, detail={"error": {"code": "alert_not_found", "message": "Alert does not exist"}})
    if current["module"]:
        require_module_access(principal, current["module"])
    updated = update_alert(
        alert_id,
        actor_id=principal.user_id,
        status=payload.status,
        owner_id=payload.owner_id,
        due_at=payload.due_at.isoformat() if payload.due_at else None,
    )
    return {"alert": updated}


@router.get("/alerts/{alert_id}/history")
def read_alert_history(alert_id: int, principal: PilotagePrincipal = Depends(get_principal)) -> dict:
    current = next((item for item in list_alerts() if item["id"] == alert_id), None)
    if not current:
        raise HTTPException(status_code=404, detail={"error": {"code": "alert_not_found", "message": "Alert does not exist"}})
    if current["module"]:
        require_module_access(principal, current["module"])
    return {"items": alert_history(alert_id)}


@router.get("/reports/{period}")
def report(
    period: str,
    anchor: date_type = Query(default_factory=lambda: date_type.fromisoformat(business_today())),
    format: str = Query(default="json", pattern="^(json|csv|pdf)$"),
    principal: PilotagePrincipal = Depends(get_principal),
):
    if period not in {"day", "week", "month"}:
        raise HTTPException(status_code=404, detail={"error": {"code": "unknown_report", "message": "Report period must be day, week or month"}})
    modules = [module for module in enabled_modules() if principal.can_view(module)]
    include_finance = principal.role in FINANCE_ROLES
    payload = build_report(period=period, anchor=anchor, modules=modules, include_finance=include_finance)
    if include_finance:
        _audit_financial_access(principal, f"report-{format}")
    if format == "csv":
        filename = f"pilotage-{period}-{anchor.isoformat()}.csv"
        return Response(content=report_csv(payload), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    if format == "pdf":
        filename = f"pilotage-{period}-{anchor.isoformat()}.pdf"
        return Response(content=report_pdf(payload), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    return payload


def _module_block(module: str, principal: PilotagePrincipal) -> dict:
    record = store.latest_summary(module, DAILY_KIND)
    summary_date = record["summary_date"] if record else business_today()
    stored_finance_record = store.latest_summary(module, FINANCE_KIND, summary_date=summary_date)
    finance_record = stored_finance_record if principal.role in FINANCE_ROLES else None
    breakdowns = []
    for dimension, metric in OVERVIEW_BREAKDOWNS.get(module, ()):
        breakdown_record = store.latest_summary(module, breakdown_kind(dimension, metric), summary_date=summary_date)
        if breakdown_record:
            breakdowns.append(breakdown_record["payload"])
    state = store.source_state(module, DAILY_KIND)
    freshness = store.compute_freshness(module, DAILY_KIND, source_updated_at=record["calculated_at"] if record else None)
    breakdowns_expected = sum(len(metrics) for metrics in BREAKDOWN_MATRIX.get(module, {}).values())
    breakdowns_available = store.count_summaries_by_kind_prefix(module, "breakdown:", summary_date)
    block = {
        "module": module,
        "display_name": get_source(module).display_name,
        "summary": _visible_payload(record["payload"], principal) if record else None,
        "freshness": freshness.model_dump(mode="json"),
        "collected_at": record["collected_at"] if record else None,
        "revision": record["revision"] if record else None,
        "finance_summary": _visible_payload(finance_record["payload"], principal) if finance_record else None,
        "breakdown_highlights": breakdowns,
        "coverage": {
            "date": summary_date,
            "daily_available": record is not None,
            "finance_expected": module in FINANCE_MODULES,
            "finance_available": stored_finance_record is not None,
            "breakdowns_expected": breakdowns_expected,
            "breakdowns_available": breakdowns_available,
            "complete": record is not None
            and (module not in FINANCE_MODULES or stored_finance_record is not None)
            and breakdowns_available >= breakdowns_expected,
        },
    }
    if state and state["last_error_code"]:
        block["last_error"] = {"code": state["last_error_code"], "message": state["last_error_message"]}
    return block


@router.get("/health")
def health() -> dict:
    return {"module": "pilotage", "status": "healthy"}


@router.get("/overview")
def overview(principal: PilotagePrincipal = Depends(get_principal)) -> dict:
    modules = [module for module in enabled_modules() if principal.can_view(module)]
    _audit_financial_access(principal, "overview")
    return {
        "contract_version": "pilotage.v1",
        "date": business_today(),
        "timezone": str(business_timezone()),
        "modules": [_module_block(module, principal) for module in modules],
    }


@router.get("/modules/{module}/daily-summary")
def module_daily_summary(
    module: str,
    date: str | None = Query(default=None),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_module_access(principal, module)
    if date and not _DATE_PATTERN.fullmatch(date):
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "invalid_date", "message": "date must be YYYY-MM-DD", "request_id": get_request_id()}},
        )
    record = store.latest_summary(module, DAILY_KIND, summary_date=date)
    freshness = store.compute_freshness(module, DAILY_KIND, source_updated_at=record["calculated_at"] if record else None)
    if not record:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "summary_unavailable",
                    "message": "No collected summary is available for this module and date",
                    "details": {"module": module, "date": date, "freshness": freshness.model_dump(mode="json")},
                    "request_id": get_request_id(),
                }
            },
        )
    _audit_financial_access(principal, "daily-summary", module)
    return {
        "summary": _visible_payload(record["payload"], principal),
        "freshness": freshness.model_dump(mode="json"),
        "revision": record["revision"],
        "first_collected_at": record["first_collected_at"],
        "collected_at": record["collected_at"],
    }


@router.get("/modules/{module}/history")
def module_history(
    module: str,
    days: int = Query(default=7, ge=1, le=90),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_module_access(principal, module)
    today = date_type.fromisoformat(business_today())
    from_date = (today - timedelta(days=days - 1)).isoformat()
    records = store.summaries_range(module, DAILY_KIND, from_date, today.isoformat())
    _audit_financial_access(principal, "history", module)
    return {
        "module": module,
        "from": from_date,
        "to": today.isoformat(),
        "items": [
            {
                "date": record["summary_date"],
                "is_final": bool(record["is_final"]),
                "metrics": _visible_metrics(record["payload"].get("metrics", []), principal),
                "revision": record["revision"],
                "state": "corrected" if record["revision"] > 1 else ("final" if record["is_final"] else "provisional"),
                "first_collected_at": record["first_collected_at"],
                "collected_at": record["collected_at"],
            }
            for record in records
        ],
    }


@router.get("/modules/{module}/aggregates")
def module_aggregates(
    module: str,
    period: str = Query(default="week", pattern="^(week|month)$"),
    count: int = Query(default=8, ge=1, le=12),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_module_access(principal, module)
    today = date_type.fromisoformat(business_today())
    _audit_financial_access(principal, "aggregates", module)
    return {
        "module": module,
        "period": period,
        "buckets": [
            {**bucket, "metrics": _visible_metrics(bucket.get("metrics", []), principal)}
            for bucket in aggregate_periods(module, period=period, count=count, today=today)
        ],
    }


@router.get("/modules/{module}/finance-summary")
def module_finance_summary(
    module: str,
    date: str | None = Query(default=None),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, FINANCE_ROLES)
    require_module_access(principal, module)
    record = store.latest_summary(module, FINANCE_KIND, summary_date=date)
    if not record:
        raise HTTPException(status_code=404, detail={"error": {"code": "finance_summary_unavailable", "message": "No finance summary is available"}})
    _audit_financial_access(principal, "finance-summary", module)
    return {"summary": _visible_payload(record["payload"], principal), "revision": record["revision"], "collected_at": record["collected_at"]}


@router.get("/modules/{module}/finance-history")
def module_finance_history(
    module: str,
    days: int = Query(default=30, ge=1, le=90),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, FINANCE_ROLES)
    require_module_access(principal, module)
    today = date_type.fromisoformat(business_today())
    start = (today - timedelta(days=days - 1)).isoformat()
    records = store.summaries_range(module, FINANCE_KIND, start, today.isoformat())
    _audit_financial_access(principal, "finance-history", module)
    return {
        "module": module,
        "from": start,
        "to": today.isoformat(),
        "items": [
            {"date": item["summary_date"], "is_final": bool(item["is_final"]), "revision": item["revision"], "metrics": item["payload"].get("metrics", [])}
            for item in records
        ],
    }


@router.get("/modules/{module}/finance-aggregates")
def module_finance_aggregates(
    module: str,
    period: str = Query(default="week", pattern="^(week|month)$"),
    count: int = Query(default=8, ge=1, le=12),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, FINANCE_ROLES)
    require_module_access(principal, module)
    _audit_financial_access(principal, "finance-aggregates", module)
    today = date_type.fromisoformat(business_today())
    return {"module": module, "period": period, "buckets": aggregate_periods(module, period=period, count=count, today=today, kind=FINANCE_KIND)}


@router.get("/finance/overview")
def finance_overview(
    date: str | None = Query(default=None),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    require_role(principal, FINANCE_ROLES)
    diddigo = store.latest_summary("diddigo", FINANCE_KIND, summary_date=date)
    diddisend = store.latest_summary("diddisend", FINANCE_KIND, summary_date=date)
    diddipay = store.latest_summary("diddipay", DAILY_KIND, summary_date=date)
    resolved_date = date or (diddigo or diddisend or diddipay or {}).get("summary_date")
    _audit_financial_access(principal, "finance-overview")
    return {
        "date": resolved_date,
        "timezone": str(business_timezone()),
        "economics": diddisend["payload"] if diddisend else None,
        "economics_by_module": {
            "diddigo": diddigo["payload"] if diddigo else None,
            "diddisend": diddisend["payload"] if diddisend else None,
        },
        "payments": diddipay["payload"] if diddipay else None,
        "reconciliation": {
            "status": "unavailable",
            "reason": "source_dimensions_missing",
            "blockers": ["diddipay_service_breakdown_missing", "diddigo_wallet_breakdown_missing"],
            "message": "DiddiPay totals are global and DiddiGo does not yet expose its wallet breakdown.",
        },
    }


@router.get("/accounting/daily-export")
def accounting_daily_export(
    date: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$"),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    """Stable, read-only daily payload consumed by Odoo."""
    require_role(principal, FINANCE_ROLES)
    try:
        date_type.fromisoformat(date)
    except ValueError as error:
        raise HTTPException(status_code=422, detail={"error": {"code": "invalid_date", "message": "date must be a valid YYYY-MM-DD date"}}) from error

    business = []
    missing = []
    source_revisions = {}
    final_flags = []
    for module in FINANCE_MODULES:
        record = store.latest_summary(module, FINANCE_KIND, summary_date=date)
        if not record:
            missing.append(f"{module}_finance_summary_missing")
            continue
        source_revisions[module] = int(record["revision"])
        final_flags.append(bool(record["is_final"]))
        payload = record["payload"]
        business.append({
            "module": module,
            "revision": record["revision"],
            "collected_at": record["collected_at"],
            "calculated_at": payload.get("calculated_at"),
            "is_final": bool(record["is_final"]),
            "metrics": payload.get("metrics", []),
            "sources": payload.get("sources", []),
        })

    payment = store.latest_summary("diddipay", ACCOUNTING_KIND, summary_date=date)
    payment_entries = []
    payment_source = None
    if payment:
        source_revisions["diddipay"] = int(payment["revision"])
        final_flags.append(bool(payment["is_final"]))
        payment_entries = payment["payload"].get("entries", [])
        payment_source = {
            "module": "diddipay",
            "revision": payment["revision"],
            "collected_at": payment["collected_at"],
            "calculated_at": payment["payload"].get("calculated_at"),
            "is_final": bool(payment["is_final"]),
            "sources": payment["payload"].get("sources", []),
        }
    else:
        missing.append("diddipay_accounting_summary_missing")

    _audit_financial_access(principal, "accounting-daily-export")
    revision_material = json.dumps({"date": date, "sources": source_revisions, "missing": missing}, sort_keys=True)
    revision = hashlib.sha256(revision_material.encode("utf-8")).hexdigest()[:16]
    return {
        "contract_version": "pilotage.accounting.v1",
        "date": date,
        "timezone": str(business_timezone()),
        "currency": "XOF",
        "is_final": bool(final_flags) and not missing and all(final_flags),
        "revision": revision,
        "source_revisions": source_revisions,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "business_summaries": business,
        "payment_entries": payment_entries,
        "payment_source": payment_source,
        "reconciliation": {
            "status": "complete" if not missing else "partial",
            "blockers": missing,
            "rule": "Business amounts come from each service; processor fees, settlements, payouts and exact partial refunds come from DiddiPay.",
        },
    }


@router.post("/sources/diddipay/collect-accounting")
async def trigger_accounting_collection(
    date: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    require_role(principal, COLLECT_ROLES & FINANCE_ROLES)
    require_module_access(principal, "diddipay")
    return {"result": await collect_accounting_summary(date=date), "request_id": get_request_id()}


@router.post("/sources/{module}/collect-finance")
async def trigger_finance_collection(module: str, principal: PilotagePrincipal = Depends(get_principal)) -> dict:
    _known_module(module)
    require_role(principal, COLLECT_ROLES & FINANCE_ROLES)
    require_module_access(principal, module)
    return {"result": await collect_finance_summary(module), "request_id": get_request_id()}


@router.post("/sources/{module}/backfill-finance")
async def trigger_finance_backfill(
    module: str,
    days: int = Query(default=30, ge=1, le=90),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, COLLECT_ROLES & FINANCE_ROLES)
    require_module_access(principal, module)
    return {"result": await backfill_finance_module(module, days=days), "request_id": get_request_id()}


@router.get("/modules/{module}/breakdown")
def module_breakdown(
    module: str,
    date: str,
    dimension: str = Query(pattern="^[a-z][a-z0-9_]{0,39}$"),
    metric: str = Query(pattern="^[a-z][a-z0-9_]{0,79}$"),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_module_access(principal, module)
    record = store.latest_summary(module, breakdown_kind(dimension, metric), summary_date=date)
    if not record:
        raise HTTPException(status_code=404, detail={"error": {"code": "breakdown_unavailable", "message": "No collected breakdown is available"}})
    return {"breakdown": record["payload"], "revision": record["revision"], "collected_at": record["collected_at"]}


@router.post("/sources/{module}/collect-breakdown")
async def trigger_breakdown_collection(
    module: str,
    date: str,
    dimension: str = Query(pattern="^[a-z][a-z0-9_]{0,39}$"),
    metric: str = Query(pattern="^[a-z][a-z0-9_]{0,79}$"),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, COLLECT_ROLES)
    require_module_access(principal, module)
    return {"result": await collect_breakdown(module, date=date, dimension=dimension, metric=metric), "request_id": get_request_id()}


@router.get("/modules/{module}/breakdown-aggregates")
def module_breakdown_aggregates(
    module: str,
    dimension: str = Query(pattern="^[a-z][a-z0-9_]{0,39}$"),
    metric: str = Query(pattern="^[a-z][a-z0-9_]{0,79}$"),
    period: str = Query(default="week", pattern="^(week|month)$"),
    count: int = Query(default=8, ge=1, le=12),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_module_access(principal, module)
    today = date_type.fromisoformat(business_today())
    return {"module": module, "dimension": dimension, "metric": metric, "period": period, "buckets": aggregate_breakdowns(module, dimension, metric, period=period, count=count, today=today)}


@router.post("/sources/{module}/collect-default-breakdowns")
async def trigger_default_breakdowns(
    module: str,
    date: str,
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, COLLECT_ROLES)
    require_module_access(principal, module)
    return {"result": await collect_default_breakdowns(module, date=date), "request_id": get_request_id()}


@router.post("/sources/{module}/backfill-default-breakdowns")
async def trigger_default_breakdown_backfill(
    module: str,
    days: int = Query(default=5, ge=1, le=90),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, COLLECT_ROLES)
    require_module_access(principal, module)
    return {"result": await backfill_default_breakdowns(module, days=days), "request_id": get_request_id()}


@router.get("/sources")
def sources(principal: PilotagePrincipal = Depends(get_principal)) -> dict:
    states = {(state["module"], state["kind"]): state for state in store.all_source_states()}
    items = []
    for module in enabled_modules():
        if not principal.can_view(module):
            continue
        state = states.get((module, DAILY_KIND))
        freshness = store.compute_freshness(module, DAILY_KIND)
        items.append(
            {
                "module": module,
                "display_name": get_source(module).display_name,
                "kind": DAILY_KIND,
                "freshness": freshness.model_dump(mode="json"),
                "last_attempt_at": state["last_attempt_at"] if state else None,
                "consecutive_failures": state["consecutive_failures"] if state else 0,
                "last_error": {"code": state["last_error_code"], "message": state["last_error_message"]}
                if state and state["last_error_code"]
                else None,
            }
        )
    return {"items": items}


@router.get("/audit/financial-access")
def financial_audit(
    limit: int = Query(default=100, ge=1, le=500),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    require_role(principal, FINANCE_ROLES)
    return {"items": store.financial_access_log(limit)}


@router.post("/sources/{module}/collect")
async def trigger_collection(module: str, principal: PilotagePrincipal = Depends(get_principal)) -> dict:
    _known_module(module)
    require_role(principal, COLLECT_ROLES)
    require_module_access(principal, module)
    result = await collect_daily_summary(module)
    return {"result": result, "request_id": get_request_id()}


@router.post("/sources/{module}/backfill")
async def trigger_backfill(
    module: str,
    days: int = Query(default=30, ge=1, le=90),
    principal: PilotagePrincipal = Depends(get_principal),
) -> dict:
    _known_module(module)
    require_role(principal, COLLECT_ROLES)
    require_module_access(principal, module)
    result = await backfill_module(module, days=days)
    return {"result": result, "request_id": get_request_id()}
