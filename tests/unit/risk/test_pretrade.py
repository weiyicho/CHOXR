from decimal import Decimal

import pytest

from engine.domain.account import AccountSnapshot, BalanceSnapshot
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderType, Side, TimeInForce
from engine.risk import (
    PreTradeRiskCheck,
    PreTradeRiskRejected,
    RiskContext,
    RiskLimits,
)


def account(available: str = "1000", venue: str = "binance") -> AccountSnapshot:
    return AccountSnapshot(
        venue=venue,
        balances=(BalanceSnapshot("USDT", available, available),),
        positions=(),
    )


def intent(venue: str = "binance") -> OrderIntent:
    return OrderIntent(
        execution_id="execution-1",
        client_order_id="execution-1-order-1",
        instrument=InstrumentId(venue, "SPOT", "ETHUSDT"),
        side=Side.BUY,
        quantity="2",
        order_type=OrderType.LIMIT,
        price="100",
        time_in_force=TimeInForce.GTC,
        post_only=True,
    )


def test_safe_order_is_approved_with_projected_exposure() -> None:
    decision = PreTradeRiskCheck().evaluate(
        intent(),
        RiskContext(
            account(),
            "USDT",
            current_gross_notional="500",
            current_instrument_notional="100",
        ),
        RiskLimits(
            max_order_notional="300",
            max_gross_notional="1000",
            max_instrument_notional="500",
            max_available_capital_fraction="0.5",
            min_remaining_available_capital="500",
            allowed_venues=("binance",),
            allowed_markets=("SPOT",),
        ),
    )

    assert decision.approved
    assert decision.order_notional == Decimal("200")
    assert decision.projected_gross_notional == Decimal("700")
    assert decision.projected_instrument_notional == Decimal("300")


def test_order_can_fail_multiple_limits_in_one_auditable_decision() -> None:
    decision = PreTradeRiskCheck().evaluate(
        intent(),
        RiskContext(account("250"), "USDT", current_gross_notional="500"),
        RiskLimits(
            max_order_notional="150",
            max_gross_notional="650",
            max_available_capital_fraction="0.5",
            min_remaining_available_capital="100",
        ),
    )

    assert not decision.approved
    assert set(decision.violation_codes) == {
        "MAX_ORDER_NOTIONAL",
        "MAX_GROSS_NOTIONAL",
        "AVAILABLE_CAPITAL_FRACTION",
        "MIN_REMAINING_CAPITAL",
    }


def test_reducing_exposure_does_not_require_new_capital() -> None:
    decision = PreTradeRiskCheck().evaluate(
        intent(),
        RiskContext(
            account("10"),
            "USDT",
            current_gross_notional="500",
            current_instrument_notional="300",
            increases_exposure=False,
        ),
        RiskLimits(min_remaining_available_capital="10"),
    )

    assert decision.approved
    assert decision.required_capital == Decimal("0")
    assert decision.projected_gross_notional == Decimal("300")


def test_account_venue_mismatch_fails_closed() -> None:
    decision = PreTradeRiskCheck().evaluate(
        intent("bybit"), RiskContext(account(), "USDT"), RiskLimits()
    )
    assert decision.violation_codes == ("ACCOUNT_VENUE_MISMATCH",)


def test_require_approved_raises_with_violation_codes() -> None:
    with pytest.raises(PreTradeRiskRejected, match="MAX_ORDER_NOTIONAL"):
        PreTradeRiskCheck().require_approved(
            intent(),
            RiskContext(account(), "USDT"),
            RiskLimits(max_order_notional="100"),
        )
