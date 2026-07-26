from decimal import Decimal

import pytest

from engine.domain.order_event import OrderEvent, OrderEventKind


def test_trade_metadata_is_optional_and_normalized() -> None:
    event = OrderEvent(
        kind=OrderEventKind.TRADE,
        last_executed_quantity="0.025",
        last_executed_price="3200.50",
        trade_id=9,
        commission="0.000025",
        commission_asset=" ETH ",
    )

    assert event.last_executed_quantity == Decimal("0.025")
    assert event.last_executed_price == Decimal("3200.50")
    assert event.trade_id == "9"
    assert event.commission == Decimal("0.000025")
    assert event.commission_asset == "ETH"

    empty_event = OrderEvent(kind=OrderEventKind.ACKNOWLEDGED)
    assert empty_event.last_executed_quantity is None
    assert empty_event.last_executed_price is None
    assert empty_event.trade_id is None
    assert empty_event.commission is None
    assert empty_event.commission_asset is None


@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        ("last_executed_quantity", "last_executed_quantity cannot be negative"),
        ("last_executed_price", "last_executed_price cannot be negative"),
        ("commission", "commission cannot be negative"),
    ],
)
def test_trade_decimal_metadata_rejects_negative_values(
    field_name: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        OrderEvent(
            kind=OrderEventKind.TRADE,
            **{field_name: "-0.01"},
        )
