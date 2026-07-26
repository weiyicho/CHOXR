import pytest

from adapters.binance import (
    AccountModeMismatch,
    BinanceAccountMode,
    BinanceConfig,
    BinanceMarketDataGateway,
    ClassicPortfolioMarginAccountGateway,
    ClassicPortfolioMarginMarginTradingGateway,
    ClassicPortfolioMarginTradingRouter,
    ClassicPortfolioMarginUsdMTradingGateway,
    PortfolioMarginOrderEventStream,
    verify_account_mode,
)


def test_pm_2_verifies_as_classic_portfolio_margin():
    assert verify_account_mode(
        BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN,
        {"accountType": "PM_2"},
    ) is BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN


def test_account_mode_mismatch_halts_instead_of_endpoint_fallback():
    with pytest.raises(AccountModeMismatch):
        verify_account_mode(
            BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN,
            {"accountType": "PM_1"},
        )


def test_classic_config_guard_and_public_gateway_exports():
    BinanceConfig("key", "secret").require_classic_portfolio_margin()
    with pytest.raises(ValueError):
        BinanceConfig(
            "key", "secret", BinanceAccountMode.REGULAR
        ).require_classic_portfolio_margin()

    assert BinanceMarketDataGateway
    assert ClassicPortfolioMarginAccountGateway
    assert ClassicPortfolioMarginMarginTradingGateway
    assert ClassicPortfolioMarginTradingRouter
    assert ClassicPortfolioMarginUsdMTradingGateway
    assert PortfolioMarginOrderEventStream
