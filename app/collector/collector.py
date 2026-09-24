"""Periodic read-model collection from the module-owned Pilotage routes."""

from __future__ import annotations

import asyncio
import os
from datetime import date as date_type, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.contracts.pilotage import PilotageSummary
from app.collector import store
from app.core.logging import log_json
from app.sources.catalog import enabled_modules
from app.sources.client import PilotageSourceClient
from app.sources.gateway import SourceError

DAILY_KIND = "daily"


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
        payload = await client.daily_summary(target_date)
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


async def run_forever() -> None:
    interval = max(float(os.getenv("PILOTAGE_COLLECT_INTERVAL_SECONDS", "30")), 5.0)
    log_json({"event": "collector_started", "interval_seconds": interval, "modules": enabled_modules()})
    while True:
        await collect_all()
        await asyncio.sleep(interval)
