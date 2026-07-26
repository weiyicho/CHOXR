"""Application-level guard preventing accidental exchange mutations."""

from __future__ import annotations

from adapters.binance.config import BinanceAccountMode
from adapters.binance.gateways.account_gateway import (
    ClassicPortfolioMarginAccountGateway,
)
from engine.domain.account import AccountSnapshot
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord
from engine.domain.position import PositionSnapshot
from engine.ports.trading_gateway import TradingGateway

from .settings import Settings


class LiveTradingGuard:
    """Allow read-only reconciliation while gating submit and cancel."""

    def __init__(self, delegate: TradingGateway, settings: Settings) -> None:
        self._delegate = delegate
        self._settings = settings

    def submit_order(self, intent: OrderIntent) -> OrderRecord:
        self._settings.require_live_trading()
        return self._delegate.submit_order(intent)

    def get_order(
        self, instrument: InstrumentId, client_order_id: str
    ) -> OrderRecord | None:
        return self._delegate.get_order(instrument, client_order_id)

    def cancel_order(
        self, instrument: InstrumentId, client_order_id: str
    ) -> OrderRecord:
        self._settings.require_live_trading()
        return self._delegate.cancel_order(instrument, client_order_id)

    def list_open_orders(
        self, instrument: InstrumentId | None = None
    ) -> tuple[OrderRecord, ...]:
        return self._delegate.list_open_orders(instrument)


class LiveAccountGuard:
    """Expose account reads while gating account mutations.

    Binance UI Auto Aggregate Balances is the normal collection mechanism for
    this account.  The API command remains available only as an explicitly
    confirmed operational recovery action; it is never part of order execution
    or startup reconciliation. Initial-leverage changes are permitted only
    while live trading is enabled.
    """

    def __init__(
        self,
        delegate: ClassicPortfolioMarginAccountGateway,
        settings: Settings,
    ) -> None:
        self._delegate = delegate
        self._settings = settings

    def verify_configured_mode(
        self,
        configured: BinanceAccountMode,
    ) -> BinanceAccountMode:
        return self._delegate.verify_configured_mode(configured)

    def get_account_snapshot(self) -> AccountSnapshot:
        return self._delegate.get_account_snapshot()

    def get_position_snapshot(self, instrument: InstrumentId) -> PositionSnapshot:
        return self._delegate.get_position_snapshot(instrument)

    def is_one_way_mode(self) -> bool:
        return self._delegate.is_one_way_mode()

    def get_um_symbol_leverage(self, instrument: InstrumentId) -> int:
        return self._delegate.get_um_symbol_leverage(instrument)

    def set_um_symbol_leverage(
        self,
        instrument: InstrumentId,
        leverage: int,
    ) -> int:
        self._settings.require_live_trading()
        return self._delegate.set_um_symbol_leverage(instrument, leverage)

    def list_funding_income(self, **filters: object):
        return self._delegate.list_funding_income(**filters)

    def collect_futures_funds(
        self,
        *,
        confirmed_manual_recovery: bool = False,
    ) -> dict[str, object]:
        self._settings.require_live_trading()
        if not confirmed_manual_recovery:
            raise RuntimeError(
                "fund collection is manual recovery only; pass "
                "confirmed_manual_recovery=True explicitly"
            )
        return self._delegate.collect_futures_funds()
