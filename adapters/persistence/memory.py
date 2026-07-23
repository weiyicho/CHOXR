"""Deterministic order repository for unit tests and offline simulation."""

from __future__ import annotations

from copy import deepcopy

from engine.domain.order import OrderRecord


class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, OrderRecord] = {}

    def get(self, client_order_id: str) -> OrderRecord | None:
        order = self._orders.get(client_order_id)
        return deepcopy(order) if order is not None else None

    def save(self, order: OrderRecord) -> None:
        existing = self._orders.get(order.intent.client_order_id)
        if existing is not None and existing.intent != order.intent:
            raise ValueError("client order ID is already bound to another intent")
        self._orders[order.intent.client_order_id] = deepcopy(order)

    def list_open(self, execution_id: str | None = None) -> tuple[OrderRecord, ...]:
        return tuple(
            deepcopy(order)
            for order in self._orders.values()
            if not order.is_terminal
            and (execution_id is None or order.intent.execution_id == execution_id)
        )
