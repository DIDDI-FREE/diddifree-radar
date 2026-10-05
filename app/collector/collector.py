"""Periodic read-model collection from the module-owned Pilotage routes."""

from __future__ import annotations

import asyncio
import os
from datetime import date as date_type, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.contracts.pilotage import PilotageSummary
from app.contracts.breakdown import PilotageBreakdown
from app.collector import store
from app.core.logging import log_json
from app.sources.catalog import enabled_modules
from app.sources.client import PilotageSourceClient
from app.sources.gateway import SourceError
from app.sources.normalization import normalize_daily_summary

DAILY_KIND = "daily"
FINANCE_KIND = "finance"
FINANCE_MODULES = ("diddigo", "diddisend", "diddifood")


def breakdown_kind(dimension: str, metric: str) -> str:
    return f"breakdown:{dimension}:{metric}"


BREAKDOWN_MATRIX = {
    "diddigo": {
        "hour": ("rides_requested", "rides_completed", "completed_fare_total_xof"),
        "payment_method": ("rides_requested", "rides_completed", "completed_fare_total_xof"),
        "service_type": ("rides_requested", "rides_completed", "completed_fare_total_xof"),
        "final_status": ("rides_requested",),
    },
    "diddisend": {
        "hour": ("deliveries_requested", "deliveries_completed", "delivery_value"),
        "payment_method": ("deliveries_requested", "deliveries_completed", "delivery_value"),
        "service_type": ("deliveries_requested", "deliveries_completed", "delivery_value"),
        "final_status": ("deliveries_requested",),
        "pickup_city": ("deliveries_requested", "deliveries_completed", "delivery_value"),
        "dropoff_city": ("deliveries_requested", "deliveries_completed", "delivery_value"),
        "participant_category": ("deliveries_requested", "deliveries_completed", "delivery_value"),
    },
}


def business_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("PILOTAGE_BUSINESS_TIMEZONE", "Africa/Abidjan"))


def business_today() -> str:
    return datetime.now(business_timezone()).date().isoformat()


async def collect_daily_summary(
    module: str,
    *,
    date: str | None = None,
    client: PilotageSourceClient | None = None,
    update_state: bool = True,
) -> dict:
    """Collect one module's daily summary; failures never erase the last value.

    ``update_state=False`` keeps ``pilotage_source_state`` untouched so a
    historical backfill cannot masquerade as live-collection health.
    """
    target_date = date or business_today()
    client = client or PilotageSourceClient(module)
    try:
        payload = normalize_daily_summary(module, await client.daily_summary(target_date))
        summary = PilotageSummary.model_validate(payload)
    except SourceError as error:
        if update_state:
            store.record_failure(module, DAILY_KIND, error.code, str(error))
        log_json({"event": "collect_failed", "module": module, "kind": DAILY_KIND, "date": target_date, "code": error.code})
        return {"module": module, "date": target_date, "status": "failed", "code": error.code}
    except ValidationError as error:
        if update_state:
            store.record_failure(module, DAILY_KIND, "contract_invalid", f"summary does not match pilotage.v1 ({error.error_count()} errors)")
        log_json({"event": "collect_failed", "module": module, "kind": DAILY_KIND, "date": target_date, "code": "contract_invalid"})
        return {"module": module, "date": target_date, "status": "failed", "code": "contract_invalid"}
    store.save_summary(
        module,
        DAILY_KIND,
        summary.date.isoformat(),
        summary.model_dump(mode="json"),
        summary.calculated_at.isoformat(),
        summary.is_final,
    )
    if update_state:
        store.record_success(module, DAILY_KIND)
    log_json({"event": "collect_succeeded", "module": module, "kind": DAILY_KIND, "date": summary.date.isoformat()})
    return {"module": module, "status": "collected", "date": summary.date.isoformat()}


async def backfill_module(module: str, *, days: int, client: PilotageSourceClient | None = None) -> dict:
    """Collect the last ``days`` daily summaries for one module, oldest first.

    Runs outside the live source-state so old dates cannot flip freshness,
    and stops early after repeated failures — a module that rejects one
    historical date will reject them all the same way.
    """
    days = max(1, min(days, 90))
    client = client or PilotageSourceClient(module)
    today = date_type.fromisoformat(business_today())
    collected, failed = 0, 0
    last_code: str | None = None
    for offset in range(days, 0, -1):
        target = (today - timedelta(days=offset)).isoformat()
        result = await collect_daily_summary(module, date=target, client=client, update_state=False)
        if result["status"] == "collected":
            collected += 1
        else:
            failed += 1
            last_code = result.get("code")
            if failed >= 3 and collected == 0:
                break
    log_json({"event": "backfill_finished", "module": module, "days": days, "collected": collected, "failed": failed})
    return {"module": module, "days": days, "collected": collected, "failed": failed, "last_error_code": last_code}


async def collect_finance_summary(module: str, *, date: str | None = None, client: PilotageSourceClient | None = None) -> dict:
    target_date = date or business_today()
    client = client or PilotageSourceClient(module)
    try:
        payload = normalize_daily_summary(module, await client.finance_summary(target_date))
        summary = PilotageSummary.model_validate(payload)
    except SourceError as error:
        store.record_failure(module, FINANCE_KIND, error.code, str(error))
        return {"module": module, "date": target_date, "status": "failed", "code": error.code}
    except ValidationError:
        store.record_failure(module, FINANCE_KIND, "contract_invalid", "finance summary does not match pilotage.v1")
        return {"module": module, "date": target_date, "status": "failed", "code": "contract_invalid"}
    store.save_summary(module, FINANCE_KIND, summary.date.isoformat(), summary.model_dump(mode="json"), summary.calculated_at.isoformat(), summary.is_final)
    store.record_success(module, FINANCE_KIND)
    return {"module": module, "date": summary.date.isoformat(), "status": "collected"}


