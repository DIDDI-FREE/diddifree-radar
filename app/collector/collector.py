"""Periodic read-model collection from the module-owned Pilotage routes."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
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


async def collect_daily_summary(module: str, *, date: str | None = None, client: PilotageSourceClient | None = None) -> dict:
    """Collect one module's daily summary; failures never erase the last value."""
    target_date = date or business_today()
    client = client or PilotageSourceClient(module)
    try:
        payload = await client.daily_summary(target_date)
        summary = PilotageSummary.model_validate(payload)
    except SourceError as error:
        store.record_failure(module, DAILY_KIND, error.code, str(error))
        log_json({"event": "collect_failed", "module": module, "kind": DAILY_KIND, "date": target_date, "code": error.code})
        return {"module": module, "status": "failed", "code": error.code}
    except ValidationError as error:
        store.record_failure(module, DAILY_KIND, "contract_invalid", f"summary does not match pilotage.v1 ({error.error_count()} errors)")
        log_json({"event": "collect_failed", "module": module, "kind": DAILY_KIND, "date": target_date, "code": "contract_invalid"})
        return {"module": module, "status": "failed", "code": "contract_invalid"}
    store.save_summary(
        module,
        DAILY_KIND,
        summary.date.isoformat(),
        summary.model_dump(mode="json"),
        summary.calculated_at.isoformat(),
        summary.is_final,
    )
    store.record_success(module, DAILY_KIND)
    log_json({"event": "collect_succeeded", "module": module, "kind": DAILY_KIND, "date": summary.date.isoformat()})
    return {"module": module, "status": "collected", "date": summary.date.isoformat()}


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
