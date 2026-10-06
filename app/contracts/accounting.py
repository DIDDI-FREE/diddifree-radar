from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.common import SourceRef


class AccountingEntry(BaseModel):
    """One authoritative DiddiPay accounting aggregate."""

    model_config = ConfigDict(extra="ignore")

    service: str
    processor: str
    flow_type: str
    status: str
    transactions_count: int = Field(ge=0)
    gross_amount_xof: int
    refund_amount_xof: int
    processor_fees_xof: int
    net_expected_xof: int
    settled_amount_xof: int
    outstanding_amount_xof: int


class AccountingSourceSummary(BaseModel):
    """DiddiPay's source contract, validated before entering Pilotage."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str
    module: str
    date: date
    timezone: str
    currency: str
    is_final: bool = False
    entries: list[AccountingEntry]
    calculated_at: datetime
    sources: list[SourceRef] = Field(default_factory=list)
