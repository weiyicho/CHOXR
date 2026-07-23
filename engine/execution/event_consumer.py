"""Async event consumption; WebSocket events drive normal order progress."""

from __future__ import annotations

import asyncio

from engine.ports.order_event_stream import OrderEventStream

from .event_handler import OrderEventHandler


class OrderEventConsumer:
    def __init__(self, stream: OrderEventStream, handler: OrderEventHandler) -> None:
        self._stream = stream
        self._handler = handler

    async def run(self) -> None:
        async for event in self._stream.events():
            # Persistence and per-order synchronization are deliberately
            # synchronous.  Keep them off the event loop so a reconciliation
            # lock or SQLite write cannot stall websocket receives and pings.
            await asyncio.to_thread(self._handler.handle, event)
