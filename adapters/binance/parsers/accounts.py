from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import AccountSnapshot, BalanceSnapshot, FundingIncomeSnapshot


def _decimal(payload: dict[str, Any], *keys: str, default: str = "0") -> Decimal:
    for key in keys:
        if key in payload and payload[key] not in {None, ""}:
            return Decimal(str(payload[key]))
    return Decimal(default)


def parse_account(payload: dict[str, Any]) -> AccountSnapshot:
    return AccountSnapshot(
        account_equity=_decimal(payload, "accountEquity", "totalEquity"),
        actual_equity=_decimal(payload, "actualEquity", "accountEquity"),
        available_balance=_decimal(
            payload, "totalAvailableBalance", "availableBalance"
        ),
        initial_margin=_decimal(payload, "accountInitialMargin", "totalInitialMargin"),
        maintenance_margin=_decimal(
            payload, "accountMaintMargin", "totalMaintMargin"
        ),
        uni_mmr=_decimal(payload, "uniMMR"),
        account_status=(
            str(payload["accountStatus"]) if "accountStatus" in payload else None
        ),
    )


def parse_balances(payloads: list[dict[str, Any]]) -> tuple[BalanceSnapshot, ...]:
    return tuple(
        BalanceSnapshot(
            asset=str(item["asset"]),
            total_wallet_balance=_decimal(item, "totalWalletBalance"),
            cross_margin_free=_decimal(item, "crossMarginFree"),
            cross_margin_locked=_decimal(item, "crossMarginLocked"),
            cross_margin_borrowed=_decimal(item, "crossMarginBorrowed"),
            cross_margin_interest=_decimal(item, "crossMarginInterest"),
            um_wallet_balance=_decimal(item, "umWalletBalance"),
            um_unrealized_pnl=_decimal(item, "umUnrealizedPNL", "umUnrealizedProfit"),
            update_time_ms=(
                int(item["updateTime"]) if item.get("updateTime") is not None else None
            ),
        )
        for item in payloads
    )


def parse_funding_income(
    payloads: list[dict[str, Any]],
) -> tuple[FundingIncomeSnapshot, ...]:
    parsed: list[FundingIncomeSnapshot] = []
    for item in payloads:
        income_type = str(item.get("incomeType", ""))
        if income_type != "FUNDING_FEE":
            continue
        transaction = item.get("tranId")
        parsed.append(
            FundingIncomeSnapshot(
                symbol=str(item.get("symbol", "")),
                asset=str(item.get("asset", "")),
                income_type=income_type,
                income=_decimal(item, "income"),
                time_ms=int(item["time"]),
                transaction_id=str(transaction) if transaction is not None else None,
                trade_id=(
                    str(item["tradeId"]) if item.get("tradeId") not in {None, ""} else None
                ),
                info=str(item["info"]) if item.get("info") else None,
            )
        )
    return tuple(parsed)
