from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from adapters.persistence import (
    SqliteAtomicOrderPersistence,
    SqliteOrderEventRepository,
    SqliteOrderRepository,
)
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord, OrderState, Side
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.ports.repositories import AtomicOrderPersistence


OCCURRED_AT = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def make_order(
    *,
    side: Side = Side.BUY,
    state: OrderState = OrderState.PARTIALLY_FILLED,
    cumulative_quantity: Decimal = Decimal("0.25"),
) -> OrderRecord:
    return OrderRecord(
        intent=OrderIntent(
            execution_id="exec-atomic",
            client_order_id="atomic-order-1",
            instrument=InstrumentId("test", "SPOT", "ETHUSDT"),
            side=side,
            quantity=Decimal("1.25"),
        ),
        state=state,
        cumulative_quantity=cumulative_quantity,
        average_price=Decimal("2000.5"),
    )


def make_event(*, event_id: str = "event-atomic-1") -> OrderEvent:
    return OrderEvent(
        kind=OrderEventKind.TRADE,
        client_order_id="atomic-order-1",
        event_id=event_id,
        cumulative_quantity=Decimal("0.25"),
        average_price=Decimal("2000.5"),
        occurred_at=OCCURRED_AT,
    )


def test_atomic_commit_writes_event_and_order_snapshot(tmp_path) -> None:
    database = tmp_path / "engine.sqlite3"
    persistence = SqliteAtomicOrderPersistence(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    order = make_order()
    event = make_event()

    assert isinstance(persistence, AtomicOrderPersistence)
    assert persistence.commit(order, event) is True
    assert orders.get("atomic-order-1") == order
    assert events.list_for_order("atomic-order-1") == (event,)


def test_atomic_commit_rolls_back_event_when_order_snapshot_fails(tmp_path) -> None:
    database = tmp_path / "engine.sqlite3"
    persistence = SqliteAtomicOrderPersistence(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    original = make_order()
    orders.save(original)

    conflicting_snapshot = make_order(side=Side.SELL)
    event = replace(make_event(), event_id="must-roll-back")
    with pytest.raises(
        ValueError,
        match="client order ID is already bound to another intent",
    ):
        persistence.commit(conflicting_snapshot, event)

    assert not events.contains("must-roll-back")
    assert events.list_for_order("atomic-order-1") == ()
    assert orders.get("atomic-order-1") == original


def test_exact_duplicate_event_is_noop_for_order_snapshot(tmp_path) -> None:
    database = tmp_path / "engine.sqlite3"
    persistence = SqliteAtomicOrderPersistence(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    original = make_order()
    event = make_event()
    assert persistence.commit(original, event) is True

    candidate_from_duplicate = make_order(
        state=OrderState.FILLED,
        cumulative_quantity=Decimal("1.25"),
    )
    candidate_from_duplicate.average_price = Decimal("2001")
    assert persistence.commit(candidate_from_duplicate, event) is False

    assert orders.get("atomic-order-1") == original
    assert events.list_for_order("atomic-order-1") == (event,)


def test_conflicting_duplicate_event_id_is_rejected_without_writes(tmp_path) -> None:
    database = tmp_path / "engine.sqlite3"
    persistence = SqliteAtomicOrderPersistence(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    original = make_order()
    event = make_event()
    assert persistence.commit(original, event) is True

    conflicting_event = replace(event, kind=OrderEventKind.CANCELED)
    candidate = make_order(
        state=OrderState.CANCELED,
        cumulative_quantity=Decimal("0.25"),
    )
    with pytest.raises(
        ValueError,
        match="event ID is already bound to another event",
    ):
        persistence.commit(candidate, conflicting_event)

    assert orders.get("atomic-order-1") == original
    assert events.list_for_order("atomic-order-1") == (event,)


def test_atomic_commit_rejects_mismatched_client_order_ids(tmp_path) -> None:
    persistence = SqliteAtomicOrderPersistence(tmp_path / "engine.sqlite3")
    event = replace(make_event(), client_order_id="some-other-order")

    with pytest.raises(
        ValueError,
        match="order event and snapshot client order IDs differ",
    ):
        persistence.commit(make_order(), event)
