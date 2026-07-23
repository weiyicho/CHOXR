"""Exchange-neutral instrument and market-data value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from ._numbers import ZERO, as_decimal


def _required(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


@dataclass(frozen=True, order=True)
class InstrumentId:
    """Stable identity for any instrument on any venue.

    ``market`` is deliberately a string rather than a closed enum.  A new
    exchange can expose a new market family without requiring a change to the
    engine domain.
    """

    venue: str
    market: str
    symbol: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "venue", _required(self.venue, "venue"))
        object.__setattr__(self, "market", _required(self.market, "market"))
        object.__setattr__(self, "symbol", _required(self.symbol, "symbol"))


@dataclass(frozen=True)
class OrderBookLevel:
    price: Decimal
    quantity: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", as_decimal(self.price))
        object.__setattr__(self, "quantity", as_decimal(self.quantity))
        if self.price <= ZERO:
            raise ValueError("order-book price must be positive")
        if self.quantity < ZERO:
            raise ValueError("order-book quantity cannot be negative")


@dataclass(frozen=True)
class OrderBookSnapshot:
    instrument: InstrumentId
    bids: Tuple[OrderBookLevel, ...]
    asks: Tuple[OrderBookLevel, ...]
    sequence: Optional[int] = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "bids", tuple(self.bids))
        object.__setattr__(self, "asks", tuple(self.asks))
        if self.sequence is not None and self.sequence < 0:
            raise ValueError("order-book sequence cannot be negative")
        if any(left.price < right.price for left, right in zip(self.bids, self.bids[1:])):
            raise ValueError("bids must be ordered from highest to lowest price")
        if any(left.price > right.price for left, right in zip(self.asks, self.asks[1:])):
            raise ValueError("asks must be ordered from lowest to highest price")
        if self.bids and self.asks and self.bids[0].price >= self.asks[0].price:
            raise ValueError("order book is crossed or locked")

    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True)
class SymbolRules:
    """Trading constraints published by a venue for one instrument."""

    instrument: InstrumentId
    base_asset: str
    quote_asset: str
    price_increment: Decimal
    quantity_increment: Decimal
    min_quantity: Decimal = ZERO
    max_quantity: Optional[Decimal] = None
    min_notional: Decimal = ZERO
    max_notional: Optional[Decimal] = None
    market_quantity_increment: Optional[Decimal] = None
    market_min_quantity: Optional[Decimal] = None
    market_max_quantity: Optional[Decimal] = None
    trading_enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_asset", _required(self.base_asset, "base_asset"))
        object.__setattr__(self, "quote_asset", _required(self.quote_asset, "quote_asset"))
        for name in (
            "price_increment",
            "quantity_increment",
            "min_quantity",
            "min_notional",
        ):
            object.__setattr__(self, name, as_decimal(getattr(self, name)))
        for name in (
            "max_quantity",
            "market_quantity_increment",
            "market_min_quantity",
            "market_max_quantity",
            "max_notional",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, as_decimal(value))

        if self.price_increment <= ZERO:
            raise ValueError("price_increment must be positive")
        if self.quantity_increment <= ZERO:
            raise ValueError("quantity_increment must be positive")
        if self.min_quantity < ZERO or self.min_notional < ZERO:
            raise ValueError("minimum trading constraints cannot be negative")
        if self.max_quantity is not None and self.max_quantity < self.min_quantity:
            raise ValueError("max_quantity cannot be less than min_quantity")
        if (
            self.market_quantity_increment is not None
            and self.market_quantity_increment <= ZERO
        ):
            raise ValueError("market_quantity_increment must be positive")
        if self.market_min_quantity is not None and self.market_min_quantity < ZERO:
            raise ValueError("market_min_quantity cannot be negative")
        if (
            self.effective_market_max_quantity is not None
            and self.effective_market_max_quantity
            < self.effective_market_min_quantity
        ):
            raise ValueError(
                "effective market max quantity cannot be less than its minimum"
            )
        if self.max_notional is not None and self.max_notional < self.min_notional:
            raise ValueError("max_notional cannot be less than min_notional")
        if not isinstance(self.trading_enabled, bool):
            raise ValueError("trading_enabled must be a boolean")

    @property
    def tick_size(self) -> Decimal:
        """Common exchange name for :attr:`price_increment`."""

        return self.price_increment

    @property
    def step_size(self) -> Decimal:
        """Common exchange name for :attr:`quantity_increment`."""

        return self.quantity_increment

    @property
    def effective_market_quantity_increment(self) -> Decimal:
        """Market-order increment, falling back to the general increment."""

        return self.market_quantity_increment or self.quantity_increment

    @property
    def effective_market_min_quantity(self) -> Decimal:
        """Market-order minimum, falling back to the general minimum."""

        if self.market_min_quantity is not None:
            return self.market_min_quantity
        return self.min_quantity

    @property
    def effective_market_max_quantity(self) -> Optional[Decimal]:
        """Market-order maximum, falling back to the general maximum."""

        if self.market_max_quantity is not None:
            return self.market_max_quantity
        return self.max_quantity
