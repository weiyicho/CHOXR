"""Exchange-confirmed trade fills used for REST gap reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ._numbers import as_decimal
from .instrument import InstrumentId


@dataclass(frozen=True)
class OrderFill:
    """One immutable exchange trade belonging to an order."""

    instrument: InstrumentId
    trade_id: str
    exchange_order_id: str
    price: Decimal
    quantity: Decimal
    quote_quantity: Decimal
    commission: Decimal
    commission_asset: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("trade_id", "exchange_order_id", "commission_asset"):
            normalized = str(getattr(self, field_name)).strip()
            if not normalized:
                raise ValueError(f"{field_name} cannot be blank")
            object.__setattr__(self, field_name, normalized)
        for field_name in (
            "price",
            "quantity",
            "quote_quantity",
            "commission",
        ):
            value = as_decimal(getattr(self, field_name))
            if value < 0:
                raise ValueError(f"{field_name} cannot be negative")
            object.__setattr__(self, field_name, value)
        normalized_asset = self.commission_asset.upper()
        object.__setattr__(self, "commission_asset", normalized_asset)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
