from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from engine.domain.order_event import OrderEventKind
from strategies.funding_rate.execution_policy import (
    FundingCommandKind,
    FundingOrderRole,
    FundingPolicyCommand,
    FundingPolicyContext,
    PerpetualMakerSpotTakerPolicy,
)
from strategies.funding_rate.hedge import (
    FundingHedgeCalculator,
    HedgeCalculationInput,
)


def hedge_decision(**overrides: str):
    values = {
        "perpetual_filled_quantity": "0.6",
        "spot_confirmed_quantity": "0.4",
        "spot_base_commission": "0",
        "spot_pending_quantity": "0",
        "reference_price": "100",
        "quantity_step": "0.001",
        "min_quantity": "0.001",
        "min_notional": "0",
        "delta_tolerance": "0.0001",
    }
    values.update(overrides)
    return FundingHedgeCalculator().calculate(HedgeCalculationInput(**values))


def policy_context(**overrides) -> FundingPolicyContext:
    values = {
        "event_role": FundingOrderRole.MAKER,
        "event_kind": OrderEventKind.TRADE,
        "maker_terminal": False,
        "maker_remaining_quantity": "0.4",
        "hedge": hedge_decision(),
        "reference_price": "100",
        "max_unhedged_notional": "100",
        "source_event_id": "maker-trade-1",
    }
    values.update(overrides)
    return FundingPolicyContext(**values)


def command_kinds(commands) -> tuple[FundingCommandKind, ...]:
    return tuple(command.kind for command in commands)


def test_partial_maker_fill_submits_exact_calculated_hedge_only() -> None:
    commands = PerpetualMakerSpotTakerPolicy().decide(policy_context())

    assert command_kinds(commands) == (FundingCommandKind.SUBMIT_HEDGE,)
    assert commands[0].quantity == Decimal("0.2")
    assert commands[0].source_event_id == "maker-trade-1"


def test_pending_hedge_blocks_replayed_submission() -> None:
    context = policy_context(
        hedge=hedge_decision(spot_pending_quantity="0.2"),
    )

    assert PerpetualMakerSpotTakerPolicy().decide(context) == ()


def test_acknowledgement_and_inactive_session_are_no_ops() -> None:
    policy = PerpetualMakerSpotTakerPolicy()

    assert policy.decide(
        policy_context(event_kind=OrderEventKind.ACKNOWLEDGED)
    ) == ()
    assert policy.decide(policy_context(session_status="OPEN")) == ()


def test_terminal_maker_with_confirmed_delta_in_tolerance_marks_open() -> None:
    context = policy_context(
        event_kind=OrderEventKind.CANCELED,
        maker_terminal=True,
        maker_remaining_quantity="0.4",
        hedge=hedge_decision(
            perpetual_filled_quantity="0.6",
            spot_confirmed_quantity="0.59995",
            delta_tolerance="0.0001",
        ),
    )

    commands = PerpetualMakerSpotTakerPolicy().decide(context)

    assert command_kinds(commands) == (FundingCommandKind.MARK_OPEN,)


def test_pending_order_prevents_marking_terminal_session_open() -> None:
    context = policy_context(
        event_kind=OrderEventKind.CANCELED,
        maker_terminal=True,
        hedge=hedge_decision(
            perpetual_filled_quantity="0.6",
            spot_confirmed_quantity="0.6",
            spot_pending_quantity="0.1",
        ),
    )

    assert PerpetualMakerSpotTakerPolicy().decide(context) == ()


def test_hedge_rejection_cancels_live_maker_then_reconciles_and_pauses() -> None:
    context = policy_context(
        event_role=FundingOrderRole.HEDGE,
        event_kind=OrderEventKind.REJECTED,
    )

    commands = PerpetualMakerSpotTakerPolicy().decide(context)

    assert command_kinds(commands) == (
        FundingCommandKind.CANCEL_MAKER,
        FundingCommandKind.RECONCILE,
        FundingCommandKind.PAUSE,
    )


def test_hedge_rejection_does_not_cancel_an_already_terminal_maker() -> None:
    context = policy_context(
        event_role=FundingOrderRole.HEDGE,
        event_kind=OrderEventKind.REJECTED,
        maker_terminal=True,
    )

    commands = PerpetualMakerSpotTakerPolicy().decide(context)

    assert command_kinds(commands) == (
        FundingCommandKind.RECONCILE,
        FundingCommandKind.PAUSE,
    )


def test_excess_unhedged_notional_stops_maker_and_hedges_exact_residual() -> None:
    context = policy_context(max_unhedged_notional="10")

    commands = PerpetualMakerSpotTakerPolicy().decide(context)

    assert command_kinds(commands) == (
        FundingCommandKind.CANCEL_MAKER,
        FundingCommandKind.SUBMIT_HEDGE,
    )
    assert commands[1].quantity == Decimal("0.2")


def test_terminal_dust_outside_tolerance_enters_recovery_not_open() -> None:
    context = policy_context(
        event_kind=OrderEventKind.CANCELED,
        maker_terminal=True,
        maker_remaining_quantity="0.58",
        hedge=hedge_decision(
            perpetual_filled_quantity="0.42",
            spot_confirmed_quantity="0.4",
            min_notional="5",
            delta_tolerance="0.001",
        ),
    )

    commands = PerpetualMakerSpotTakerPolicy().decide(context)

    assert command_kinds(commands) == (
        FundingCommandKind.RECONCILE,
        FundingCommandKind.RECOVER,
    )
    assert FundingCommandKind.MARK_OPEN not in command_kinds(commands)


def test_nonterminal_dust_waits_for_more_fill() -> None:
    context = policy_context(
        hedge=hedge_decision(
            perpetual_filled_quantity="0.42",
            spot_confirmed_quantity="0.4",
            min_notional="5",
            delta_tolerance="0.001",
        ),
    )

    assert PerpetualMakerSpotTakerPolicy().decide(context) == ()


def test_request_timeout_reconciles_and_pauses_without_resubmitting() -> None:
    context = policy_context(
        event_role=FundingOrderRole.HEDGE,
        event_kind=OrderEventKind.REQUEST_TIMED_OUT,
    )

    commands = PerpetualMakerSpotTakerPolicy().decide(context)

    assert command_kinds(commands) == (
        FundingCommandKind.RECONCILE,
        FundingCommandKind.PAUSE,
    )


def test_context_and_commands_are_immutable() -> None:
    context = policy_context()
    command = FundingPolicyCommand(
        kind=FundingCommandKind.SUBMIT_HEDGE,
        quantity="0.2",
    )

    with pytest.raises(FrozenInstanceError):
        context.session_status = "OPEN"
    with pytest.raises(FrozenInstanceError):
        command.quantity = Decimal("0.3")


def test_only_submit_hedge_commands_accept_a_quantity() -> None:
    with pytest.raises(ValueError, match="requires a quantity"):
        FundingPolicyCommand(kind=FundingCommandKind.SUBMIT_HEDGE)
    with pytest.raises(ValueError, match="cannot specify a quantity"):
        FundingPolicyCommand(
            kind=FundingCommandKind.MARK_OPEN,
            quantity="0.2",
        )
