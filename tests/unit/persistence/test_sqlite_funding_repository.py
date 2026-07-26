import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from adapters.persistence.sqlite.funding_repository import SqliteFundingRepository
from adapters.persistence.sqlite.order_repository import SqliteOrderRepository
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord, OrderState, Side
from strategies.funding_rate.session import (
    FundingAction,
    FundingActionStatus,
    FundingSession,
    FundingSessionStatus,
)


CREATED_AT = datetime(
    2026,
    7,
    26,
    15,
    1,
    2,
    345678,
    tzinfo=timezone(timedelta(hours=8)),
)


def make_session(
    *,
    execution_id: str = "funding-exec-1",
    status: FundingSessionStatus = FundingSessionStatus.ENTERING,
    target_quantity: Decimal = Decimal("0.07000000"),
) -> FundingSession:
    return FundingSession(
        execution_id=execution_id,
        symbol="BNBUSDT",
        policy_name="PERPETUAL_MAKER_SPOT_TAKER",
        status=status,
        target_quantity=target_quantity,
        capital=Decimal("40.01270000"),
        maker_client_order_id="frp-perp-maker-1",
        starting_spot_quantity=Decimal("1.25000000"),
        delta_tolerance=Decimal("0.00001000"),
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def make_action(
    *,
    action_id: str = "funding-action-1",
    execution_id: str = "funding-exec-1",
    status: FundingActionStatus = FundingActionStatus.PENDING,
    requested_quantity: Decimal | None = Decimal("0.02000000"),
    created_at: datetime = CREATED_AT,
) -> FundingAction:
    return FundingAction(
        action_id=action_id,
        execution_id=execution_id,
        source_event_id="binance-trade-100",
        action_type="SUBMIT_HEDGE_ORDER",
        client_order_id=f"frh-{action_id}",
        requested_quantity=requested_quantity,
        status=status,
        created_at=created_at,
        updated_at=created_at,
    )


def test_funding_and_order_repositories_share_one_database(tmp_path) -> None:
    database = tmp_path / "engine.sqlite3"
    orders = SqliteOrderRepository(database)
    funding = SqliteFundingRepository(database)
    order = OrderRecord(
        intent=OrderIntent(
            execution_id="funding-exec-1",
            client_order_id="frp-perp-maker-1",
            instrument=InstrumentId(
                "binance",
                "USD_M_PERPETUAL",
                "BNBUSDT",
            ),
            side=Side.SELL,
            quantity=Decimal("0.07000000"),
        ),
        state=OrderState.NEW,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )
    session = make_session()
    action = make_action()

    orders.save(order)
    funding.save_session(session)
    assert funding.save_action(action) is True

    with sqlite3.connect(database) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"orders", "funding_sessions", "funding_actions"} <= table_names
    assert SqliteOrderRepository(database).get(order.intent.client_order_id) == order
    restarted = SqliteFundingRepository(database)
    assert restarted.get_session(session.execution_id) == session
    assert restarted.get_action(action.action_id) == action


def test_restart_preserves_decimal_and_datetime_representation(tmp_path) -> None:
    database = tmp_path / "engine.sqlite3"
    repository = SqliteFundingRepository(database)
    session = make_session()
    action = make_action()
    repository.save_session(session)
    repository.save_action(action)

    restarted = SqliteFundingRepository(database)
    restored_session = restarted.get_session(session.execution_id)
    restored_action = restarted.get_action(action.action_id)

    assert restored_session is not None
    assert restored_action is not None
    assert restored_session.target_quantity.as_tuple() == (
        session.target_quantity.as_tuple()
    )
    assert restored_session.delta_tolerance.as_tuple() == (
        session.delta_tolerance.as_tuple()
    )
    assert restored_session.capital.as_tuple() == session.capital.as_tuple()
    assert restored_action.requested_quantity is not None
    assert restored_action.requested_quantity.as_tuple() == (
        action.requested_quantity.as_tuple()
    )
    assert restored_session.created_at.isoformat() == session.created_at.isoformat()
    assert restored_action.created_at.isoformat() == action.created_at.isoformat()


def test_duplicate_action_is_idempotent_and_conflicting_payload_is_rejected(
    tmp_path,
) -> None:
    repository = SqliteFundingRepository(tmp_path / "engine.sqlite3")
    original = make_action()

    assert repository.save_action(original) is True
    assert repository.save_action(original) is False

    conflicting = replace(original, requested_quantity=Decimal("0.03"))
    with pytest.raises(
        ValueError,
        match="action ID is already bound to another funding action",
    ):
        repository.save_action(conflicting)

    assert repository.get_action(original.action_id) == original


def test_session_payload_is_immutable_and_status_has_explicit_update_path(
    tmp_path,
) -> None:
    repository = SqliteFundingRepository(tmp_path / "engine.sqlite3")
    original = make_session()
    repository.save_session(original)
    repository.save_session(original)

    with pytest.raises(
        ValueError,
        match="execution ID is already bound to another funding session",
    ):
        repository.save_session(
            replace(original, target_quantity=Decimal("0.08"))
        )
    with pytest.raises(
        ValueError,
        match="execution ID is already bound to another funding session",
    ):
        repository.save_session(
            replace(original, status=FundingSessionStatus.HEDGING)
        )

    updated_at = CREATED_AT + timedelta(seconds=2)
    updated = repository.update_session_status(
        original.execution_id,
        FundingSessionStatus.HEDGING,
        updated_at=updated_at,
    )
    assert updated.status is FundingSessionStatus.HEDGING
    assert updated.updated_at == updated_at
    assert repository.get_session(original.execution_id) == updated


