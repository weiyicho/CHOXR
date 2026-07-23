from decimal import Decimal

from adapters.persistence import SqliteOrderEventRepository, SqliteOrderRepository
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord, OrderState, Side
from engine.domain.order_event import OrderEvent, OrderEventKind


def make_order() -> OrderRecord:
    return OrderRecord(
        intent=OrderIntent(
            execution_id="exec-sqlite",
            client_order_id="sqlite-order-1",
            instrument=InstrumentId("test", "SPOT", "ETHUSDT"),
            side=Side.BUY,
            quantity=Decimal("1.25"),
        ),
        state=OrderState.PARTIALLY_FILLED,
        cumulative_quantity=Decimal("0.25"),
        average_price=Decimal("2000.5"),
    )


def test_sqlite_order_round_trip_and_open_filter(tmp_path) -> None:
    repository = SqliteOrderRepository(tmp_path / "engine.sqlite3")
    order = make_order()

    repository.save(order)
    restored = repository.get(order.intent.client_order_id)

    assert restored == order
    assert repository.list_open("exec-sqlite") == (order,)

    order.state = OrderState.CANCELED
    repository.save(order)
    assert repository.list_open() == ()


def test_sqlite_event_journal_preserves_order(tmp_path) -> None:
    repository = SqliteOrderEventRepository(tmp_path / "engine.sqlite3")
    events = (
        OrderEvent(
            kind=OrderEventKind.ACKNOWLEDGED,
            client_order_id="sqlite-order-1",
            event_id="event-1",
            exchange_order_id="123",
        ),
        OrderEvent(
            kind=OrderEventKind.TRADE,
            client_order_id="sqlite-order-1",
            event_id="event-2",
            cumulative_quantity=Decimal("0.25"),
            average_price=Decimal("2000.5"),
        ),
    )

    for event in events:
        repository.append(event)

    assert repository.list_for_order("sqlite-order-1") == events
    assert repository.contains("event-1")
    assert not repository.contains("missing-event")
