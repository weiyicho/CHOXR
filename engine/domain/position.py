"""Exchange-neutral position observations and desired targets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from ._numbers import ZERO, as_decimal
from .instrument import InstrumentId


@dataclass(frozen=True)
class PositionSnapshot:
    instrument: InstrumentId
    quantity: Decimal = ZERO
    average_entry_price: Optional[Decimal] = None
    mark_price: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    open_order_ids: Tuple[str, ...] = ()
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", as_decimal(self.quantity))
        object.__setattr__(self, "open_order_ids", tuple(self.open_order_ids))
        for name in ("average_entry_price", "mark_price", "unrealized_pnl"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, as_decimal(value))
        if self.average_entry_price is not None and self.average_entry_price < ZERO:
            raise ValueError("average_entry_price cannot be negative")
        if self.mark_price is not None and self.mark_price < ZERO:
            raise ValueError("mark_price cannot be negative")

    @property
    def is_flat(self) -> bool:
        return self.quantity == ZERO


@dataclass(frozen=True)
class PositionTarget:
    """Desired signed quantity for one arbitrary instrument."""

    execution_id: str
    instrument: InstrumentId
    quantity: Decimal
    tolerance: Decimal = ZERO
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_id", self.execution_id.strip())
        object.__setattr__(self, "quantity", as_decimal(self.quantity))
        object.__setattr__(self, "tolerance", as_decimal(self.tolerance))
        if not self.execution_id:
            raise ValueError("execution_id is required")
        if self.tolerance < ZERO:
            raise ValueError("tolerance cannot be negative")

    def remaining_quantity(self, snapshot: PositionSnapshot) -> Decimal:
        if snapshot.instrument != self.instrument:
            raise ValueError("position snapshot belongs to a different instrument")
        difference = self.quantity - snapshot.quantity
        return ZERO if abs(difference) <= self.tolerance else difference

    def is_reached_by(self, snapshot: PositionSnapshot) -> bool:
        return self.remaining_quantity(snapshot) == ZERO
