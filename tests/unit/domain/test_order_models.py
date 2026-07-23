from decimal import Decimal

import pytest

from engine.domain import (
    InstrumentId,
    OrderIntent,
    OrderType,
    PositionSnapshot,
    PositionTarget,
    Side,
    TimeInForce,
)


INSTRUMENT = InstrumentId("venue-a", "SPOT", "ETH-USD")


def test_limit_maker_intent_contains_an_exact_price_and_quantity() -> None:
    intent = OrderIntent(
        execution_id="execution-1",
        client_order_id="execution-1-order-1",
        instrument=INSTRUMENT,
        side=Side.BUY,
        quantity="1.25",
        order_type=OrderType.LIMIT,
        price="1999.50",
        post_only=True,
    )

    assert intent.quantity == Decimal("1.25")
    assert intent.price == Decimal("1999.50")
    assert intent.time_in_force is TimeInForce.GTC
    assert intent.signed_quantity == Decimal("1.25")


def test_limit_requires_price_and_market_rejects_price() -> None:
    common = {
        "execution_id": "execution-1",
        "client_order_id": "execution-1-order-1",
        "instrument": INSTRUMENT,
        "side": Side.BUY,
        "quantity": "1",
    }

    with pytest.raises(ValueError, match="LIMIT order requires"):
        OrderIntent(**common, order_type=OrderType.LIMIT)
    with pytest.raises(ValueError, match="MARKET order cannot specify"):
        OrderIntent(**common, order_type=OrderType.MARKET, price="10")


def test_position_target_supports_long_short_and_flat_for_any_instrument() -> None:
    short = PositionTarget("execution-1", INSTRUMENT, quantity="-2", tolerance="0.01")
    observed = PositionSnapshot(INSTRUMENT, quantity="-1.25")

    assert short.remaining_quantity(observed) == Decimal("-0.75")
    assert not short.is_reached_by(observed)
    assert PositionTarget("execution-2", INSTRUMENT, quantity="0").quantity == Decimal("0")


def test_position_target_rejects_snapshot_for_another_instrument() -> None:
    target = PositionTarget("execution-1", INSTRUMENT, quantity="1")
    other = PositionSnapshot(InstrumentId("venue-b", "SPOT", "ETH-USD"))

    with pytest.raises(ValueError, match="different instrument"):
        target.remaining_quantity(other)
