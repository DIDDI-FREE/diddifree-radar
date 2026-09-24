from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.common import Freshness, ModuleKey, SourceRef


class MetricDefinition(BaseModel):
    """Definition of one module-owned Pilotage metric."""

    model_config = ConfigDict(extra="ignore")

    name: str
    label: str
    unit: str
    description: str


class PilotageSummaryManifest(BaseModel):
    """Read-model manifest exposed by a module for Pilotage collection."""

    model_config = ConfigDict(extra="ignore")

    module: ModuleKey | str
    version: str = "pilotage.v1"
    period_type: Literal["day", "week", "month"] = "day"
    timezone: str
    metrics: list[MetricDefinition]


class PilotageMetric(BaseModel):
    """One measured value in a Pilotage summary."""

    model_config = ConfigDict(extra="ignore")

    name: str
    value: int | float | str
    unit: str


class DeepLink(BaseModel):
    """Contextual link from Pilotage into Backoffice or another internal tool."""

    model_config = ConfigDict(extra="ignore")

    label: str
    href: str


class PilotageSummary(BaseModel):
    """Read-only KPI payload consumed by DiddiFree Pilotage.

    ``contract_version`` and ``is_final`` are mandated by the internal
    integration guide; producers that omit them get the safe defaults.
    """

    model_config = ConfigDict(extra="ignore")

    contract_version: str = "pilotage.v1"
    module: ModuleKey | str
    date: date
    timezone: str
    is_final: bool = False
    metrics: list[PilotageMetric]
    calculated_at: datetime
    freshness: Freshness | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    deep_links: list[DeepLink] = Field(default_factory=list)
