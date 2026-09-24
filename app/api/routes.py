from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query

from datetime import date as date_type, timedelta

from app.collector import store
from app.collector.collector import DAILY_KIND, backfill_module, business_timezone, business_today, collect_daily_summary
from app.core.auth import COLLECT_ROLES, PilotagePrincipal, get_principal, require_module_access, require_role
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


def _module_block(module: str) -> dict:
    record = store.latest_summary(module, DAILY_KIND)
    state = store.source_state(module, DAILY_KIND)
    freshness = store.compute_freshness(module, DAILY_KIND, source_updated_at=record["calculated_at"] if record else None)
    block = {
        "module": module,
        "display_name": get_source(module).display_name,
        "summary": record["payload"] if record else None,
        "freshness": freshness.model_dump(mode="json"),
        "collected_at": record["collected_at"] if record else None,
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
    return {
        "contract_version": "pilotage.v1",
        "date": business_today(),
        "timezone": str(business_timezone()),
        "modules": [_module_block(module) for module in modules],
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
    return {"summary": record["payload"], "freshness": freshness.model_dump(mode="json"), "collected_at": record["collected_at"]}


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
    return {
        "module": module,
        "from": from_date,
        "to": today.isoformat(),
        "items": [
            {
                "date": record["summary_date"],
                "is_final": bool(record["is_final"]),
                "metrics": record["payload"].get("metrics", []),
                "collected_at": record["collected_at"],
            }
            for record in records
        ],
    }


@router.get("/sources")
def sources(principal: PilotagePrincipal = Depends(get_principal)) -> dict:
    states = {(state["module"], state["kind"]): state for state in store.all_source_states()}
    items = []
    for module in enabled_modules():
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
