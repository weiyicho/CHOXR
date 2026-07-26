import threading
from decimal import Decimal

from adapters.persistence import (
    InMemoryOrderRepository,
    SqliteAtomicOrderPersistence,
    SqliteOrderEventRepository,
    SqliteOrderRepository,
)
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord, OrderState, Side
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.execution import OrderExecutionService
from engine.ports.trading_gateway import (
    OrderSubmissionRejected,
    UnknownSubmissionState,
)


INSTRUMENT = InstrumentId("test", "SPOT", "ETHUSDT")


def make_intent(client_order_id: str = "exec-1-order-1") -> OrderIntent:
    return OrderIntent(
        execution_id="exec-1",
        client_order_id=client_order_id,
        instrument=INSTRUMENT,
        side=Side.BUY,
        quantity=Decimal("1"),
    )


class StubGateway:
    def __init__(
        self,
        *,
        timeout: bool = False,
        reject: bool = False,
        cancel_timeout: bool = False,
    ) -> None:
        self.timeout = timeout
        self.reject = reject
        self.cancel_timeout = cancel_timeout
        self.submit_calls = 0
        self.cancel_calls = 0
        self.orders: dict[str, OrderRecord] = {}

    def submit_order(self, intent: OrderIntent) -> OrderRecord:
        self.submit_calls += 1
        if self.timeout:
            raise UnknownSubmissionState(intent.client_order_id)
        if self.reject:
            raise OrderSubmissionRejected(
                intent.client_order_id,
                "[-2015] Invalid API-key, IP, or permissions for action",
            )
        order = OrderRecord(intent=intent, state=OrderState.NEW)
        self.orders[intent.client_order_id] = order
        return order

    def get_order(
        self, instrument: InstrumentId, client_order_id: str
    ) -> OrderRecord | None:
        assert instrument == INSTRUMENT
        return self.orders.get(client_order_id)

    def cancel_order(
        self, instrument: InstrumentId, client_order_id: str
    ) -> OrderRecord:
        self.cancel_calls += 1
        if self.cancel_timeout:
            raise UnknownSubmissionState(client_order_id)
        order = self.orders[client_order_id]
        order.state = OrderState.CANCELED
        return order

    def list_open_orders(
        self, instrument: InstrumentId | None = None
    ) -> tuple[OrderRecord, ...]:
        return tuple(order for order in self.orders.values() if not order.is_terminal)


class ImmediateFillGateway(StubGateway):
    def submit_order(self, intent: OrderIntent) -> OrderRecord:
        order = super().submit_order(intent)
        order.state = OrderState.FILLED
        order.exchange_order_id = "exchange-order-1"
        order.cumulative_quantity = intent.quantity
        order.average_price = Decimal("123.45")
        return order


def test_submit_persists_authoritative_new_order() -> None:
    gateway = StubGateway()
    repository = InMemoryOrderRepository()
    service = OrderExecutionService(gateway, repository)

    order = service.submit(make_intent())

    assert order.state is OrderState.NEW
    assert gateway.submit_calls == 1
    assert repository.get(order.intent.client_order_id).state is OrderState.NEW


def test_unknown_submission_is_not_blindly_resent() -> None:
    gateway = StubGateway(timeout=True)
    repository = InMemoryOrderRepository()
    service = OrderExecutionService(gateway, repository)
    intent = make_intent()

    first = service.submit(intent)
    second = service.submit(intent)

    assert first.state is OrderState.UNKNOWN
    assert second.state is OrderState.UNKNOWN
    assert gateway.submit_calls == 1


def test_definitive_submission_rejection_is_terminal_and_not_resent() -> None:
    gateway = StubGateway(reject=True)
    repository = InMemoryOrderRepository()
    events = RecordingEventRepository()
    service = OrderExecutionService(
        gateway,
        repository,
        event_repository=events,
    )
    intent = make_intent()

    first = service.submit(intent)
    second = service.submit(intent)

    assert first.state is OrderState.REJECTED
    assert first.rejection_reason == (
        "[-2015] Invalid API-key, IP, or permissions for action"
    )
    assert second == first
    assert gateway.submit_calls == 1
    assert [event.kind for event in events.events] == [
        OrderEventKind.SUBMIT_REQUESTED,
        OrderEventKind.REJECTED,
    ]
    persisted = repository.get(intent.client_order_id)
    assert persisted is not None
    assert persisted.state is OrderState.REJECTED
    assert persisted.rejection_reason == first.rejection_reason


