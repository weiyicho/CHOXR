from __future__ import annotations

from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord
from engine.ports.trading_gateway import TradingGateway

from .margin_trading_gateway import (
    ClassicPortfolioMarginMarginTradingGateway,
)
from .market_data_gateway import _market_family
from .usd_m_trading_gateway import ClassicPortfolioMarginUsdMTradingGateway


class ClassicPortfolioMarginTradingRouter:
    """Expose product-specific Portfolio Margin gateways as one engine port."""

    def __init__(
        self,
        *,
        margin_gateway: TradingGateway,
        usd_m_gateway: TradingGateway,
    ) -> None:
        self._margin_gateway = margin_gateway
        self._usd_m_gateway = usd_m_gateway

    def submit_order(self, intent: OrderIntent) -> OrderRecord:
        return self._gateway_for(intent.instrument).submit_order(intent)

    def get_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> OrderRecord | None:
        return self._gateway_for(instrument).get_order(
            instrument,
            client_order_id,
        )

    def cancel_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> OrderRecord:
        return self._gateway_for(instrument).cancel_order(
            instrument,
            client_order_id,
        )

    def list_open_orders(
        self,
        instrument: InstrumentId | None = None,
    ) -> tuple[OrderRecord, ...]:
        if instrument is not None:
            return self._gateway_for(instrument).list_open_orders(instrument)
        return (
            *self._margin_gateway.list_open_orders(),
            *self._usd_m_gateway.list_open_orders(),
        )

    def _gateway_for(self, instrument: InstrumentId) -> TradingGateway:
        family = _market_family(instrument)
        return self._margin_gateway if family == "SPOT" else self._usd_m_gateway


__all__ = [
    "ClassicPortfolioMarginMarginTradingGateway",
    "ClassicPortfolioMarginTradingRouter",
    "ClassicPortfolioMarginUsdMTradingGateway",
]
