from decimal import Decimal

import pytest

from engine.domain import (
    InstrumentId,
    InvalidOrderTransition,
    OrderEvent,
    OrderEventKind,
    OrderIntent,
    OrderRecord,
    OrderState,
    OrderStateMachine,
    Side,
)


def make_order(quantity: str = "1") -> OrderRecord:
    return OrderRecord(
        OrderIntent(
            execution_id="execution-1",
            client_order_id="execution-1-order-1",
            instrument=InstrumentId("venue-a", "SPOT", "ETH-USD"),
            side=Side.BUY,
            quantity=quantity,
        )
    )


def test_partial_fill_then_fill_uses_cumulative_quantity_idempotently() -> None:
    machine = OrderStateMachine()
    order = make_order()
    machine.apply(order, OrderEvent(OrderEventKind.SUBMIT_REQUESTED))
    machine.apply(order, OrderEvent(OrderEventKind.ACKNOWLEDGED, exchange_order_id="x-1"))

    partial = OrderEvent(OrderEventKind.TRADE, cumulative_quantity="0.4")
    machine.apply(order, partial)
    machine.apply(order, partial)

    assert order.state is OrderState.PARTIALLY_FILLED
    assert order.cumulative_quantity == Decimal("0.4")
    assert order.leaves_quantity == Decimal("0.6")

    machine.apply(order, OrderEvent(OrderEventKind.TRADE, cumulative_quantity="1"))
    assert order.state is OrderState.FILLED

    machine.apply(order, OrderEvent(OrderEventKind.TRADE, cumulative_quantity="1"))
    assert order.cumulative_quantity == Decimal("1")


def test_timeout_enters_unknown_and_reconciles_by_same_idempotency_key() -> None:
    machine = OrderStateMachine()
    order = make_order()
    machine.apply(order, OrderEvent(OrderEventKind.SUBMIT_REQUESTED))
    machine.apply(order, OrderEvent(OrderEventKind.REQUEST_TIMED_OUT))

    assert order.state is OrderState.UNKNOWN

    machine.apply(
        order,
        OrderEvent(
            OrderEventKind.RECONCILED,
            client_order_id=order.intent.client_order_id,
            reconciled_state=OrderState.FILLED,
            cumulative_quantity="1",
            exchange_order_id="x-1",
        ),
    )
    assert order.state is OrderState.FILLED


def test_filled_reconciliation_requires_full_cumulative_quantity() -> None:
    machine = OrderStateMachine()
    order = make_order()
    machine.apply(order, OrderEvent(OrderEventKind.SUBMIT_REQUESTED))
    machine.apply(order, OrderEvent(OrderEventKind.REQUEST_TIMED_OUT))

    with pytest.raises(InvalidOrderTransition, match="full cumulative"):
        machine.apply(
            order,
            OrderEvent(
                OrderEventKind.RECONCILED,
                reconciled_state=OrderState.FILLED,
                cumulative_quantity="0.4",
            ),
        )


def test_event_for_different_client_order_id_is_rejected() -> None:
    with pytest.raises(InvalidOrderTransition, match="different client_order_id"):
        OrderStateMachine().apply(
            make_order(),
            OrderEvent(
                OrderEventKind.SUBMIT_REQUESTED,
                client_order_id="another-order",
            ),
        )


def test_cancel_event_can_carry_a_last_fill_observed_by_exchange() -> None:
    machine = OrderStateMachine()
    order = make_order()
    machine.apply(order, OrderEvent(OrderEventKind.SUBMIT_REQUESTED))
    machine.apply(order, OrderEvent(OrderEventKind.ACKNOWLEDGED))
    machine.apply(order, OrderEvent(OrderEventKind.CANCEL_REQUESTED))
    machine.apply(
        order,
        OrderEvent(
            OrderEventKind.CANCELED,
            cumulative_quantity="0.2",
            average_price="100",
        ),
    )

    assert order.state is OrderState.CANCELED
    assert order.cumulative_quantity == Decimal("0.2")
    assert order.average_price == Decimal("100")
