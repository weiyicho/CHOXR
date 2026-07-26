"""Durable SQLite storage for normalized orders and order events."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from engine.domain.instrument import InstrumentId
from engine.domain.order import (
    TERMINAL_ORDER_STATES,
    OrderIntent,
    OrderRecord,
    OrderState,
    OrderType,
    Side,
    TimeInForce,
)
from engine.domain.order_event import OrderEvent, OrderEventKind


class _SqliteStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection


def _ensure_orders_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            client_order_id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            venue TEXT NOT NULL,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity TEXT NOT NULL,
            order_type TEXT NOT NULL,
            price TEXT,
            time_in_force TEXT,
            reduce_only INTEGER NOT NULL,
            post_only INTEGER NOT NULL,
            reason TEXT NOT NULL,
            state TEXT NOT NULL,
            exchange_order_id TEXT,
            cumulative_quantity TEXT NOT NULL,
            average_price TEXT,
            rejection_reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _ensure_order_events_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS order_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            client_order_id TEXT NOT NULL,
            event_id TEXT,
            kind TEXT NOT NULL,
            cumulative_quantity TEXT,
            average_price TEXT,
            last_executed_quantity TEXT,
            last_executed_price TEXT,
            trade_id TEXT,
            commission TEXT,
            commission_asset TEXT,
            exchange_order_id TEXT,
            reconciled_state TEXT,
            reason TEXT,
            occurred_at TEXT NOT NULL
        )
        """
    )
    # Existing runtime databases predate fill-level metadata. Migrate them in
    # place instead of requiring the user to delete durable order history.
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(order_events)").fetchall()
    }
    for name in (
        "last_executed_quantity",
        "last_executed_price",
        "trade_id",
        "commission",
        "commission_asset",
    ):
        if name not in existing_columns:
            connection.execute(
                f"ALTER TABLE order_events ADD COLUMN {name} TEXT"
            )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_order_events_event_id
        ON order_events(event_id)
        WHERE event_id IS NOT NULL
        """
    )


def _order_values(order: OrderRecord) -> tuple[object, ...]:
    intent = order.intent
    return (
        intent.client_order_id,
        intent.execution_id,
        intent.instrument.venue,
        intent.instrument.market,
        intent.instrument.symbol,
        intent.side.value,
        str(intent.quantity),
        intent.order_type.value,
        str(intent.price) if intent.price is not None else None,
        intent.time_in_force.value if intent.time_in_force is not None else None,
        int(intent.reduce_only),
        int(intent.post_only),
        intent.reason,
        order.state.value,
        order.exchange_order_id,
        str(order.cumulative_quantity),
        str(order.average_price) if order.average_price is not None else None,
        order.rejection_reason,
        order.created_at.isoformat(),
        order.updated_at.isoformat(),
    )


def _upsert_order(connection: sqlite3.Connection, order: OrderRecord) -> None:
    existing_row = connection.execute(
        "SELECT * FROM orders WHERE client_order_id = ?",
        (order.intent.client_order_id,),
    ).fetchone()
    if existing_row is not None:
        existing = SqliteOrderRepository._record(existing_row)
        if existing.intent != order.intent:
            raise ValueError("client order ID is already bound to another intent")

    connection.execute(
        """
        INSERT INTO orders VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(client_order_id) DO UPDATE SET
            state = excluded.state,
            exchange_order_id = excluded.exchange_order_id,
            cumulative_quantity = excluded.cumulative_quantity,
            average_price = excluded.average_price,
            rejection_reason = excluded.rejection_reason,
            updated_at = excluded.updated_at
        """,
        _order_values(order),
    )


def _event_values(event: OrderEvent) -> tuple[object, ...]:
    if not event.client_order_id:
        raise ValueError("persisted order event requires a client order ID")
    return (
        event.client_order_id,
        event.event_id,
        event.kind.value,
        (
            str(event.cumulative_quantity)
            if event.cumulative_quantity is not None
            else None
        ),
        str(event.average_price) if event.average_price is not None else None,
        (
            str(event.last_executed_quantity)
            if event.last_executed_quantity is not None
            else None
        ),
        (
            str(event.last_executed_price)
            if event.last_executed_price is not None
            else None
        ),
        event.trade_id,
        str(event.commission) if event.commission is not None else None,
        event.commission_asset,
        event.exchange_order_id,
        event.reconciled_state.value if event.reconciled_state is not None else None,
        event.reason,
        event.occurred_at.isoformat(),
    )


def _append_event(connection: sqlite3.Connection, event: OrderEvent) -> None:
    connection.execute(
        """
        INSERT INTO order_events (
            client_order_id, event_id, kind, cumulative_quantity,
            average_price, last_executed_quantity, last_executed_price,
            trade_id, commission, commission_asset, exchange_order_id,
            reconciled_state, reason, occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _event_values(event),
    )


