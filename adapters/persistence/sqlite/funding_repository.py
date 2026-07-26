"""SQLite persistence for funding strategy sessions and actions.

The repository intentionally accepts the same database path as the generic
order repositories.  It creates only its own tables and leaves every existing
table and row untouched.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from strategies.funding_rate.session import (
    TERMINAL_FUNDING_ACTION_STATUSES,
    TERMINAL_FUNDING_SESSION_STATUSES,
    FundingAction,
    FundingActionStatus,
    FundingSession,
    FundingSessionStatus,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SqliteFundingRepository:
    """Store funding sessions and actions beside generic order tables."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as connection:
            self._ensure_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS funding_sessions (
                execution_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                status TEXT NOT NULL,
                target_quantity TEXT NOT NULL,
                capital TEXT NOT NULL,
                maker_client_order_id TEXT,
                starting_spot_quantity TEXT NOT NULL,
                delta_tolerance TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS funding_actions (
                action_id TEXT PRIMARY KEY,
                execution_id TEXT NOT NULL,
                source_event_id TEXT,
                action_type TEXT NOT NULL,
                client_order_id TEXT,
                requested_quantity TEXT,
                status TEXT NOT NULL,
                failure_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_funding_actions_execution_created
            ON funding_actions(execution_id, created_at, action_id)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_funding_actions_status_created
            ON funding_actions(status, created_at, action_id)
            """
        )

    def save_session(self, session: FundingSession) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM funding_sessions WHERE execution_id = ?",
                (session.execution_id,),
            ).fetchone()
            if row is not None:
                existing = self._session_from_row(row)
                if existing != session:
                    raise ValueError(
                        "execution ID is already bound to another funding session"
                    )
                connection.rollback()
                return

            connection.execute(
                """
                INSERT INTO funding_sessions (
                    execution_id, symbol, policy_name, status, target_quantity,
                    capital, maker_client_order_id, starting_spot_quantity,
                    delta_tolerance, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._session_values(session),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_session(self, execution_id: str) -> FundingSession | None:
        normalized = self._required_id(execution_id, "execution_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM funding_sessions WHERE execution_id = ?",
                (normalized,),
            ).fetchone()
        return self._session_from_row(row) if row is not None else None

    def list_active_sessions(self) -> tuple[FundingSession, ...]:
        terminal = tuple(status.value for status in TERMINAL_FUNDING_SESSION_STATUSES)
        placeholders = ", ".join("?" for _ in terminal)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM funding_sessions
                WHERE status NOT IN ({placeholders})
                """,
                terminal,
            ).fetchall()
        sessions = (self._session_from_row(row) for row in rows)
        return tuple(
            sorted(
                sessions,
                key=lambda session: (session.created_at, session.execution_id),
            )
        )

    def update_session_status(
        self,
        execution_id: str,
        status: FundingSessionStatus,
        *,
        updated_at: datetime | None = None,
    ) -> FundingSession:
        normalized = self._required_id(execution_id, "execution_id")
        normalized_status = FundingSessionStatus(status)
        timestamp = updated_at or _utc_now()

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM funding_sessions WHERE execution_id = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown funding session: {normalized}")
            existing = self._session_from_row(row)
            candidate = FundingSession(
                execution_id=existing.execution_id,
                symbol=existing.symbol,
                policy_name=existing.policy_name,
                status=normalized_status,
                target_quantity=existing.target_quantity,
                capital=existing.capital,
                maker_client_order_id=existing.maker_client_order_id,
                starting_spot_quantity=existing.starting_spot_quantity,
                delta_tolerance=existing.delta_tolerance,
                created_at=existing.created_at,
                updated_at=timestamp,
            )
            connection.execute(
                """
                UPDATE funding_sessions
                SET status = ?, updated_at = ?
                WHERE execution_id = ?
                """,
                (
                    candidate.status.value,
                    candidate.updated_at.isoformat(),
                    candidate.execution_id,
                ),
            )
            connection.commit()
            return candidate
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save_action(self, action: FundingAction) -> bool:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM funding_actions WHERE action_id = ?",
                (action.action_id,),
            ).fetchone()
            if row is not None:
                existing = self._action_from_row(row)
                if self._action_payload(existing) != self._action_payload(action):
                    raise ValueError(
                        "action ID is already bound to another funding action"
                    )
                connection.rollback()
                return False

            connection.execute(
                """
                INSERT INTO funding_actions (
                    action_id, execution_id, source_event_id, action_type,
                    client_order_id, requested_quantity, status,
                    failure_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._action_values(action),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_action(self, action_id: str) -> FundingAction | None:
        normalized = self._required_id(action_id, "action_id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM funding_actions WHERE action_id = ?",
                (normalized,),
            ).fetchone()
        return self._action_from_row(row) if row is not None else None

    def list_actions(self, execution_id: str) -> tuple[FundingAction, ...]:
        normalized = self._required_id(execution_id, "execution_id")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM funding_actions WHERE execution_id = ?",
                (normalized,),
            ).fetchall()
        return self._sorted_actions(rows)

    def list_pending_actions(
        self,
        execution_id: str | None = None,
    ) -> tuple[FundingAction, ...]:
        pending = tuple(
            status.value
            for status in FundingActionStatus
            if status not in TERMINAL_FUNDING_ACTION_STATUSES
        )
        placeholders = ", ".join("?" for _ in pending)
        query = (
            "SELECT * FROM funding_actions "
            f"WHERE status IN ({placeholders})"
        )
        parameters: tuple[str, ...] = pending
        if execution_id is not None:
            normalized = self._required_id(execution_id, "execution_id")
            query += " AND execution_id = ?"
            parameters += (normalized,)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return self._sorted_actions(rows)

    def update_action_status(
        self,
        action_id: str,
        status: FundingActionStatus,
        *,
        updated_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> FundingAction:
        normalized = self._required_id(action_id, "action_id")
        normalized_status = FundingActionStatus(status)
        timestamp = updated_at or _utc_now()

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM funding_actions WHERE action_id = ?",
                (normalized,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown funding action: {normalized}")
            existing = self._action_from_row(row)
            candidate = FundingAction(
                action_id=existing.action_id,
                execution_id=existing.execution_id,
                source_event_id=existing.source_event_id,
                action_type=existing.action_type,
                client_order_id=existing.client_order_id,
                requested_quantity=existing.requested_quantity,
                status=normalized_status,
                failure_reason=failure_reason,
                created_at=existing.created_at,
                updated_at=timestamp,
            )
            connection.execute(
                """
                UPDATE funding_actions
                SET status = ?, failure_reason = ?, updated_at = ?
                WHERE action_id = ?
                """,
                (
                    candidate.status.value,
                    candidate.failure_reason,
                    candidate.updated_at.isoformat(),
                    candidate.action_id,
                ),
            )
            connection.commit()
            return candidate
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def fail_hedge_and_pause(
        self,
        action_id: str,
        *,
        failure_reason: str,
        recovery_actions: tuple[FundingAction, ...],
        updated_at: datetime | None = None,
    ) -> tuple[FundingAction, FundingSession, tuple[FundingAction, ...]]:
        """Commit the failed hedge, paused session and stop outbox together."""

        normalized = self._required_id(action_id, "action_id")
        timestamp = updated_at or _utc_now()
        candidates = tuple(recovery_actions)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            action_row = connection.execute(
                "SELECT * FROM funding_actions WHERE action_id = ?",
                (normalized,),
            ).fetchone()
            if action_row is None:
                raise KeyError(f"unknown funding action: {normalized}")
            existing_action = self._action_from_row(action_row)
            failed_action = FundingAction(
                action_id=existing_action.action_id,
                execution_id=existing_action.execution_id,
                source_event_id=existing_action.source_event_id,
                action_type=existing_action.action_type,
                client_order_id=existing_action.client_order_id,
                requested_quantity=existing_action.requested_quantity,
                status=FundingActionStatus.FAILED,
                failure_reason=failure_reason,
                created_at=existing_action.created_at,
                updated_at=timestamp,
            )

            session_row = connection.execute(
                "SELECT * FROM funding_sessions WHERE execution_id = ?",
                (existing_action.execution_id,),
            ).fetchone()
            if session_row is None:
                raise KeyError(
                    "unknown funding session: "
                    f"{existing_action.execution_id}"
                )
            existing_session = self._session_from_row(session_row)
            paused_session = FundingSession(
                execution_id=existing_session.execution_id,
                symbol=existing_session.symbol,
                policy_name=existing_session.policy_name,
                status=FundingSessionStatus.PAUSED,
                target_quantity=existing_session.target_quantity,
                capital=existing_session.capital,
                maker_client_order_id=existing_session.maker_client_order_id,
                starting_spot_quantity=existing_session.starting_spot_quantity,
                delta_tolerance=existing_session.delta_tolerance,
                created_at=existing_session.created_at,
                updated_at=timestamp,
            )

            persisted_recovery: list[FundingAction] = []
            for candidate in candidates:
                if candidate.execution_id != existing_action.execution_id:
                    raise ValueError(
                        "recovery action execution does not match failed hedge"
                    )
                row = connection.execute(
                    "SELECT * FROM funding_actions WHERE action_id = ?",
                    (candidate.action_id,),
                ).fetchone()
                if row is not None:
                    existing = self._action_from_row(row)
                    if (
                        self._action_payload(existing)
                        != self._action_payload(candidate)
                    ):
                        raise ValueError(
                            "action ID is already bound to another funding action"
                        )
                    persisted_recovery.append(existing)
                    continue
                connection.execute(
                    """
                    INSERT INTO funding_actions (
                        action_id, execution_id, source_event_id, action_type,
                        client_order_id, requested_quantity, status,
                        failure_reason, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._action_values(candidate),
                )
                persisted_recovery.append(candidate)

            connection.execute(
                """
                UPDATE funding_actions
                SET status = ?, failure_reason = ?, updated_at = ?
                WHERE action_id = ?
                """,
                (
                    failed_action.status.value,
                    failed_action.failure_reason,
                    failed_action.updated_at.isoformat(),
                    failed_action.action_id,
                ),
            )
            connection.execute(
                """
                UPDATE funding_sessions
                SET status = ?, updated_at = ?
                WHERE execution_id = ?
                """,
                (
                    paused_session.status.value,
                    paused_session.updated_at.isoformat(),
                    paused_session.execution_id,
                ),
            )
            connection.commit()
            return (
                failed_action,
                paused_session,
                tuple(persisted_recovery),
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _required_id(value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} is required")
        return normalized

    @staticmethod
    def _session_values(session: FundingSession) -> tuple[object, ...]:
        return (
            session.execution_id,
            session.symbol,
            session.policy_name,
            session.status.value,
            str(session.target_quantity),
            str(session.capital),
            session.maker_client_order_id,
            str(session.starting_spot_quantity),
            str(session.delta_tolerance),
            session.created_at.isoformat(),
            session.updated_at.isoformat(),
        )

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> FundingSession:
        return FundingSession(
            execution_id=row["execution_id"],
            symbol=row["symbol"],
            policy_name=row["policy_name"],
            status=FundingSessionStatus(row["status"]),
            target_quantity=Decimal(row["target_quantity"]),
            capital=Decimal(row["capital"]),
            maker_client_order_id=row["maker_client_order_id"],
            starting_spot_quantity=Decimal(row["starting_spot_quantity"]),
            delta_tolerance=Decimal(row["delta_tolerance"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _action_values(action: FundingAction) -> tuple[object, ...]:
        return (
            action.action_id,
            action.execution_id,
            action.source_event_id,
            action.action_type,
            action.client_order_id,
            (
                str(action.requested_quantity)
                if action.requested_quantity is not None
                else None
            ),
            action.status.value,
            action.failure_reason,
            action.created_at.isoformat(),
            action.updated_at.isoformat(),
        )

    @staticmethod
    def _action_payload(action: FundingAction) -> tuple[object, ...]:
        return (
            action.action_id,
            action.execution_id,
            action.source_event_id,
            action.action_type,
            action.client_order_id,
            action.requested_quantity,
        )

    @classmethod
    def _action_from_row(cls, row: sqlite3.Row) -> FundingAction:
        return FundingAction(
            action_id=row["action_id"],
            execution_id=row["execution_id"],
            source_event_id=row["source_event_id"],
            action_type=row["action_type"],
            client_order_id=row["client_order_id"],
            requested_quantity=(
                Decimal(row["requested_quantity"])
                if row["requested_quantity"] is not None
                else None
            ),
            status=FundingActionStatus(row["status"]),
            failure_reason=row["failure_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @classmethod
    def _sorted_actions(
        cls,
        rows: list[sqlite3.Row],
    ) -> tuple[FundingAction, ...]:
        actions = (cls._action_from_row(row) for row in rows)
        return tuple(
            sorted(
                actions,
                key=lambda action: (action.created_at, action.action_id),
            )
        )
