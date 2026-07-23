from decimal import Decimal

import pytest

from engine.domain.account import AccountSnapshot, BalanceSnapshot
from engine.planning import (
    CapitalBudget,
    CapitalSizer,
    InsufficientCapital,
    QuantityCalculator,
)


def account(available: str) -> AccountSnapshot:
    return AccountSnapshot(
        venue="binance",
        balances=(BalanceSnapshot("USDT", available, available),),
        positions=(),
    )


def test_capital_sizer_uses_live_available_balance_reserve_and_fraction() -> None:
    allocation = CapitalSizer().size(
        account("800"),
        CapitalBudget(
            requested_notional="500",
            quote_asset="USDT",
            reserve="100",
            max_available_fraction="0.5",
        ),
    )

    assert allocation.available_balance == Decimal("800")
    assert allocation.spendable_balance == Decimal("700")
    assert allocation.approved_notional == Decimal("350.0")
    assert allocation.was_capped


def test_capital_sizer_fails_when_reserve_consumes_available_balance() -> None:
    with pytest.raises(InsufficientCapital):
        CapitalSizer().size(
            account("100"),
            CapitalBudget("50", "USDT", reserve="100"),
        )


def test_quantity_calculator_preserves_decimal_precision() -> None:
    quantity = QuantityCalculator().from_notional(
        Decimal("10"), Decimal("3")
    )
    assert quantity == Decimal("10") / Decimal("3")
