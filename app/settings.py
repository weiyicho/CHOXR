"""Environment-backed application settings with live trading disabled by default."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    binance_api_key: str
    binance_api_secret: str
    binance_account_mode: str = "CLASSIC_PORTFOLIO_MARGIN"
    live_trading_enabled: bool = False
    discord_webhook_url: str = ""
    discord_notifications_enabled: bool = False
    funding_scan_interval_seconds: float = 300.0
    funding_summary_interval_seconds: float = 1_800.0
    funding_min_annualized_rate: Decimal = Decimal("0.10")
    funding_min_quote_volume_24h: Decimal = Decimal("3000000")
    funding_top_n: int = 10

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "funding_min_annualized_rate",
            Decimal(str(self.funding_min_annualized_rate)),
        )
        object.__setattr__(
            self,
            "funding_min_quote_volume_24h",
            Decimal(str(self.funding_min_quote_volume_24h)),
        )
        if self.funding_scan_interval_seconds <= 0:
            raise ValueError("funding_scan_interval_seconds must be positive")
        if self.funding_summary_interval_seconds <= 0:
            raise ValueError("funding_summary_interval_seconds must be positive")
        if self.funding_min_annualized_rate < 0:
            raise ValueError("funding_min_annualized_rate cannot be negative")
        if self.funding_min_quote_volume_24h < 0:
            raise ValueError("funding_min_quote_volume_24h cannot be negative")
        if not 1 <= self.funding_top_n <= 10:
            raise ValueError("funding_top_n must be between 1 and 10")

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            binance_api_key=os.getenv("BINANCE_API_KEY", ""),
            binance_api_secret=os.getenv("BINANCE_API_SECRET", ""),
            binance_account_mode=os.getenv(
                "BINANCE_ACCOUNT_MODE", "CLASSIC_PORTFOLIO_MARGIN"
            ),
            live_trading_enabled=_truthy(os.getenv("CHOXR_LIVE_TRADING")),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL", ""),
            discord_notifications_enabled=_truthy(
                os.getenv("CHOXR_DISCORD_NOTIFICATIONS")
            ),
            funding_scan_interval_seconds=float(
                os.getenv("CHOXR_FUNDING_SCAN_INTERVAL_SECONDS", "300")
            ),
            funding_summary_interval_seconds=float(
                os.getenv("CHOXR_FUNDING_SUMMARY_INTERVAL_SECONDS", "1800")
            ),
            funding_min_annualized_rate=Decimal(
                os.getenv("CHOXR_FUNDING_MIN_ANNUALIZED_RATE", "0.10")
            ),
            funding_min_quote_volume_24h=Decimal(
                os.getenv("CHOXR_FUNDING_MIN_QUOTE_VOLUME_24H", "3000000")
            ),
            funding_top_n=int(os.getenv("CHOXR_FUNDING_TOP_N", "10")),
        )

    def require_credentials(self) -> None:
        if not self.binance_api_key or not self.binance_api_secret:
            raise RuntimeError("Binance API credentials are not configured")

    def require_live_trading(self) -> None:
        if not self.live_trading_enabled:
            raise RuntimeError(
                "live trading is disabled; set CHOXR_LIVE_TRADING=true explicitly"
            )
