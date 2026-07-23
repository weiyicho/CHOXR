"""Read-only Binance Classic Portfolio Margin account preflight.

This module deliberately exposes only GET operations.  It never submits or
cancels orders, transfers assets, borrows, repays, or triggers fund collection.
Financial values and credentials are not printed.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from adapters.binance.account_mode import verify_account_mode
from adapters.binance.api import (
    PortfolioAccountProfileApi,
    PortfolioMarginApi,
    UsdMApi,
)
from adapters.binance.config import BinanceAccountMode, BinanceConfig
from adapters.binance.transport.clock import ServerClock
from adapters.binance.transport.rate_limit import RateLimitState
from adapters.binance.transport.rest_client import BinanceRestClient

from .settings import Settings


def _is_nonzero(value: object) -> bool:
    if value in {None, ""}:
        return False
    try:
        return Decimal(str(value)) != 0
    except InvalidOperation:
        return False


def _has_nonzero_balance(item: dict[str, Any]) -> bool:
    return any(
        _is_nonzero(item.get(field))
        for field in (
            "totalWalletBalance",
            "crossMarginFree",
            "crossMarginLocked",
            "crossMarginBorrowed",
            "crossMarginInterest",
            "umWalletBalance",
            "umUnrealizedPNL",
        )
    )


def read_masked_account_summary(settings: Settings) -> dict[str, object]:
    """Call documented read-only endpoints and return a non-financial summary."""

    settings.require_credentials()
    configured_mode = BinanceAccountMode(settings.binance_account_mode)
    config = BinanceConfig(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
        account_mode=configured_mode,
    )
    config.require_classic_portfolio_margin()

    clock = ServerClock()
    rate_limits = RateLimitState()
    spot_client = BinanceRestClient(
        config.spot_rest_url,
        config,
        clock=clock,
        rate_limits=rate_limits,
    )
    usd_m_client = BinanceRestClient(
        config.usd_m_rest_url,
        config,
        clock=clock,
        rate_limits=rate_limits,
    )
    portfolio_client = BinanceRestClient(
        config.portfolio_margin_rest_url,
        config,
        clock=clock,
        rate_limits=rate_limits,
    )

    usd_m_api = UsdMApi(usd_m_client)
    portfolio_api = PortfolioMarginApi(portfolio_client)
    profile_api = PortfolioAccountProfileApi(spot_client)

    def sync_clock() -> int:
        return clock.sync_from(usd_m_api.get_server_time)

    for client in (spot_client, usd_m_client, portfolio_client):
        client.set_clock_sync(sync_clock)

    # Synchronize before the signed reads.  The same callback performs one safe
    # recovery attempt if Binance later responds with timestamp error -1021.
    sync_clock()

    profile = profile_api.get_account_profile()
    observed_mode = verify_account_mode(configured_mode, profile)
    account = portfolio_api.get_account()
    balances = portfolio_api.get_balances()
    positions = portfolio_api.get_um_positions()
    position_mode = portfolio_api.get_um_position_mode()

    return {
        "account_type": str(profile.get("accountType", "UNKNOWN")),
        "observed_account_mode": observed_mode.value,
        "account_status": str(account.get("accountStatus", "UNKNOWN")),
        "account_equity_field_present": account.get("accountEquity") not in {None, ""},
        "available_balance_field_present": account.get("totalAvailableBalance")
        not in {None, ""},
        "balance_record_count": len(balances),
        "nonzero_balance_record_count": sum(
            _has_nonzero_balance(item) for item in balances
        ),
        "um_position_record_count": len(positions),
        "open_um_position_count": sum(
            _is_nonzero(item.get("positionAmt")) for item in positions
        ),
        "position_mode": (
            "HEDGE"
            if bool(position_mode.get("dualSidePosition"))
            else "ONE_WAY"
        ),
        "read_only": True,
        "financial_values_redacted": True,
    }


def main() -> int:
    summary = read_masked_account_summary(Settings.from_environment())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
