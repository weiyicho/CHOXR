"""Persistence ports for durable order lifecycle and event history."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from engine.domain.order import OrderRecord
from engine.domain.order_event import OrderEvent


class OrderRepository(Protocol):
    """Durable order state keyed by the idempotent client order id.

    Implementations must reject saving a different intent under an existing
    ``client_order_id``.
    """

    def get(self, client_order_id: str) -> Optional[OrderRecord]: ...

    def save(self, order: OrderRecord) -> None: ...

    def list_open(
        self,
        execution_id: Optional[str] = None,
    ) -> tuple[OrderRecord, ...]: ...


class OrderEventRepository(Protocol):
    """Append-only normalized event journal used for audit and replay."""

    def append(self, event: OrderEvent) -> None: ...

    def contains(self, event_id: str) -> bool: ...

    def list_for_order(self, client_order_id: str) -> tuple[OrderEvent, ...]: ...


@runtime_checkable
class AtomicOrderPersistence(Protocol):
    """Optional capability for atomically persisting an event and snapshot.

    ``commit`` returns ``True`` when both records were written.  It returns
    ``False`` only when the exact same non-null ``event_id`` was already
    committed; in that case the supplied order snapshot must not be written.
    Reusing an ``event_id`` for different event data is an error.

    Execution services can detect this capability with ``isinstance`` or
    accept it as an optional dependency.  A false result means the caller
    should discard its candidate snapshot and reload the persisted order.
    """

    def commit(self, order: OrderRecord, event: OrderEvent) -> bool: ...
