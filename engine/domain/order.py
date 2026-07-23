"""Exchange-neutral order intent and observed order state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from ._numbers import ZERO, as_decimal
from .instrument import InstrumentId


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

    @property
    def signed_multiplier(self) -> Decimal:
        return Decimal("1") if self is Side.BUY else Decimal("-1")


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class OrderState(str, Enum):
    CREATED = "CREATED"
    SUBMITTING = "SUBMITTING"
    UNKNOWN = "UNKNOWN"
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


TERMINAL_ORDER_STATES = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    }
)


@dataclass(frozen=True)
class OrderIntent:
    """An exact, validated instruction ready for an execution gateway.

    ``client_order_id`` is the engine's idempotency key.  A repository or
    gateway must reject attempts to reuse it with a different intent.
    """

    execution_id: str
    client_order_id: str
    instrument: InstrumentId
    side: Side
    quantity: Decimal
    order_type: OrderType = OrderType.MARKET
    price: Optional[Decimal] = None
    time_in_force: Optional[TimeInForce] = None
    reduce_only: bool = False
    post_only: bool = False
    reason: str = "unspecified"

    def __post_init__(self) -> None:
        object.__setattr__(self, "execution_id", self.execution_id.strip())
        object.__setattr__(self, "client_order_id", self.client_order_id.strip())
        object.__setattr__(self, "quantity", as_decimal(self.quantity))
        object.__setattr__(self, "reason", self.reason.strip())
        if self.price is not None:
            object.__setattr__(self, "price", as_decimal(self.price))

        if not self.execution_id:
            raise ValueError("execution_id is required")
        if not self.client_order_id:
            raise ValueError("client_order_id is required")
        if self.quantity <= ZERO:
            raise ValueError("order quantity must be positive")
        if self.order_type is OrderType.LIMIT:
            if self.price is None or self.price <= ZERO:
                raise ValueError("LIMIT order requires a positive price")
            if self.time_in_force is None:
                object.__setattr__(self, "time_in_force", TimeInForce.GTC)
        elif self.price is not None:
            raise ValueError("MARKET order cannot specify a price")
        elif self.time_in_force is not None:
            raise ValueError("MARKET order cannot specify time_in_force")
        if self.post_only and self.order_type is not OrderType.LIMIT:
            raise ValueError("post_only requires a LIMIT order")
        if self.post_only and self.time_in_force is not TimeInForce.GTC:
            raise ValueError("post_only requires GTC time_in_force")

    @property
    def signed_quantity(self) -> Decimal:
        return self.side.signed_multiplier * self.quantity


@dataclass
class OrderRecord:
    """Engine-owned state for one exchange order."""

    intent: OrderIntent
    state: OrderState = OrderState.CREATED
    exchange_order_id: Optional[str] = None
    cumulative_quantity: Decimal = ZERO
    average_price: Optional[Decimal] = None
    rejection_reason: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.cumulative_quantity = as_decimal(self.cumulative_quantity)
        if self.average_price is not None:
            self.average_price = as_decimal(self.average_price)
        if self.cumulative_quantity < ZERO:
            raise ValueError("cumulative_quantity cannot be negative")
        if self.cumulative_quantity > self.intent.quantity:
            raise ValueError("cumulative_quantity exceeds requested quantity")

    @property
    def leaves_quantity(self) -> Decimal:
        return max(ZERO, self.intent.quantity - self.cumulative_quantity)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_ORDER_STATES
