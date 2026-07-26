from __future__ import annotations

from engine.domain.instrument import InstrumentId

from adapters.binance.gateways.fill_gateway import (
    ClassicPortfolioMarginFillGateway,
)


class FakePortfolioMarginApi:
    def __init__(self) -> None:
        self.margin_calls: list[tuple[str, int, int]] = []

    def list_margin_fills(
        self,
        symbol: str,
        *,
        order_id: int,
        limit: int,
    ):
        self.margin_calls.append((symbol, order_id, limit))
        return [
            {
                "symbol": symbol,
                "id": 55,
                "orderId": order_id,
                "price": "100",
                "qty": "0.2",
                "quoteQty": "20",
                "commission": "0.001",
                "commissionAsset": "bnb",
                "time": 1785052800000,
                "buyer": True,
                "maker": False,
            }
        ]


def test_margin_fill_gateway_maps_existing_trade_history_endpoint() -> None:
    api = FakePortfolioMarginApi()
    gateway = ClassicPortfolioMarginFillGateway(api)

    fills = gateway.list_order_fills(
        InstrumentId("binance", "MARGIN", "BNBUSDT"),
        "77",
    )

    assert api.margin_calls == [("BNBUSDT", 77, 1000)]
    assert len(fills) == 1
    assert fills[0].trade_id == "55"
    assert fills[0].exchange_order_id == "77"
    assert str(fills[0].quantity) == "0.2"
    assert fills[0].commission_asset == "BNB"
