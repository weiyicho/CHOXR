"""Binance adapter for the exchange-agnostic order engine."""

from .account_mode import AccountModeMismatch, verify_account_mode
from .config import BinanceAccountMode, BinanceConfig
from .gateways import (
    BinanceMarketDataGateway,
    ClassicPortfolioMarginAccountGateway,
    ClassicPortfolioMarginTradingGateway,
    PortfolioMarginOrderEventStream,
)

__all__ = [
    "AccountModeMismatch",
    "BinanceAccountMode",
    "BinanceConfig",
    "BinanceMarketDataGateway",
    "ClassicPortfolioMarginAccountGateway",
    "ClassicPortfolioMarginTradingGateway",
    "PortfolioMarginOrderEventStream",
    "verify_account_mode",
]
