"""Async event consumption; WebSocket events drive normal order progress."""

from __future__ import annotations

import asyncio

from engine.domain.order_event import OrderEvent
from engine.ports.order_event_stream import OrderEventStream

from .event_handler import OrderEventHandler


class OrderEventConsumer:
    def __init__(
        self,
        stream: OrderEventStream,
        handler: OrderEventHandler,
        *,
        committed_event_queue: asyncio.Queue[OrderEvent] | None = None,
    ) -> None:
        self._stream = stream
        self._handler = handler
        self._committed_event_queue = committed_event_queue

    async def run(self) -> None:
        async for event in self._stream.events():
            # Persistence and per-order synchronization are deliberately
            # synchronous.  Keep them off the event loop so a reconciliation
            # lock or SQLite write cannot stall websocket receives and pings.
            committed_order = await asyncio.to_thread(self._handler.handle, event)
            if (
                committed_order is not None
                and self._committed_event_queue is not None
            ):
                # Strategy workers receive only events whose generic order state
                # was accepted and durably persisted. The queue contains the
                # immutable event rather than a mutable OrderRecord; consumers
                # reload the authoritative local snapshot by client order ID.
                self._committed_event_queue.put_nowait(event)