async def backfill_finance_module(module: str, *, days: int, client: PilotageSourceClient | None = None) -> dict:
    days = max(1, min(days, 90))
    client = client or PilotageSourceClient(module)
    today = date_type.fromisoformat(business_today())
    collected = failed = 0
    last_code = None
    for offset in range(days, 0, -1):
        result = await collect_finance_summary(module, date=(today - timedelta(days=offset)).isoformat(), client=client)
        if result["status"] == "collected":
            collected += 1
        else:
            failed += 1
            last_code = result.get("code")
    return {"module": module, "kind": FINANCE_KIND, "days": days, "collected": collected, "failed": failed, "last_error_code": last_code}


async def collect_breakdown(module: str, *, date: str, dimension: str, metric: str, client: PilotageSourceClient | None = None) -> dict:
    kind = breakdown_kind(dimension, metric)
    client = client or PilotageSourceClient(module)
    try:
        payload = PilotageBreakdown.model_validate(await client.breakdown(date, dimension, metric))
    except SourceError as error:
        store.record_failure(module, kind, error.code, str(error))
        return {"module": module, "date": date, "status": "failed", "code": error.code}
    except ValidationError:
        store.record_failure(module, kind, "contract_invalid", "breakdown does not match pilotage.breakdown.v1")
        return {"module": module, "date": date, "status": "failed", "code": "contract_invalid"}
    store.save_summary(module, kind, payload.date.isoformat(), payload.model_dump(mode="json"), payload.calculated_at.isoformat(), payload.is_final)
    store.record_success(module, kind)
    return {"module": module, "date": payload.date.isoformat(), "status": "collected", "dimension": dimension, "metric": metric}


async def collect_default_breakdowns(module: str, *, date: str, client: PilotageSourceClient | None = None) -> dict:
    client = client or PilotageSourceClient(module)
    pairs = [(dimension, metric) for dimension, metrics in BREAKDOWN_MATRIX.get(module, {}).items() for metric in metrics]
    concurrency = max(1, min(int(os.getenv("PILOTAGE_BREAKDOWN_CONCURRENCY", "5")), 10))
    semaphore = asyncio.Semaphore(concurrency)

    async def one(dimension: str, metric: str):
        async with semaphore:
            return await collect_breakdown(module, date=date, dimension=dimension, metric=metric, client=client)

    results = await asyncio.gather(*(one(dimension, metric) for dimension, metric in pairs))
    return {"module": module, "date": date, "collected": sum(result["status"] == "collected" for result in results), "failed": sum(result["status"] != "collected" for result in results), "results": results}


async def backfill_default_breakdowns(module: str, *, days: int, client: PilotageSourceClient | None = None) -> dict:
    days = max(1, min(days, 90))
    client = client or PilotageSourceClient(module)
    today = date_type.fromisoformat(business_today())
    results = []
    for offset in range(days, 0, -1):
        results.append(await collect_default_breakdowns(module, date=(today - timedelta(days=offset)).isoformat(), client=client))
    return {"module": module, "days": days, "collected": sum(item["collected"] for item in results), "failed": sum(item["failed"] for item in results), "dates": results}


async def collect_all(*, date: str | None = None) -> list[dict]:
    results = await asyncio.gather(
        *(collect_daily_summary(module, date=date) for module in enabled_modules()),
        return_exceptions=True,
    )
    normalized: list[dict] = []
    for module, result in zip(enabled_modules(), results):
        if isinstance(result, BaseException):
            store.record_failure(module, DAILY_KIND, "collector_error", "unexpected collector failure")
            log_json({"event": "collect_failed", "module": module, "kind": DAILY_KIND, "code": "collector_error", "error": str(result)})
            normalized.append({"module": module, "status": "failed", "code": "collector_error"})
        else:
            normalized.append(result)
    return normalized


async def collect_auxiliary(*, date: str | None = None, finance: bool = True, breakdowns: bool = True) -> list[dict]:
    target_date = date or business_today()
    jobs = []
    if finance:
        jobs.extend(collect_finance_summary(module, date=target_date) for module in FINANCE_MODULES if module in enabled_modules())
    if breakdowns:
        jobs.extend(collect_default_breakdowns(module, date=target_date) for module in ("diddigo", "diddisend") if module in enabled_modules())
    if not jobs:
        return []
    results = await asyncio.gather(*jobs, return_exceptions=True)
    normalized = []
    for result in results:
        if isinstance(result, BaseException):
            log_json({"event": "auxiliary_collection_failed", "error_type": type(result).__name__})
            normalized.append({"status": "failed", "code": "collector_error"})
        else:
            normalized.append(result)
    return normalized


async def run_forever() -> None:
    interval = max(float(os.getenv("PILOTAGE_COLLECT_INTERVAL_SECONDS", "30")), 5.0)
    finance_interval = max(float(os.getenv("PILOTAGE_FINANCE_COLLECT_INTERVAL_SECONDS", "60")), interval)
    breakdown_interval = max(float(os.getenv("PILOTAGE_BREAKDOWN_COLLECT_INTERVAL_SECONDS", "60")), interval)
    last_finance = last_breakdown = 0.0
    log_json({"event": "collector_started", "interval_seconds": interval, "modules": enabled_modules()})
    while True:
        await collect_all()
        now = asyncio.get_running_loop().time()
        run_finance = now - last_finance >= finance_interval
        run_breakdowns = now - last_breakdown >= breakdown_interval
        if run_finance or run_breakdowns:
            await collect_auxiliary(finance=run_finance, breakdowns=run_breakdowns)
            if run_finance:
                last_finance = now
            if run_breakdowns:
                last_breakdown = now
        await asyncio.sleep(interval)
