"""Typed client for the module-owned Pilotage summary routes."""

from __future__ import annotations

import re

import httpx

from app.sources.catalog import PilotageSource, get_source
from app.sources.gateway import SourceGateway

_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


class PilotageSourceClient(SourceGateway):
    def __init__(self, source: PilotageSource | str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        source = get_source(source) if isinstance(source, str) else source
        super().__init__(source, transport=transport)

    async def daily_summary(self, date: str) -> dict:
        if not _DATE_PATTERN.fullmatch(date):
            raise ValueError("date must be YYYY-MM-DD")
        return await self.get(f"{self.source.summary_base()}/daily-summary", params={"date": date})

    async def finance_summary(self, date: str) -> dict:
        if not _DATE_PATTERN.fullmatch(date):
            raise ValueError("date must be YYYY-MM-DD")
        return await self.get(f"{self.source.summary_base()}/finance-summary", params={"date": date})

    async def health_summary(self) -> dict:
        return await self.get(f"{self.source.summary_base()}/health-summary")
