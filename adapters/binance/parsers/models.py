"""Exchange-facing snapshots before the final engine-domain mapping."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PriceLevel:
    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    symbol: str
    last_update_id: int
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]
    event_time_ms: int | None = None
    transaction_time_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SymbolRules:
    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    price_tick: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    min_notional: Decimal | None
    max_notional: Decimal | None = None
    market_quantity_step: Decimal | None = None
    market_min_quantity: Decimal | None = None
    market_max_quantity: Decimal | None = None


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    market: str
    symbol: str
    exchange_order_id: int
    client_order_id: str
    status: str
    side: str
    order_type: str
    original_quantity: Decimal
    executed_quantity: Decimal
    cumulative_quote_quantity: Decimal
    price: Decimal
    average_price: Decimal | None
    reduce_only: bool = False
    position_side: str | None = None
    update_time_ms: int | None = None

    @property
    def leaves_quantity(self) -> Decimal:
        return max(ZERO, self.original_quantity - self.executed_quantity)


@dataclass(frozen=True, slots=True)
class FillSnapshot:
    market: str
    symbol: str
    trade_id: int
    exchange_order_id: int
    price: Decimal
    quantity: Decimal
    quote_quantity: Decimal
    commission: Decimal
    commission_asset: str
    realized_pnl: Decimal | None
    time_ms: int
    buyer: bool | None = None
    maker: bool | None = None


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    asset: str
    total_wallet_balance: Decimal
    cross_margin_free: Decimal
    cross_margin_locked: Decimal
    cross_margin_borrowed: Decimal
    cross_margin_interest: Decimal
    um_wallet_balance: Decimal
    um_unrealized_pnl: Decimal
    update_time_ms: int | None = None


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    account_equity: Decimal
    actual_equity: Decimal
    available_balance: Decimal
    initial_margin: Decimal
    maintenance_margin: Decimal
    uni_mmr: Decimal
    account_status: str | None = None


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: str
    quantity: Decimal
    position_side: str
    entry_price: Decimal
    mark_price: Decimal
    notional: Decimal
    unrealized_pnl: Decimal
    liquidation_price: Decimal | None
    leverage: int | None
    update_time_ms: int | None = None


@dataclass(frozen=True, slots=True)
class FundingIncomeSnapshot:
    symbol: str
    asset: str
    income_type: str
    income: Decimal
    time_ms: int
    transaction_id: str | None
    trade_id: str | None
    info: str | None = None


@dataclass(frozen=True, slots=True)
class OrderEventSnapshot:
    market: str
    event_type: str
    event_time_ms: int
    transaction_time_ms: int | None
    symbol: str
    client_order_id: str
    original_client_order_id: str | None
    exchange_order_id: int
    side: str
    order_type: str
    execution_type: str
    status: str
    original_quantity: Decimal
    cumulative_quantity: Decimal
    average_price: Decimal | None
    reject_reason: str | None
    last_executed_quantity: Decimal | None = None
    last_executed_price: Decimal | None = None
    trade_id: int | None = None
    commission: Decimal | None = None
    commission_asset: str | None = None
    reduce_only: bool = False
    position_side: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "last_executed_quantity",
            "last_executed_price",
            "commission",
        ):
            value = getattr(self, field_name)
            if value is None:
                continue
            decimal_value = Decimal(str(value))
            object.__setattr__(self, field_name, decimal_value)
            if decimal_value < ZERO:
                raise ValueError(f"{field_name} cannot be negative")

        if self.trade_id is not None and self.trade_id < 0:
            raise ValueError("trade_id cannot be negative")
        if self.commission_asset is not None:
            normalized_asset = self.commission_asset.strip()
            object.__setattr__(
                self,
                "commission_asset",
                normalized_asset or None,
            )
