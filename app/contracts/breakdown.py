from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator


class BreakdownItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    value: int | float | str


class PilotageBreakdown(BaseModel):
    """Aggregated dimension with no raw operation or personal identifier."""

    model_config = ConfigDict(extra="ignore")

    contract_version: str = "pilotage.breakdown.v1"
    module: str
    date: date
    timezone: str = "Africa/Abidjan"
    dimension: str
    metric: str
    unit: str
    total: int | float | str
    items: list[BreakdownItem]
    is_final: bool = False
    calculated_at: datetime

    @model_validator(mode="after")
    def items_match_total(self):
        total = Decimal(str(self.total))
        item_total = sum((Decimal(str(item.value)) for item in self.items), Decimal("0"))
        if item_total != total:
            raise ValueError("breakdown items must sum exactly to total")
        if any(not item.key or not item.label for item in self.items):
            raise ValueError("breakdown items need non-empty keys and labels")
        return self
