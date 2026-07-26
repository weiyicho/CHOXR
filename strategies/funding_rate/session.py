"""Durable strategy state for one funding-rate execution.

These models contain strategy-specific state only.  Exchange orders continue
to live in the generic order repository and are linked through deterministic
client order IDs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Protocol


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _required_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


def _aware_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class FundingSessionStatus(str, Enum):
    """Lifecycle of one two-leg funding-rate strategy execution."""

    PLANNED = "PLANNED"
    ENTERING = "ENTERING"
    HEDGING = "HEDGING"
    OPEN = "OPEN"
    RECOVERING = "RECOVERING"
    PAUSED = "PAUSED"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


TERMINAL_FUNDING_SESSION_STATUSES = frozenset(
    {
        FundingSessionStatus.CLOSED,
        FundingSessionStatus.FAILED,
    }
)


@dataclass(frozen=True)
class FundingSession:
    """Immutable materialized state for one funding-rate execution."""

    execution_id: str
    symbol: str
    policy_name: str
    status: FundingSessionStatus
    target_quantity: Decimal
    capital: Decimal
    maker_client_order_id: str | None = None
    starting_spot_quantity: Decimal = Decimal("0")
    delta_tolerance: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_id",
            _required_text(self.execution_id, "execution_id"),
        )
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        object.__setattr__(
            self,
            "policy_name",
            _required_text(self.policy_name, "policy_name"),
        )
        object.__setattr__(self, "status", FundingSessionStatus(self.status))
        object.__setattr__(
            self,
            "maker_client_order_id",
            _optional_text(self.maker_client_order_id),
        )
        object.__setattr__(
            self,
            "target_quantity",
            _decimal(self.target_quantity, "target_quantity"),
        )
        object.__setattr__(
            self,
            "capital",
            _decimal(self.capital, "capital"),
        )
        object.__setattr__(
            self,
            "starting_spot_quantity",
            _decimal(self.starting_spot_quantity, "starting_spot_quantity"),
        )
        object.__setattr__(
            self,
            "delta_tolerance",
            _decimal(self.delta_tolerance, "delta_tolerance"),
        )
        object.__setattr__(
            self,
            "created_at",
            _aware_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _aware_datetime(self.updated_at, "updated_at"),
        )

        if self.target_quantity <= 0:
            raise ValueError("target_quantity must be positive")
        if self.capital <= 0:
            raise ValueError("capital must be positive")
        if self.starting_spot_quantity < 0:
            raise ValueError("starting_spot_quantity cannot be negative")
        if self.delta_tolerance < 0:
            raise ValueError("delta_tolerance cannot be negative")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")


class FundingActionStatus(str, Enum):
    """Durable dispatch state for an action selected by a funding policy."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


TERMINAL_FUNDING_ACTION_STATUSES = frozenset(
    {
        FundingActionStatus.COMPLETED,
        FundingActionStatus.FAILED,
    }
)


@dataclass(frozen=True)
class FundingAction:
    """One idempotent strategy action selected from a committed event."""

    action_id: str
    execution_id: str
    action_type: str
    status: FundingActionStatus = FundingActionStatus.PENDING
    source_event_id: str | None = None
    client_order_id: str | None = None
    requested_quantity: Decimal | None = None
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_id",
            _required_text(self.action_id, "action_id"),
        )
        object.__setattr__(
            self,
            "execution_id",
            _required_text(self.execution_id, "execution_id"),
        )
        object.__setattr__(
            self,
            "action_type",
            _required_text(self.action_type, "action_type"),
        )
        object.__setattr__(self, "status", FundingActionStatus(self.status))
        object.__setattr__(
            self,
            "source_event_id",
            _optional_text(self.source_event_id),
        )
        object.__setattr__(
            self,
            "client_order_id",
            _optional_text(self.client_order_id),
        )
        object.__setattr__(
            self,
            "failure_reason",
            _optional_text(self.failure_reason),
        )
        if self.requested_quantity is not None:
            object.__setattr__(
                self,
                "requested_quantity",
                _decimal(self.requested_quantity, "requested_quantity"),
            )
            if self.requested_quantity <= 0:
                raise ValueError("requested_quantity must be positive")
        object.__setattr__(
            self,
            "created_at",
            _aware_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            _aware_datetime(self.updated_at, "updated_at"),
        )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")


class FundingSessionRepository(Protocol):
    """Persistence contract for materialized funding session state."""

    def save_session(self, session: FundingSession) -> None: ...

    def get_session(self, execution_id: str) -> FundingSession | None: ...

    def list_active_sessions(self) -> tuple[FundingSession, ...]: ...

    def update_session_status(
        self,
        execution_id: str,
        status: FundingSessionStatus,
        *,
        updated_at: datetime | None = None,
    ) -> FundingSession: ...


class FundingActionRepository(Protocol):
    """Persistence contract for idempotent funding strategy actions."""

    def save_action(self, action: FundingAction) -> bool: ...

    def get_action(self, action_id: str) -> FundingAction | None: ...

    def list_actions(self, execution_id: str) -> tuple[FundingAction, ...]: ...

    def list_pending_actions(
        self,
        execution_id: str | None = None,
    ) -> tuple[FundingAction, ...]: ...

    def update_action_status(
        self,
        action_id: str,
        status: FundingActionStatus,
        *,
        updated_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> FundingAction: ...

    def fail_hedge_and_pause(
        self,
        action_id: str,
        *,
        failure_reason: str,
        recovery_actions: tuple[FundingAction, ...],
        updated_at: datetime | None = None,
    ) -> tuple[FundingAction, FundingSession, tuple[FundingAction, ...]]:
        """Atomically fail one hedge action and persist its stop plan."""
        ...
