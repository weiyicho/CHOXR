"""Explicit REST reconciliation entry points."""

from __future__ import annotations

from engine.domain.order import OrderRecord

from .order_service import OrderExecutionService


class OrderReconciler:
    def __init__(self, service: OrderExecutionService) -> None:
        self._service = service

    def reconcile_order(self, client_order_id: str) -> OrderRecord:
        return self._service.reconcile(client_order_id)

    def reconcile_after_startup(
        self, execution_id: str | None = None
    ) -> tuple[OrderRecord, ...]:
        return self._service.reconcile_open(execution_id)
