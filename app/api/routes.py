from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from datetime import date as date_type, timedelta

from app.collector import store
from app.collector.collector import DAILY_KIND, FINANCE_KIND, backfill_default_breakdowns, backfill_finance_module, backfill_module, breakdown_kind, business_timezone, business_today, collect_breakdown, collect_daily_summary, collect_default_breakdowns, collect_finance_summary
from app.collector.rollups import aggregate_periods
from app.collector.breakdown_rollups import aggregate_breakdowns
from app.core.auth import COLLECT_ROLES, FINANCE_ROLES, PilotagePrincipal, get_principal, require_module_access, require_role
from app.core.request_context import get_request_id
from app.sources.catalog import PILOTAGE_SOURCES, enabled_modules, get_source

router = APIRouter(prefix="/pilotage", tags=["pilotage"])

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


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
    return visible


def _audit_financial_access(principal: PilotagePrincipal, resource: str, module: str | None = None) -> None:
    if principal.role in FINANCE_ROLES:
        store.record_financial_access(principal.user_id, principal.role, resource, module)


def _module_block(module: str, principal: PilotagePrincipal) -> dict:
    record = store.latest_summary(module, DAILY_KIND)
    state = store.source_state(module, DAILY_KIND)
    freshness = store.compute_freshness(module, DAILY_KIND, source_updated_at=record["calculated_at"] if record else None)
    block = {
        "module": module,
        "display_name": get_source(module).display_name,
        "summary": _visible_payload(record["payload"], principal) if record else None,
        "freshness": freshness.model_dump(mode="json"),
        "collected_at": record["collected_at"] if record else None,
        "revision": record["revision"] if record else None,
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
    return {"summary": record["payload"], "revision": record["revision"], "collected_at": record["collected_at"]}


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
