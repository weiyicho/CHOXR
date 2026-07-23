from __future__ import annotations

from engine.domain.instrument import (
    InstrumentId,
    OrderBookLevel,
    OrderBookSnapshot,
    SymbolRules,
)

from ..api.spot_api import SpotApi
from ..api.usd_m_api import UsdMApi
from ..parsers.order_books import parse_order_book
from ..parsers.symbol_rules import parse_exchange_info


SPOT_MARKETS = frozenset({"SPOT", "MARGIN", "CROSS_MARGIN"})
UM_MARKETS = frozenset({"USD_M_FUTURES", "USD_M_PERPETUAL", "UM"})


def _market_family(instrument: InstrumentId) -> str:
    if instrument.venue.lower() != "binance":
        raise ValueError(f"Binance gateway cannot serve venue {instrument.venue!r}")
    market = instrument.market.upper()
    if market in SPOT_MARKETS:
        return "SPOT"
    if market in UM_MARKETS:
        return "UM"
    raise ValueError(f"unsupported Binance market: {instrument.market!r}")


class BinanceMarketDataGateway:
    def __init__(self, spot_api: SpotApi, usd_m_api: UsdMApi):
        self._spot_api = spot_api
        self._usd_m_api = usd_m_api

    def get_order_book(
        self,
        instrument: InstrumentId,
        depth: int | None = None,
    ) -> OrderBookSnapshot:
        family = _market_family(instrument)
        requested_depth = depth or 100
        payload = (
            self._spot_api.get_order_book(instrument.symbol, requested_depth)
            if family == "SPOT"
            else self._usd_m_api.get_order_book(instrument.symbol, requested_depth)
        )
        native = parse_order_book(instrument.symbol, payload)
        return OrderBookSnapshot(
            instrument=instrument,
            bids=tuple(OrderBookLevel(level.price, level.quantity) for level in native.bids),
            asks=tuple(OrderBookLevel(level.price, level.quantity) for level in native.asks),
            sequence=native.last_update_id,
        )

    def get_symbol_rules(self, instrument: InstrumentId) -> SymbolRules:
        family = _market_family(instrument)
        payload = (
            self._spot_api.get_exchange_info(instrument.symbol)
            if family == "SPOT"
            else self._usd_m_api.get_exchange_info()
        )
        native = parse_exchange_info(payload, instrument.symbol)
        return SymbolRules(
            instrument=instrument,
            base_asset=native.base_asset,
            quote_asset=native.quote_asset,
            price_increment=native.price_tick,
            quantity_increment=native.quantity_step,
            min_quantity=native.min_quantity,
            max_quantity=native.max_quantity,
            market_quantity_increment=native.market_quantity_step,
            market_min_quantity=native.market_min_quantity,
            market_max_quantity=native.market_max_quantity,
            min_notional=native.min_notional or 0,
            max_notional=native.max_notional,
            trading_enabled=native.status == "TRADING",
        )
