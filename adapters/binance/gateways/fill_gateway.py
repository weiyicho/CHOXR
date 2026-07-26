"""Read-only Binance fill history adapter."""

from __future__ import annotations

from datetime import datetime, timezone

from engine.domain.instrument import InstrumentId
from engine.domain.order_fill import OrderFill

from ..api.portfolio_margin import PortfolioMarginApi
from ..parsers.orders import parse_order_fills
from .market_data_gateway import _market_family


class ClassicPortfolioMarginFillGateway:
    """Fetch confirmed fills from existing Portfolio Margin trade endpoints."""

    def __init__(self, api: PortfolioMarginApi) -> None:
        self._api = api

    def list_order_fills(
        self,
        instrument: InstrumentId,
        exchange_order_id: str,
    ) -> tuple[OrderFill, ...]:
        family = _market_family(instrument)
        normalized_order_id = int(exchange_order_id)
        if family == "SPOT":
            payloads = self._api.list_margin_fills(
                instrument.symbol,
                order_id=normalized_order_id,
                limit=1000,
            )
            snapshots = parse_order_fills(payloads, "MARGIN")
        else:
            # The USD-M Portfolio Margin trade-history endpoint has no orderId
            # parameter, so filter the bounded symbol history locally.
            payloads = self._api.list_um_fills(
                instrument.symbol,
                limit=1000,
            )
            snapshots = tuple(
                fill
                for fill in parse_order_fills(payloads, "USD_M_FUTURES")
                if fill.exchange_order_id == normalized_order_id
            )

        return tuple(
            OrderFill(
                instrument=instrument,
                trade_id=str(fill.trade_id),
                exchange_order_id=str(fill.exchange_order_id),
                price=fill.price,
                quantity=fill.quantity,
                quote_quantity=fill.quote_quantity,
                commission=fill.commission,
                commission_asset=fill.commission_asset,
                occurred_at=datetime.fromtimestamp(
                    fill.time_ms / 1000,
                    tz=timezone.utc,
                ),
            )
            for fill in sorted(
                snapshots,
                key=lambda candidate: (
                    candidate.time_ms,
                    candidate.trade_id,
                ),
            )
        )