def test_definitive_submission_rejection_is_atomic_in_sqlite(tmp_path) -> None:
    database = tmp_path / "rejected-order.sqlite3"
    gateway = StubGateway(reject=True)
    repository = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    service = OrderExecutionService(
        gateway,
        repository,
        event_repository=events,
        atomic_persistence=SqliteAtomicOrderPersistence(database),
    )

    rejected = service.submit(make_intent())

    persisted = repository.get(rejected.intent.client_order_id)
    assert persisted is not None
    assert persisted.state is OrderState.REJECTED
    assert persisted.rejection_reason == rejected.rejection_reason
    assert [event.kind for event in events.list_for_order(
        rejected.intent.client_order_id
    )] == [
        OrderEventKind.SUBMIT_REQUESTED,
        OrderEventKind.REJECTED,
    ]


def test_websocket_trade_event_advances_the_persisted_order() -> None:
    gateway = StubGateway()
    repository = InMemoryOrderRepository()
    service = OrderExecutionService(gateway, repository)
    service.submit(make_intent())

    order = service.handle_event(
        OrderEvent(
            kind=OrderEventKind.TRADE,
            client_order_id="exec-1-order-1",
            cumulative_quantity=Decimal("0.4"),
            average_price=Decimal("2000"),
        )
    )

    assert order.state is OrderState.PARTIALLY_FILLED
    assert order.cumulative_quantity == Decimal("0.4")
    assert repository.get("exec-1-order-1").cumulative_quantity == Decimal("0.4")


def test_unknown_cancel_outcome_reconciles_without_repeating_cancel() -> None:
    gateway = StubGateway(cancel_timeout=True)
    repository = InMemoryOrderRepository()
    service = OrderExecutionService(gateway, repository)
    service.submit(make_intent())

    order = service.cancel("exec-1-order-1")

    assert order.state is OrderState.NEW
    assert gateway.cancel_calls == 1


class BlockingQueryGateway(StubGateway):
    def __init__(self, blocked_order_id: str) -> None:
        super().__init__()
        self.blocked_order_id = blocked_order_id
        self.query_started = threading.Event()
        self.release_query = threading.Event()

    def get_order(
        self, instrument: InstrumentId, client_order_id: str
    ) -> OrderRecord | None:
        if client_order_id == self.blocked_order_id:
            self.query_started.set()
            if not self.release_query.wait(timeout=1):
                raise TimeoutError("test did not release the REST query")
        return super().get_order(instrument, client_order_id)


def test_same_order_event_waits_for_inflight_reconciliation() -> None:
    gateway = BlockingQueryGateway("exec-1-order-1")
    repository = InMemoryOrderRepository()
    service = OrderExecutionService(gateway, repository)
    service.submit(make_intent())
    event_attempted = threading.Event()
    event_done = threading.Event()

    reconcile_thread = threading.Thread(
        target=service.reconcile,
        args=("exec-1-order-1",),
    )

    def handle_fill() -> None:
        event_attempted.set()
        service.handle_event(
            OrderEvent(
                kind=OrderEventKind.TRADE,
                client_order_id="exec-1-order-1",
                cumulative_quantity=Decimal("0.4"),
            )
        )
        event_done.set()

    event_thread = threading.Thread(target=handle_fill)
    reconcile_thread.start()
    assert gateway.query_started.wait(timeout=1)
    event_thread.start()
    assert event_attempted.wait(timeout=1)
    assert not event_done.wait(timeout=0.05)

    gateway.release_query.set()
    reconcile_thread.join(timeout=1)
    event_thread.join(timeout=1)

    assert not reconcile_thread.is_alive()
    assert not event_thread.is_alive()
    persisted = repository.get("exec-1-order-1")
    assert persisted is not None
    assert persisted.state is OrderState.PARTIALLY_FILLED
    assert persisted.cumulative_quantity == Decimal("0.4")


def test_blocked_reconciliation_does_not_delay_a_different_order() -> None:
    gateway = BlockingQueryGateway("exec-1-order-1")
    repository = InMemoryOrderRepository()
    service = OrderExecutionService(gateway, repository)
    service.submit(make_intent("exec-1-order-1"))
    service.submit(make_intent("exec-1-order-2"))

    reconcile_thread = threading.Thread(
        target=service.reconcile,
        args=("exec-1-order-1",),
    )
    reconcile_thread.start()
    assert gateway.query_started.wait(timeout=1)

    other = service.handle_event(
        OrderEvent(
            kind=OrderEventKind.TRADE,
            client_order_id="exec-1-order-2",
            cumulative_quantity=Decimal("0.2"),
        )
    )
    assert other.state is OrderState.PARTIALLY_FILLED

    gateway.release_query.set()
    reconcile_thread.join(timeout=1)
    assert not reconcile_thread.is_alive()


