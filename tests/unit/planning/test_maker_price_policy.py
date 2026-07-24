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


def test_microprice_weights_opposite_quote_by_best_queue_size() -> None:
    snapshot = OrderBookSnapshot(
        instrument=INSTRUMENT,
        bids=(level("99", "3"),),
        asks=(level("101", "1"),),
    )

    assert MakerPricePolicy.microprice(snapshot) == Decimal("100.5")


def test_microprice_falls_back_to_midpoint_when_best_queues_are_empty() -> None:
    snapshot = OrderBookSnapshot(
        instrument=INSTRUMENT,
        bids=(level("99", "0"),),
        asks=(level("101", "0"),),
    )

    assert MakerPricePolicy.microprice(snapshot) == Decimal("100")


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
    assert quote.microprice > Decimal("100.05")


def test_pressure_strength_scales_additional_ticks_continuously() -> None:
    assert MakerPricePolicy.pressure_ratio(
        Decimal("0.10"), Decimal("0.10")
    ) == Decimal("0")
    assert MakerPricePolicy.pressure_ratio(
        Decimal("0.55"), Decimal("0.10")
    ) == Decimal("0.5")
    assert MakerPricePolicy.scale_pressure_ticks(4, Decimal("0.5")) == 2


def test_depth_decay_makes_near_touch_liquidity_more_important() -> None:
    bids = (level("100", "8"), level("99", "1"))
    asks = (level("101", "2"), level("102", "20"))

    unweighted = MakerPricePolicy.order_book_imbalance(bids, asks)
    near_weighted = MakerPricePolicy.order_book_imbalance(
        bids,
        asks,
        depth_decay=Decimal("0.1"),
    )

    assert unweighted < 0
    assert near_weighted > 0


def test_imbalance_weights_are_normalized() -> None:
    combined = MakerPricePolicy.combine_imbalances(
        Decimal("0.8"),
        Decimal("-0.2"),
        quantity_weight=Decimal("3"),
        value_weight=Decimal("1"),
    )

    assert combined == Decimal("0.55")


def test_quote_caps_improvement_at_last_non_crossing_tick() -> None:
    quote = MakerPricePolicy().quote(
        book(),
        Side.BUY,
        rules(),
        MakerPriceParameters(
            improve_ticks=50,
            pressure_ticks=50,
            imbalance_threshold="0",
        ),
    )

    assert quote.available_improve_ticks == 1
    assert quote.applied_ticks == 1
    assert quote.desired_price == Decimal("100.05")


def test_quote_does_not_improve_past_microprice() -> None:
    snapshot = OrderBookSnapshot(
        instrument=INSTRUMENT,
        bids=(level("100.0", "1"),),
        asks=(level("100.4", "3"),),
    )

    quote = MakerPricePolicy().quote(
        snapshot,
        Side.BUY,
        rules(tick="0.1"),
        MakerPriceParameters(improve_ticks=50),
    )

    assert quote.microprice == Decimal("100.1")
    assert quote.available_improve_ticks == 3
    assert quote.fair_value_improve_ticks == 1
    assert quote.applied_ticks == 1
    assert quote.desired_price == Decimal("100.1")


def test_sell_uses_negative_imbalance_as_directional_pressure() -> None:
    sell_pressure_book = OrderBookSnapshot(
        instrument=INSTRUMENT,
        bids=(level("100.00", "1"),),
        asks=(level("100.10", "9"),),
    )

    quote = MakerPricePolicy().quote(
        sell_pressure_book,
        Side.SELL,
        rules(),
        MakerPriceParameters(
            pressure_ticks=1,
            imbalance_threshold="0.10",
        ),
    )

    assert quote.combined_imbalance < Decimal("-0.10")
    assert quote.directional_pressure > Decimal("0.10")
    assert quote.applied_ticks == 1
    assert quote.desired_price == Decimal("100.05")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"depth_decay": "0"}, "depth_decay"),
        ({"quantity_imbalance_weight": "-1"}, "quantity_imbalance_weight"),
        (
            {
                "quantity_imbalance_weight": "0",
                "value_imbalance_weight": "0",
            },
            "at least one imbalance weight",
        ),
    ],
)
def test_invalid_mathematical_parameters_fail_fast(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        MakerPriceParameters(**kwargs)


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
