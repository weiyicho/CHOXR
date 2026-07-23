from decimal import Decimal

from adapters.persistence import (
    InMemoryOrderRepository,
    SqliteOrderEventRepository,
)
from adapters.simulation import SimulatedTradingGateway
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, Side
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.execution import OrderEventHandler, OrderExecutionService


def make_intent() -> OrderIntent:
    return OrderIntent(
        execution_id="event-test",
        client_order_id="owned-order",
        instrument=InstrumentId("test", "SPOT", "ETHUSDT"),
        side=Side.BUY,
        quantity=Decimal("1"),
    )


def test_duplicate_exchange_event_is_applied_once(tmp_path) -> None:
    gateway = SimulatedTradingGateway()
    events = SqliteOrderEventRepository(tmp_path / "events.sqlite3")
    service = OrderExecutionService(
        gateway,
        InMemoryOrderRepository(),
        event_repository=events,
    )
    service.submit(make_intent())
    event = OrderEvent(
        kind=OrderEventKind.ACKNOWLEDGED,
        client_order_id="owned-order",
        event_id="binance-event-1",
        exchange_order_id="42",
    )

    first = service.handle_event(event)
    second = service.handle_event(event)

    assert second == first
    assert len(
        [item for item in events.list_for_order("owned-order") if item.event_id]
    ) == 1


def test_account_stream_event_for_foreign_order_does_not_crash_consumer() -> None:
    service = OrderExecutionService(
        SimulatedTradingGateway(),
        InMemoryOrderRepository(),
    )
    handler = OrderEventHandler(service)

    result = handler.handle(
        OrderEvent(
            kind=OrderEventKind.ACKNOWLEDGED,
            client_order_id="manual-or-another-bot-order",
            event_id="foreign-event-1",
        )
    )

    assert result is None