def _event_from_row(row: sqlite3.Row) -> OrderEvent:
    return OrderEvent(
        kind=OrderEventKind(row["kind"]),
        client_order_id=row["client_order_id"],
        event_id=row["event_id"],
        cumulative_quantity=(
            Decimal(row["cumulative_quantity"])
            if row["cumulative_quantity"] is not None
            else None
        ),
        average_price=(
            Decimal(row["average_price"])
            if row["average_price"] is not None
            else None
        ),
        last_executed_quantity=(
            Decimal(row["last_executed_quantity"])
            if row["last_executed_quantity"] is not None
            else None
        ),
        last_executed_price=(
            Decimal(row["last_executed_price"])
            if row["last_executed_price"] is not None
            else None
        ),
        trade_id=row["trade_id"],
        commission=(
            Decimal(row["commission"])
            if row["commission"] is not None
            else None
        ),
        commission_asset=row["commission_asset"],
        exchange_order_id=row["exchange_order_id"],
        reconciled_state=(
            OrderState(row["reconciled_state"])
            if row["reconciled_state"] is not None
            else None
        ),
        reason=row["reason"],
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
    )


class SqliteOrderRepository(_SqliteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        with self._connect() as connection:
            _ensure_orders_schema(connection)

    def get(self, client_order_id: str) -> OrderRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
        return self._record(row) if row is not None else None

    def save(self, order: OrderRecord) -> None:
        with self._connect() as connection:
            _upsert_order(connection, order)

    def list_open(self, execution_id: str | None = None) -> tuple[OrderRecord, ...]:
        terminal = tuple(state.value for state in TERMINAL_ORDER_STATES)
        placeholders = ", ".join("?" for _ in terminal)
        query = f"SELECT * FROM orders WHERE state NOT IN ({placeholders})"
        parameters: tuple[str, ...] = terminal
        if execution_id is not None:
            query += " AND execution_id = ?"
            parameters += (execution_id,)
        query += " ORDER BY created_at, client_order_id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(self._record(row) for row in rows)

    @staticmethod
    def _record(row: sqlite3.Row) -> OrderRecord:
        intent = OrderIntent(
            execution_id=row["execution_id"],
            client_order_id=row["client_order_id"],
            instrument=InstrumentId(row["venue"], row["market"], row["symbol"]),
            side=Side(row["side"]),
            quantity=Decimal(row["quantity"]),
            order_type=OrderType(row["order_type"]),
            price=Decimal(row["price"]) if row["price"] is not None else None,
            time_in_force=(
                TimeInForce(row["time_in_force"])
                if row["time_in_force"] is not None
                else None
            ),
            reduce_only=bool(row["reduce_only"]),
            post_only=bool(row["post_only"]),
            reason=row["reason"],
        )
        return OrderRecord(
            intent=intent,
            state=OrderState(row["state"]),
            exchange_order_id=row["exchange_order_id"],
            cumulative_quantity=Decimal(row["cumulative_quantity"]),
            average_price=(
                Decimal(row["average_price"])
                if row["average_price"] is not None
                else None
            ),
            rejection_reason=row["rejection_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class SqliteOrderEventRepository(_SqliteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        with self._connect() as connection:
            _ensure_order_events_schema(connection)

    def append(self, event: OrderEvent) -> None:
        with self._connect() as connection:
            _append_event(connection, event)

    def contains(self, event_id: str) -> bool:
        if not event_id.strip():
            raise ValueError("event_id cannot be blank")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM order_events WHERE event_id = ? LIMIT 1",
                (event_id,),
            ).fetchone()
        return row is not None

    def list_for_order(self, client_order_id: str) -> tuple[OrderEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM order_events
                WHERE client_order_id = ?
                ORDER BY sequence
                """,
                (client_order_id,),
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)


class SqliteAtomicOrderPersistence(_SqliteStore):
    """Atomically append an order event and update its materialized snapshot."""

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        with self._connect() as connection:
            _ensure_orders_schema(connection)
            _ensure_order_events_schema(connection)

    def commit(self, order: OrderRecord, event: OrderEvent) -> bool:
        if not event.client_order_id:
            raise ValueError("persisted order event requires a client order ID")
        if event.client_order_id != order.intent.client_order_id:
            raise ValueError("order event and snapshot client order IDs differ")

        connection = self._connect()
        try:
            # Serialize writers so duplicate detection and both writes are one
            # all-or-nothing decision, including across multiple processes.
            connection.execute("BEGIN IMMEDIATE")
            if event.event_id is not None:
                existing_row = connection.execute(
                    "SELECT * FROM order_events WHERE event_id = ? LIMIT 1",
                    (event.event_id,),
                ).fetchone()
                if existing_row is not None:
                    existing = _event_from_row(existing_row)
                    if existing != event:
                        raise ValueError("event ID is already bound to another event")
                    connection.rollback()
                    return False

            # Insert first deliberately: tests exercise that a subsequent
            # snapshot validation failure rolls this journal write back.
            _append_event(connection, event)
            _upsert_order(connection, order)
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
