"""Funding-rate strategy models.

These models deliberately live outside :mod:`engine`: choosing a Spot asset leg
and an offsetting perpetual leg is a strategy decision, not an order-engine
invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from engine.domain.instrument import InstrumentId


def _decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class FundingOpportunity:
    """A Spot/perpetual pair selected by the funding strategy."""

    spot_instrument: InstrumentId
    perpetual_instrument: InstrumentId
    funding_rate: Decimal
    next_funding_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "funding_rate", _decimal(self.funding_rate))
        if self.spot_instrument.symbol != self.perpetual_instrument.symbol:
            raise ValueError("funding legs must reference the same strategy symbol")
        if self.spot_instrument == self.perpetual_instrument:
            raise ValueError("funding legs must be different instruments")


@dataclass(frozen=True)
class FundingAllocation:
    """Capital and matched base quantity approved for one funding position."""

    available_capital: Decimal
    deployed_capital: Decimal
    spot_notional: Decimal
    futures_margin: Decimal
    futures_notional: Decimal
    reference_price: Decimal
    base_quantity: Decimal
    futures_leverage: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "available_capital",
            "deployed_capital",
            "spot_notional",
            "futures_margin",
            "futures_notional",
            "reference_price",
            "base_quantity",
            "futures_leverage",
        ):
            object.__setattr__(self, field_name, _decimal(getattr(self, field_name)))

        if self.available_capital < 0 or self.deployed_capital < 0:
            raise ValueError("capital cannot be negative")
        if self.deployed_capital > self.available_capital:
            raise ValueError("deployed capital exceeds available capital")
        if self.reference_price <= 0:
            raise ValueError("reference price must be positive")
        if self.futures_leverage <= 0:
            raise ValueError("futures leverage must be positive")
        if self.base_quantity < 0:
            raise ValueError("base quantity cannot be negative")
