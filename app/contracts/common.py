from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ModuleKey = Literal[
    "identity",
    "diddigo",
    "diddipay",
    "diddisend",
    "diddifiles",
    "diddimap",
    "diddifood",
]


class SourceRef(BaseModel):
    """Reference to an authoritative upstream source."""

    model_config = ConfigDict(extra="ignore")

    module: ModuleKey | str
    record_type: str | None = None
    record_id: str | None = None


class Freshness(BaseModel):
    """Freshness metadata for read models and dashboards."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["fresh", "stale", "unavailable"]
    synchronized_at: datetime
    source_updated_at: datetime | None = None
    last_success_at: datetime | None = None


class SafeError(BaseModel):
    """Error shape safe to return to internal clients."""

    model_config = ConfigDict(extra="ignore")

    code: str
    message: str
    details: dict = Field(default_factory=dict)
    request_id: str | None = None
    source_module: ModuleKey | str | None = None


class ServiceHealth(BaseModel):
    """Minimal health contract shared by Backoffice and Pilotage."""

    model_config = ConfigDict(extra="allow")

    module: ModuleKey | str
    status: Literal["healthy", "degraded", "unavailable", "unknown"] = "unknown"
    checked_at: datetime | None = None
    details: dict = Field(default_factory=dict)
