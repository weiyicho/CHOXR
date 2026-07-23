"""Explicit Binance connection settings.

The adapter never reads environment variables itself.  The application layer is
responsible for loading secrets and injecting this configuration, which keeps
tests from accidentally touching a live account.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BinanceAccountMode(str, Enum):
    REGULAR = "REGULAR"
    CLASSIC_PORTFOLIO_MARGIN = "CLASSIC_PORTFOLIO_MARGIN"
    PORTFOLIO_MARGIN_PRO = "PORTFOLIO_MARGIN_PRO"


SPOT_REST_URL = "https://api.binance.com"
USD_M_REST_URL = "https://fapi.binance.com"
PORTFOLIO_MARGIN_REST_URL = "https://papi.binance.com"
PORTFOLIO_MARGIN_STREAM_URL = "wss://fstream.binance.com/pm"


@dataclass(frozen=True, slots=True)
class BinanceConfig:
    api_key: str
    api_secret: str
    account_mode: BinanceAccountMode = BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN
    timeout_seconds: float = 5.0
    recv_window_ms: int = 5_000
    spot_rest_url: str = SPOT_REST_URL
    usd_m_rest_url: str = USD_M_REST_URL
    portfolio_margin_rest_url: str = PORTFOLIO_MARGIN_REST_URL
    portfolio_margin_stream_url: str = PORTFOLIO_MARGIN_STREAM_URL

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1 <= self.recv_window_ms <= 60_000:
            raise ValueError("recv_window_ms must be between 1 and 60000")
        for name in ("spot_rest_url", "usd_m_rest_url", "portfolio_margin_rest_url"):
            if not getattr(self, name).startswith("https://"):
                raise ValueError(f"{name} must use https")
        if not self.portfolio_margin_stream_url.startswith("wss://"):
            raise ValueError("portfolio_margin_stream_url must use wss")

    def require_classic_portfolio_margin(self) -> None:
        if self.account_mode is not BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN:
            raise ValueError(
                "Classic Portfolio Margin adapter requires "
                "BINANCE_ACCOUNT_MODE=CLASSIC_PORTFOLIO_MARGIN"
            )
