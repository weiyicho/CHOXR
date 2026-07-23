from __future__ import annotations

import asyncio
import threading

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
