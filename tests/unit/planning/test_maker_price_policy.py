from decimal import Decimal

from engine.domain.instrument import (
    InstrumentId,
    OrderBookLevel,
    OrderBookSnapshot,
    SymbolRules,
)
from engine.domain.order import Side
import pytest

from engine.planning import (
    MakerPriceParameters,
    MakerPricePolicy,
    SymbolNormalizationError,
    SymbolNormalizer,
)


INSTRUMENT = InstrumentId("binance", "SPOT", "ETHUSDT")


def level(price: str, quantity: str) -> OrderBookLevel:
    return OrderBookLevel(price, quantity)


def rules(tick: str = "0.05") -> SymbolRules:
    return SymbolRules(
        instrument=INSTRUMENT,
        base_asset="ETH",
        quote_asset="USDT",
        price_increment=tick,
        quantity_increment="0.001",
        min_quantity="0.001",
        min_notional="5",
    )


def book() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        instrument=INSTRUMENT,
        bids=(level("100.00", "8"), level("99.95", "2")),
        asks=(level("100.10", "3"), level("100.15", "2")),
    )


def test_obi_and_obiv_are_decimal_and_use_correct_denominators() -> None:
    bids = (level("1", "8"), level("1", "2"))
    asks = (level("1", "3"), level("1", "2"))

    assert MakerPricePolicy.order_book_imbalance(bids, asks) == Decimal("1") / Decimal("3")
    assert MakerPricePolicy.order_book_value_imbalance(bids, asks) == Decimal("1") / Decimal("3")


def test_positive_pressure_improves_buy_quote_by_configured_ticks() -> None:
    quote = MakerPricePolicy().quote(
        book(),
        Side.BUY,
        rules(),
        MakerPriceParameters(
            improve_ticks=0,
            pressure_ticks=1,
            imbalance_threshold="0.10",
        ),
    )

    assert quote.order_book_imbalance > Decimal("0.10")
    assert quote.applied_ticks == 1
    assert quote.desired_price == Decimal("100.05")


def test_side_aware_normalization_never_crosses_the_spread() -> None:
    normalizer = SymbolNormalizer()
    snapshot = book()
    symbol_rules = rules()

    buy_price = normalizer.normalize_maker_price(
        Decimal("999"), Side.BUY, snapshot, symbol_rules
    )
    sell_price = normalizer.normalize_maker_price(
        Decimal("1"), Side.SELL, snapshot, symbol_rules
    )

    assert buy_price == Decimal("100.05")
    assert buy_price < snapshot.best_ask.price
    assert sell_price == Decimal("100.05")
    assert sell_price > snapshot.best_bid.price


def test_quantity_normalization_supports_non_power_of_ten_steps() -> None:
    special_rules = SymbolRules(
        instrument=INSTRUMENT,
        base_asset="ETH",
        quote_asset="USDT",
        price_increment="0.05",
        quantity_increment="0.005",
        min_quantity="0.005",
        min_notional="1",
    )

    assert SymbolNormalizer().normalize_quantity(
        Decimal("1.019"), special_rules
    ) == Decimal("1.015")


def test_notional_below_exchange_minimum_is_rejected() -> None:
    with pytest.raises(SymbolNormalizationError, match="min_notional"):
        SymbolNormalizer.validate_notional(
            Decimal("100"), Decimal("0.01"), rules()
        )
