"""Event-driven execution of one order command at a time."""

from __future__ import annotations

from threading import Lock, RLock

from engine.domain.order import OrderIntent, OrderRecord
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.domain.order_state_machine import OrderStateMachine
from engine.ports.repositories import (
    AtomicOrderPersistence,
    OrderEventRepository,
    OrderRepository,
)
from engine.ports.trading_gateway import (
    OrderSubmissionRejected,
    TradingGateway,
    UnknownSubmissionState,
)


class OrderNotFound(LookupError):
    """Raised when an execution command references an unknown local order."""


class ClientOrderIdConflict(ValueError):
    """Raised when a client order ID is reused for a different intent."""


class OrderExecutionService:
    """Persist, submit, reconcile and update generic orders.

    Each method performs one explicit action. Strategy convergence and leg
    sequencing live outside the engine. Unknown request outcomes are queried by
    client order ID and are never blindly resubmitted.
    """

    def __init__(
        self,
        gateway: TradingGateway,
        repository: OrderRepository,
        state_machine: OrderStateMachine | None = None,
        event_repository: OrderEventRepository | None = None,
        atomic_persistence: AtomicOrderPersistence | None = None,
    ) -> None:
        self._gateway = gateway
        self._repository = repository
        self._state_machine = state_machine or OrderStateMachine()
        self._event_repository = event_repository
        self._atomic_persistence = atomic_persistence
        self._order_locks: dict[str, RLock] = {}
        self._order_locks_guard = Lock()

    def submit(self, intent: OrderIntent) -> OrderRecord:
        with self._lock_for(intent.client_order_id):
            return self._submit(intent)

    def _submit(self, intent: OrderIntent) -> OrderRecord:
        existing = self._repository.get(intent.client_order_id)
        if existing is not None:
            if existing.intent != intent:
                raise ClientOrderIdConflict(
                    f"client order ID {intent.client_order_id!r} is already in use"
                )
            return existing

        local = OrderRecord(intent=intent)
        local = self._apply_and_persist(
            local,
            OrderEvent(
                kind=OrderEventKind.SUBMIT_REQUESTED,
                client_order_id=intent.client_order_id,
            ),
        )

        try:
            authoritative = self._gateway.submit_order(intent)
        except OrderSubmissionRejected as exc:
            if exc.client_order_id != intent.client_order_id:
                raise ValueError(
                    "gateway rejected a different client order ID"
                ) from exc
            return self._apply_and_persist(
                local,
                OrderEvent(
                    kind=OrderEventKind.REJECTED,
                    client_order_id=intent.client_order_id,
                    reason=exc.reason,
                ),
            )
        except UnknownSubmissionState:
            local = self._apply_and_persist(
                local,
                OrderEvent(
                    kind=OrderEventKind.REQUEST_TIMED_OUT,
                    client_order_id=intent.client_order_id,
                    reason="exchange submission outcome is unknown",
                ),
            )
            return self.reconcile(intent.client_order_id)

        return self._accept_authoritative(local, authoritative)

    def cancel(self, client_order_id: str) -> OrderRecord:
        with self._lock_for(client_order_id):
            return self._cancel(client_order_id)

    def _cancel(self, client_order_id: str) -> OrderRecord:
        local = self._require_order(client_order_id)
        if local.is_terminal:
            return local

        local = self._apply_and_persist(
            local,
            OrderEvent(
                kind=OrderEventKind.CANCEL_REQUESTED,
                client_order_id=client_order_id,
            ),
        )

        try:
            authoritative = self._gateway.cancel_order(
                local.intent.instrument,
                client_order_id,
            )
        except UnknownSubmissionState:
            local = self._apply_and_persist(
                local,
                OrderEvent(
                    kind=OrderEventKind.REQUEST_TIMED_OUT,
                    client_order_id=client_order_id,
                    reason="exchange cancellation outcome is unknown",
                ),
            )
            return self.reconcile(client_order_id)
        return self._accept_authoritative(local, authoritative)

    def handle_event(self, event: OrderEvent) -> OrderRecord:
        if not event.client_order_id:
            raise ValueError("order event requires a client order ID")
        with self._lock_for(event.client_order_id):
            return self._handle_event(event)

    def _handle_event(self, event: OrderEvent) -> OrderRecord:
        assert event.client_order_id is not None
        if (
            event.event_id
            and self._event_repository is not None
            and self._event_repository.contains(event.event_id)
        ):
            return self._require_order(event.client_order_id)
        local = self._require_order(event.client_order_id)
        if (
            event.kind is OrderEventKind.TRADE
            and event.cumulative_quantity is not None
            and event.cumulative_quantity <= local.cumulative_quantity
        ):
            # A REST reconciliation may observe a newer cumulative fill before
            # an older websocket TRADE leaves the local queue.  Journal the
            # delivery for deduplication/audit, but never move state backwards.
            return self._persist(local, event)
        if (
            local.is_terminal
            and event.kind is OrderEventKind.ACKNOWLEDGED
            and (
                event.exchange_order_id is None
                or local.exchange_order_id is None
                or event.exchange_order_id == local.exchange_order_id
            )
            and (
                event.cumulative_quantity is None
                or event.cumulative_quantity <= local.cumulative_quantity
            )
        ):
            # A MARKET submission can return an authoritative FILLED response
            # before the websocket's earlier NEW acknowledgement leaves the
            # account-stream queue. Journal that stale delivery, but preserve
            # the terminal state and cumulative fill observed from REST.
            return self._persist(local, event)
        return self._apply_and_persist(local, event)

    def reconcile(self, client_order_id: str) -> OrderRecord:
        with self._lock_for(client_order_id):
            return self._reconcile(client_order_id)

    def _reconcile(self, client_order_id: str) -> OrderRecord:
        local = self._require_order(client_order_id)
        authoritative = self._gateway.get_order(
            local.intent.instrument,
            client_order_id,
        )
        if authoritative is None:
            return local
        return self._accept_authoritative(local, authoritative)

    def reconcile_open(self, execution_id: str | None = None) -> tuple[OrderRecord, ...]:
        """Reconcile a finite persisted snapshot after startup or stream gaps."""

        # Do not hold one global lock across N network calls.  Each reconcile
        # acquires only that order's lock, so fills for other orders remain
        # low-latency while a REST query is in flight.
        return tuple(
            self.reconcile(order.intent.client_order_id)
            for order in self._repository.list_open(execution_id)
        )

    def _lock_for(self, client_order_id: str) -> RLock:
        with self._order_locks_guard:
            lock = self._order_locks.get(client_order_id)
            if lock is None:
                lock = RLock()
                self._order_locks[client_order_id] = lock
            return lock

    def _require_order(self, client_order_id: str) -> OrderRecord:
        order = self._repository.get(client_order_id)
        if order is None:
            raise OrderNotFound(client_order_id)
        return order

    def _accept_authoritative(
        self,
        local: OrderRecord,
        authoritative: OrderRecord,
    ) -> OrderRecord:
        if authoritative.intent.client_order_id != local.intent.client_order_id:
            raise ValueError("gateway returned a different client order ID")
        if (
            authoritative.intent.instrument != local.intent.instrument
            or authoritative.intent.side is not local.intent.side
            or authoritative.intent.quantity != local.intent.quantity
            or authoritative.intent.order_type is not local.intent.order_type
        ):
            raise ClientOrderIdConflict(
                "gateway order identity differs from the persisted intent"
            )

        local.rejection_reason = authoritative.rejection_reason
        return self._apply_and_persist(
            local,
            OrderEvent(
                kind=OrderEventKind.RECONCILED,
                client_order_id=local.intent.client_order_id,
                cumulative_quantity=authoritative.cumulative_quantity,
                average_price=authoritative.average_price,
                exchange_order_id=authoritative.exchange_order_id,
                reconciled_state=authoritative.state,
                reason=authoritative.rejection_reason,
            ),
        )

    def _apply_and_persist(
        self,
        order: OrderRecord,
        event: OrderEvent,
    ) -> OrderRecord:
        self._state_machine.apply(order, event)
        return self._persist(order, event)

    def _persist(self, order: OrderRecord, event: OrderEvent) -> OrderRecord:
        if self._atomic_persistence is not None:
            committed = self._atomic_persistence.commit(order, event)
            if not committed:
                return self._require_order(order.intent.client_order_id)
            return order
        if self._event_repository is not None:
            self._event_repository.append(event)
        self._repository.save(order)
        return order
