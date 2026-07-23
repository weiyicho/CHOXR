"""Environment-backed application settings with live trading disabled by default."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    binance_api_key: str
    binance_api_secret: str
    binance_account_mode: str = "CLASSIC_PORTFOLIO_MARGIN"
    live_trading_enabled: bool = False

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            binance_api_key=os.getenv("BINANCE_API_KEY", ""),
            binance_api_secret=os.getenv("BINANCE_API_SECRET", ""),
            binance_account_mode=os.getenv(
                "BINANCE_ACCOUNT_MODE", "CLASSIC_PORTFOLIO_MARGIN"
            ),
            live_trading_enabled=_truthy(os.getenv("CHOXR_LIVE_TRADING")),
        )

    def require_credentials(self) -> None:
        if not self.binance_api_key or not self.binance_api_secret:
            raise RuntimeError("Binance API credentials are not configured")

    def require_live_trading(self) -> None:
        if not self.live_trading_enabled:
            raise RuntimeError(
                "live trading is disabled; set CHOXR_LIVE_TRADING=true explicitly"
            )
