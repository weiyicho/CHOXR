"""Account-aware capital sizing."""

from __future__ import annotations

from decimal import Decimal

from engine.domain.account import AccountSnapshot

from .models import CapitalAllocation, CapitalBudget, ZERO


class InsufficientCapital(ValueError):
    """The account cannot fund any valid part of the requested budget."""


class CapitalSizer:
    """Cap a strategy budget using current available account capital."""

    def size(
        self, account: AccountSnapshot, budget: CapitalBudget
    ) -> CapitalAllocation:
        balance = account.find_balance(budget.quote_asset)
        available = balance.available if balance is not None else Decimal("0")
        spendable = max(ZERO, available - budget.reserve)
        account_cap = spendable * budget.max_available_fraction
        approved = min(budget.requested_notional, account_cap)

        if approved <= ZERO:
            raise InsufficientCapital(
                f"no {budget.quote_asset} capital is available after reserve"
            )

        return CapitalAllocation(
            requested_notional=budget.requested_notional,
            available_balance=available,
            spendable_balance=spendable,
            approved_notional=approved,
        )
