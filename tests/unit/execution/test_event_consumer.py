from __future__ import annotations

import asyncio
import threading

from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord, Side
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.execution import OrderEventConsumer


def test_event_consumer_handles_events_off_loop_in_fifo_order() -> None:
    events = (
        OrderEvent(
            kind=OrderEventKind.ACKNOWLEDGED,
            client_order_id="order-1",
        ),
        OrderEvent(
            kind=OrderEventKind.ACKNOWLEDGED,
            client_order_id="order-2",
        ),
    )

    class FakeStream:
        async def events(self):
            for event in events:
                yield event

    class RecordingHandler:
        def __init__(self) -> None:
            self.client_order_ids: list[str] = []
            self.thread_ids: list[int] = []

        def handle(self, event: OrderEvent) -> None:
            assert event.client_order_id is not None
            self.client_order_ids.append(event.client_order_id)
            self.thread_ids.append(threading.get_ident())

    async def scenario() -> None:
        handler = RecordingHandler()
        event_loop_thread = threading.get_ident()

        await OrderEventConsumer(FakeStream(), handler).run()

        assert handler.client_order_ids == ["order-1", "order-2"]
        assert all(thread_id != event_loop_thread for thread_id in handler.thread_ids)

    asyncio.run(scenario())


def test_event_consumer_publishes_only_committed_owned_order_events() -> None:
    owned = OrderEvent(
        kind=OrderEventKind.ACKNOWLEDGED,
        client_order_id="owned-order",
    )
    ignored = OrderEvent(
        kind=OrderEventKind.ACKNOWLEDGED,
        client_order_id="external-order",
    )

    class FakeStream:
        async def events(self):
            yield owned
            yield ignored

    class RecordingHandler:
        def handle(self, event: OrderEvent) -> OrderRecord | None:
            if event.client_order_id != "owned-order":
                return None
            return OrderRecord(
                intent=OrderIntent(
                    execution_id="execution-1",
                    client_order_id="owned-order",
                    instrument=InstrumentId(
                        "binance",
                        "USD_M_PERPETUAL",
                        "BNBUSDT",
                    ),
                    side=Side.SELL,
                    quantity="0.01",
                )
            )

    async def scenario() -> None:
        committed: asyncio.Queue[OrderEvent] = asyncio.Queue()
        await OrderEventConsumer(
            FakeStream(),
            RecordingHandler(),
            committed_event_queue=committed,
        ).run()

        assert committed.qsize() == 1
        assert committed.get_nowait() is owned

    asyncio.run(scenario())
