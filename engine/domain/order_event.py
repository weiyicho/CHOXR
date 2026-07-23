"""Normalized events that drive the order state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from ._numbers import as_decimal
from .order import OrderState


class OrderEventKind(str, Enum):
    SUBMIT_REQUESTED = "SUBMIT_REQUESTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    TRADE = "TRADE"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    REQUEST_TIMED_OUT = "REQUEST_TIMED_OUT"
    RECONCILED = "RECONCILED"


@dataclass(frozen=True)
class OrderEvent:
    kind: OrderEventKind
    client_order_id: Optional[str] = None
    event_id: Optional[str] = None
    cumulative_quantity: Optional[Decimal] = None
    average_price: Optional[Decimal] = None
    exchange_order_id: Optional[str] = None
    reconciled_state: Optional[OrderState] = None
    reason: Optional[str] = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.client_order_id is not None:
            object.__setattr__(self, "client_order_id", self.client_order_id.strip())
            if not self.client_order_id:
                raise ValueError("client_order_id cannot be blank")
        if self.event_id is not None:
            object.__setattr__(self, "event_id", self.event_id.strip())
            if not self.event_id:
                raise ValueError("event_id cannot be blank")
        if self.cumulative_quantity is not None:
            object.__setattr__(
                self, "cumulative_quantity", as_decimal(self.cumulative_quantity)
            )
            if self.cumulative_quantity < 0:
                raise ValueError("cumulative_quantity cannot be negative")
        if self.average_price is not None:
            object.__setattr__(self, "average_price", as_decimal(self.average_price))
            if self.average_price < 0:
                raise ValueError("average_price cannot be negative")
