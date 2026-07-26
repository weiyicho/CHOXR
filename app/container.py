"""Application composition root for Classic Binance Portfolio Margin."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from adapters.binance.api import (
    PortfolioMarginApi,
    PortfolioAccountProfileApi,
    PortfolioMarginUserStreamApi,
    SpotApi,
    UsdMApi,
)
from adapters.binance.config import BinanceAccountMode, BinanceConfig
from adapters.binance.gateways import (
    BinanceMarketDataGateway,
    ClassicPortfolioMarginAccountGateway,
    ClassicPortfolioMarginMarginTradingGateway,
    ClassicPortfolioMarginTradingRouter,
    ClassicPortfolioMarginUsdMTradingGateway,
    PortfolioMarginOrderEventStream,
)
from adapters.binance.transport.clock import ServerClock
from adapters.binance.transport.rate_limit import RateLimitState
from adapters.binance.transport.rest_client import BinanceRestClient
from adapters.discord_notifier import DiscordNotifier
from adapters.persistence import (
    SqliteAtomicOrderPersistence,
    SqliteOrderEventRepository,
    SqliteOrderRepository,
)
from engine.execution import OrderExecutionService
from engine.ports.trading_gateway import TradingGateway

from .safety import LiveAccountGuard, LiveTradingGuard
from .settings import Settings


@dataclass(frozen=True)
class ApplicationContainer:
    settings: Settings
    trading_gateway: TradingGateway
    market_data_gateway: BinanceMarketDataGateway
    account_gateway: LiveAccountGuard
    order_event_stream: PortfolioMarginOrderEventStream
    order_repository: SqliteOrderRepository
    order_event_repository: SqliteOrderEventRepository
    atomic_order_persistence: SqliteAtomicOrderPersistence
    execution_service: OrderExecutionService
    discord_notifier: DiscordNotifier


def build_binance_container(
    settings: Settings,
    *,
    database_path: str | Path,
) -> ApplicationContainer:
    """Construct dependencies without starting a stream or sending a request."""

    settings.require_credentials()
    account_mode = BinanceAccountMode(settings.binance_account_mode)
    if account_mode is not BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN:
        raise ValueError("the first live adapter supports Classic Portfolio Margin")

    config = BinanceConfig(
        api_key=settings.binance_api_key,
        api_secret=settings.binance_api_secret,
        account_mode=account_mode,
    )
    shared_clock = ServerClock()
    shared_rate_limits = RateLimitState()
    spot_client = BinanceRestClient(
        config.spot_rest_url,
        config,
        clock=shared_clock,
        rate_limits=shared_rate_limits,
    )
    usd_m_client = BinanceRestClient(
        config.usd_m_rest_url,
        config,
        clock=shared_clock,
        rate_limits=shared_rate_limits,
    )
    portfolio_client = BinanceRestClient(
        config.portfolio_margin_rest_url,
        config,
        clock=shared_clock,
        rate_limits=shared_rate_limits,
    )

    spot_api = SpotApi(spot_client)
    usd_m_api = UsdMApi(usd_m_client)
    portfolio_api = PortfolioMarginApi(portfolio_client)

    def sync_clock() -> int:
        return shared_clock.sync_from(usd_m_api.get_server_time)

    # SAPI account-profile reads are sent by ``spot_client`` and occur before
    # the first PAPI read during startup.  Every client that can issue a signed
    # request therefore needs the same -1021 recovery callback.
    for client in (spot_client, usd_m_client, portfolio_client):
        client.set_clock_sync(sync_clock)

    market_data = BinanceMarketDataGateway(spot_api, usd_m_api)
    margin_trading = ClassicPortfolioMarginMarginTradingGateway(portfolio_api)
    usd_m_trading = ClassicPortfolioMarginUsdMTradingGateway(portfolio_api)
    raw_trading = ClassicPortfolioMarginTradingRouter(
        margin_gateway=margin_trading,
        usd_m_gateway=usd_m_trading,
    )
    trading = LiveTradingGuard(raw_trading, settings)
    account_profile_api = PortfolioAccountProfileApi(spot_client)
    raw_account = ClassicPortfolioMarginAccountGateway(
        portfolio_api,
        market_data,
        account_profile_api,
    )
    account = LiveAccountGuard(raw_account, settings)
    stream_api = PortfolioMarginUserStreamApi(portfolio_client)
    order_stream = PortfolioMarginOrderEventStream(
        stream_api,
        config.portfolio_margin_stream_url,
    )

    order_repository = SqliteOrderRepository(database_path)
    event_repository = SqliteOrderEventRepository(database_path)
    atomic_persistence = SqliteAtomicOrderPersistence(database_path)
    execution_service = OrderExecutionService(
        trading,
        order_repository,
        event_repository=event_repository,
        atomic_persistence=atomic_persistence,
    )
    discord_notifier = DiscordNotifier(
        settings.discord_webhook_url,
        enabled=settings.discord_notifications_enabled,
    )
    return ApplicationContainer(
        settings=settings,
        trading_gateway=trading,
        market_data_gateway=market_data,
        account_gateway=account,
        order_event_stream=order_stream,
        order_repository=order_repository,
        order_event_repository=event_repository,
        atomic_order_persistence=atomic_persistence,
        execution_service=execution_service,
        discord_notifier=discord_notifier,
    )
