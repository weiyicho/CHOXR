"""Route exchange order events into the execution service."""

from __future__ import annotations

from engine.domain.order import OrderRecord
from engine.domain.order_event import OrderEvent

from .order_service import OrderExecutionService, OrderNotFound


class OrderEventHandler:
    def __init__(self, service: OrderExecutionService) -> None:
        self._service = service

    def handle(self, event: OrderEvent) -> OrderRecord | None:
        """Ignore account-wide events for orders this engine does not own."""

        try:
            return self._service.handle_event(event)
        except OrderNotFound:
            return None