class RecordingEventRepository:
    def __init__(self) -> None:
        self.events = []

    def append(self, event: OrderEvent) -> None:
        self.events.append(event)

    def contains(self, event_id: str) -> bool:
        return any(event.event_id == event_id for event in self.events)

    def list_for_order(self, client_order_id: str):
        return tuple(
            event for event in self.events if event.client_order_id == client_order_id
        )


class RecordingAtomicPersistence:
    def __init__(self, repository: InMemoryOrderRepository) -> None:
        self.repository = repository
        self.events = []

    def commit(self, order: OrderRecord, event: OrderEvent) -> bool:
        self.events.append(event)
        self.repository.save(order)
        return True


class AppendMustNotBeCalled(RecordingEventRepository):
    def append(self, event: OrderEvent) -> None:
        raise AssertionError("separate event append bypassed atomic persistence")


def test_execution_service_uses_atomic_transition_persistence_when_provided() -> None:
    gateway = StubGateway()
    repository = InMemoryOrderRepository()
    atomic = RecordingAtomicPersistence(repository)
    service = OrderExecutionService(
        gateway,
        repository,
        event_repository=AppendMustNotBeCalled(),
        atomic_persistence=atomic,
    )

    order = service.submit(make_intent())

    assert order.state is OrderState.NEW
    assert [event.kind for event in atomic.events] == [
        OrderEventKind.SUBMIT_REQUESTED,
        OrderEventKind.RECONCILED,
    ]
    assert repository.get(order.intent.client_order_id) == order


def test_old_partial_trade_after_filled_reconciliation_is_journaled_noop() -> None:
    gateway = StubGateway()
    repository = InMemoryOrderRepository()
    events = RecordingEventRepository()
    service = OrderExecutionService(
        gateway,
        repository,
        event_repository=events,
    )
    service.submit(make_intent())
    authoritative = gateway.orders["exec-1-order-1"]
    authoritative.state = OrderState.FILLED
    authoritative.cumulative_quantity = Decimal("1")
    service.reconcile("exec-1-order-1")

    result = service.handle_event(
        OrderEvent(
            kind=OrderEventKind.TRADE,
            client_order_id="exec-1-order-1",
            event_id="older-partial-fill",
            cumulative_quantity=Decimal("0.4"),
        )
    )

    assert result.state is OrderState.FILLED
    assert result.cumulative_quantity == Decimal("1")
    assert events.contains("older-partial-fill")
    persisted = repository.get("exec-1-order-1")
    assert persisted is not None
    assert persisted.state is OrderState.FILLED
    assert persisted.cumulative_quantity == Decimal("1")


def test_late_websocket_ack_after_immediate_rest_fill_is_journaled_noop() -> None:
    gateway = ImmediateFillGateway()
    repository = InMemoryOrderRepository()
    events = RecordingEventRepository()
    service = OrderExecutionService(
        gateway,
        repository,
        event_repository=events,
    )
    filled = service.submit(make_intent())
    assert filled.state is OrderState.FILLED

    result = service.handle_event(
        OrderEvent(
            kind=OrderEventKind.ACKNOWLEDGED,
            client_order_id="exec-1-order-1",
            event_id="late-new-ack",
            cumulative_quantity=Decimal("0"),
            exchange_order_id="exchange-order-1",
        )
    )

    assert result.state is OrderState.FILLED
    assert result.cumulative_quantity == Decimal("1")
    assert result.average_price == Decimal("123.45")
    assert events.contains("late-new-ack")
    persisted = repository.get("exec-1-order-1")
    assert persisted is not None
    assert persisted.state is OrderState.FILLED
    assert persisted.cumulative_quantity == Decimal("1")


def test_explicit_reconcile_enriches_terminal_order_average_price() -> None:
    gateway = StubGateway()
    repository = InMemoryOrderRepository()
    events = RecordingEventRepository()
    service = OrderExecutionService(
        gateway,
        repository,
        event_repository=events,
    )
    service.submit(make_intent())
    authoritative = gateway.orders["exec-1-order-1"]
    authoritative.state = OrderState.FILLED
    authoritative.cumulative_quantity = Decimal("1")
    authoritative.average_price = None
    filled = service.reconcile("exec-1-order-1")
    assert filled.state is OrderState.FILLED
    assert filled.average_price is None

    authoritative.average_price = Decimal("123.45")
    enriched = service.reconcile("exec-1-order-1")

    assert enriched.state is OrderState.FILLED
    assert enriched.cumulative_quantity == Decimal("1")
    assert enriched.average_price == Decimal("123.45")
    persisted = repository.get("exec-1-order-1")
    assert persisted is not None
    assert persisted.average_price == Decimal("123.45")
    assert [event.kind for event in events.events[-2:]] == [
        OrderEventKind.RECONCILED,
        OrderEventKind.RECONCILED,
    ]
