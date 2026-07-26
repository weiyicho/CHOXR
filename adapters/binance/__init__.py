"""Binance adapter for the exchange-agnostic order engine."""

from .account_mode import AccountModeMismatch, verify_account_mode
from .config import BinanceAccountMode, BinanceConfig
from .gateways import (
    BinanceMarketDataGateway,
    ClassicPortfolioMarginAccountGateway,
    ClassicPortfolioMarginMarginTradingGateway,
    ClassicPortfolioMarginTradingRouter,
    ClassicPortfolioMarginUsdMTradingGateway,
    PortfolioMarginOrderEventStream,
)

__all__ = [
    "AccountModeMismatch",
    "BinanceAccountMode",
    "BinanceConfig",
    "BinanceMarketDataGateway",
    "ClassicPortfolioMarginAccountGateway",
    "ClassicPortfolioMarginMarginTradingGateway",
    "ClassicPortfolioMarginTradingRouter",
    "ClassicPortfolioMarginUsdMTradingGateway",
    "PortfolioMarginOrderEventStream",
    "verify_account_mode",
]