def test_action_listing_is_stable_and_pending_includes_crash_recovery_work(
    tmp_path,
) -> None:
    repository = SqliteFundingRepository(tmp_path / "engine.sqlite3")
    later = CREATED_AT + timedelta(seconds=1)
    actions = (
        make_action(action_id="action-b", created_at=CREATED_AT),
        make_action(action_id="action-a", created_at=CREATED_AT),
        make_action(
            action_id="action-completed",
            status=FundingActionStatus.COMPLETED,
            created_at=later,
        ),
        make_action(
            action_id="action-in-progress",
            status=FundingActionStatus.IN_PROGRESS,
            created_at=later,
        ),
        make_action(
            action_id="other-execution",
            execution_id="funding-exec-2",
            created_at=CREATED_AT,
        ),
    )
    for action in actions:
        repository.save_action(action)

    assert tuple(
        action.action_id
        for action in repository.list_actions("funding-exec-1")
    ) == (
        "action-a",
        "action-b",
        "action-completed",
        "action-in-progress",
    )
    assert tuple(
        action.action_id
        for action in repository.list_pending_actions("funding-exec-1")
    ) == (
        "action-a",
        "action-b",
        "action-in-progress",
    )

    failed_at = later + timedelta(seconds=1)
    failed = repository.update_action_status(
        "action-in-progress",
        FundingActionStatus.FAILED,
        updated_at=failed_at,
        failure_reason="Spot hedge rejected",
    )
    assert failed.status is FundingActionStatus.FAILED
    assert failed.failure_reason == "Spot hedge rejected"
    assert tuple(
        action.action_id
        for action in repository.list_pending_actions("funding-exec-1")
    ) == ("action-a", "action-b")


def test_status_updates_reject_unknown_ids(tmp_path) -> None:
    repository = SqliteFundingRepository(tmp_path / "engine.sqlite3")

    with pytest.raises(KeyError, match="unknown funding session"):
        repository.update_session_status(
            "missing-session",
            FundingSessionStatus.FAILED,
        )
    with pytest.raises(KeyError, match="unknown funding action"):
        repository.update_action_status(
            "missing-action",
            FundingActionStatus.FAILED,
        )


def test_failed_hedge_pause_and_recovery_outbox_commit_atomically(
    tmp_path,
) -> None:
    repository = SqliteFundingRepository(tmp_path / "engine.sqlite3")
    session = make_session()
    hedge = make_action(action_id="hedge-submit")
    cancel = replace(
        make_action(action_id="cancel-maker", requested_quantity=None),
        action_type="CANCEL_MAKER",
        client_order_id=session.maker_client_order_id,
    )
    reconcile = replace(
        make_action(action_id="reconcile-orders", requested_quantity=None),
        action_type="RECONCILE",
        client_order_id=session.maker_client_order_id,
    )
    repository.save_session(session)
    repository.save_action(hedge)

    failed, paused, recovery = repository.fail_hedge_and_pause(
        hedge.action_id,
        failure_reason="exchange rejected order action",
        recovery_actions=(cancel, reconcile),
    )

    assert failed.status is FundingActionStatus.FAILED
    assert paused.status is FundingSessionStatus.PAUSED
    assert recovery == (cancel, reconcile)
    assert repository.get_action(hedge.action_id).status is FundingActionStatus.FAILED
    assert repository.get_session(session.execution_id).status is FundingSessionStatus.PAUSED
    assert tuple(
        action.action_id
        for action in repository.list_pending_actions(session.execution_id)
    ) == ("cancel-maker", "reconcile-orders")


def test_failed_hedge_recovery_conflict_rolls_back_every_state_change(
    tmp_path,
) -> None:
    repository = SqliteFundingRepository(tmp_path / "engine.sqlite3")
    session = make_session()
    hedge = make_action(action_id="hedge-submit")
    conflicting_existing = make_action(
        action_id="cancel-maker",
        requested_quantity=Decimal("0.01"),
    )
    cancel_candidate = replace(
        conflicting_existing,
        action_type="CANCEL_MAKER",
        client_order_id=session.maker_client_order_id,
        requested_quantity=None,
    )
    reconcile_candidate = replace(
        make_action(action_id="reconcile-orders", requested_quantity=None),
        action_type="RECONCILE",
        client_order_id=session.maker_client_order_id,
    )
    repository.save_session(session)
    repository.save_action(hedge)
    repository.save_action(conflicting_existing)

    with pytest.raises(
        ValueError,
        match="action ID is already bound",
    ):
        repository.fail_hedge_and_pause(
            hedge.action_id,
            failure_reason="exchange rejected order action",
            recovery_actions=(cancel_candidate, reconcile_candidate),
        )

    assert repository.get_action(hedge.action_id).status is FundingActionStatus.PENDING
    assert repository.get_session(session.execution_id).status is FundingSessionStatus.ENTERING
    assert repository.get_action("reconcile-orders") is None
