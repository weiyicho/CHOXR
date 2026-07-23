"""Thin wrappers around documented Binance REST resources."""

from .account_profile import PortfolioAccountProfileApi
from .portfolio_margin import PortfolioMarginApi
from .spot_api import SpotApi
from .usd_m_api import UsdMApi
from .user_stream import PortfolioMarginUserStreamApi

__all__ = [
    "PortfolioMarginApi",
    "PortfolioAccountProfileApi",
    "PortfolioMarginUserStreamApi",
    "SpotApi",
    "UsdMApi",
]
