"""Helpers for resolving account capital without exchange assumptions."""

from __future__ import annotations

from decimal import Decimal

from engine.domain.account import AccountSnapshot


def available_quote_capital(account: AccountSnapshot, quote_asset: str) -> Decimal:
    balance = account.find_balance(quote_asset)
    return balance.available if balance is not None else Decimal("0")
