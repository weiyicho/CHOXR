"""Data contracts for turning a strategy budget into an exact order.

The contracts in this module deliberately describe *how* to size and price one
order.  They contain no strategy names and no exchange API details.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.domain.account import AccountSnapshot
from engine.domain.instrument import InstrumentId, OrderBookSnapshot, SymbolRules
from engine.domain.order import OrderIntent, Side


ZERO = Decimal("0")
ONE = Decimal("1")


def _decimal(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class CapitalBudget:
    """Strategy-owned capital request, before account-aware sizing.

    ``reserve`` is kept untouched.  ``max_available_fraction`` then limits how
    much of the remaining available balance may be assigned to this order.
    """

    requested_notional: Decimal
    quote_asset: str
    reserve: Decimal = ZERO
    max_available_fraction: Decimal = ONE

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "requested_notional", _decimal(self.requested_notional)
        )
        object.__setattr__(self, "reserve", _decimal(self.reserve))
        object.__setattr__(
            self, "max_available_fraction", _decimal(self.max_available_fraction)
        )
        if self.requested_notional <= ZERO:
            raise ValueError("requested_notional must be positive")
        if not self.quote_asset.strip():
            raise ValueError("quote_asset is required")
        if self.reserve < ZERO:
            raise ValueError("reserve cannot be negative")
        if not ZERO < self.max_available_fraction <= ONE:
            raise ValueError("max_available_fraction must be in (0, 1]")


@dataclass(frozen=True)
class MakerPriceParameters:
    """Exchange-independent knobs for a post-only maker quote.

    A quote starts at the best price on our side of the book.  It may improve
    by ``improve_ticks`` unconditionally, and by ``pressure_ticks`` when the
    combined OBI/OBIV signal indicates pressure in the order direction.
    """

    improve_ticks: int = 0
    pressure_ticks: int = 1
    imbalance_threshold: Decimal = Decimal("0.10")
    depth_levels: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "imbalance_threshold", _decimal(self.imbalance_threshold)
        )
        if self.improve_ticks < 0:
            raise ValueError("improve_ticks cannot be negative")
        if self.pressure_ticks < 0:
            raise ValueError("pressure_ticks cannot be negative")
        if not ZERO <= self.imbalance_threshold <= ONE:
            raise ValueError("imbalance_threshold must be in [0, 1]")
        if self.depth_levels is not None and self.depth_levels <= 0:
            raise ValueError("depth_levels must be positive")


@dataclass(frozen=True)
class CapitalAllocation:
    requested_notional: Decimal
    available_balance: Decimal
    spendable_balance: Decimal
    approved_notional: Decimal

    @property
    def was_capped(self) -> bool:
        return self.approved_notional < self.requested_notional


@dataclass(frozen=True)
class PriceQuote:
    desired_price: Decimal
    order_book_imbalance: Decimal
    order_book_value_imbalance: Decimal
    combined_imbalance: Decimal
    applied_ticks: int


@dataclass(frozen=True)
class PlanningRequest:
    execution_id: str
    client_order_id: str
    instrument: InstrumentId
    side: Side
    budget: CapitalBudget
    account: AccountSnapshot
    order_book: OrderBookSnapshot
    symbol_rules: SymbolRules
    price_parameters: MakerPriceParameters = MakerPriceParameters()
    reduce_only: bool = False
    reason: str = "planned_order"

    def __post_init__(self) -> None:
        if not self.execution_id.strip():
            raise ValueError("execution_id is required")
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required")
        if self.order_book.instrument != self.instrument:
            raise ValueError("order_book does not match instrument")
        if self.symbol_rules.instrument != self.instrument:
            raise ValueError("symbol_rules do not match instrument")
        if self.account.venue != self.instrument.venue:
            raise ValueError("account venue does not match instrument")
        if self.symbol_rules.quote_asset != self.budget.quote_asset:
            raise ValueError("budget quote_asset does not match symbol rules")


@dataclass(frozen=True)
class ExecutionPlan:
    """Auditable output of planning one exact post-only limit order."""

    request: PlanningRequest
    allocation: CapitalAllocation
    price_quote: PriceQuote
    raw_quantity: Decimal
    normalized_price: Decimal
    normalized_quantity: Decimal
    order_notional: Decimal
    intent: OrderIntent


@dataclass(frozen=True)
class MarketOrderRequest:
    """Exact-quantity request for a generic taker/market order."""

    execution_id: str
    client_order_id: str
    instrument: InstrumentId
    side: Side
    desired_quantity: Decimal
    symbol_rules: SymbolRules
    reduce_only: bool = False
    reason: str = "planned_market_order"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "desired_quantity", _decimal(self.desired_quantity)
        )
        if not self.execution_id.strip():
            raise ValueError("execution_id is required")
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required")
        if self.desired_quantity <= ZERO:
            raise ValueError("desired_quantity must be positive")
        if self.symbol_rules.instrument != self.instrument:
            raise ValueError("symbol_rules do not match instrument")


@dataclass(frozen=True)
class MarketOrderPlan:
    request: MarketOrderRequest
    normalized_quantity: Decimal
    intent: OrderIntent
