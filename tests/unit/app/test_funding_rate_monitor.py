from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.funding_rate_monitor import (
    FundingRateMonitor,
    FundingScanReport,
    build_funding_rate_monitor,
    discord_summary,
)
from app.settings import Settings
from engine.domain.instrument import (
    InstrumentId,
    OrderBookLevel,
    OrderBookSnapshot,
)
from strategies.funding_rate import FundingCandidate


NOW = datetime(2027, 1, 1, tzinfo=timezone.utc)


class FakeSpotApi:
    def __init__(self) -> None:
        self.exchange_info_calls = 0

    def get_exchange_info(self):
        self.exchange_info_calls += 1
        return {
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                },
                {
                    "symbol": "BTCUSDC",
                    "status": "TRADING",
                    "quoteAsset": "USDC",
                },
            ]
        }


class FakeUsdMApi:
    def __init__(self) -> None:
        self.exchange_info_calls = 0

    def get_exchange_info(self):
        self.exchange_info_calls += 1
        return {
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                },
                {
                    "symbol": "DELIVERYUSDT",
                    "status": "TRADING",
                    "quoteAsset": "USDT",
                    "contractType": "CURRENT_QUARTER",
                },
            ]
        }

    def get_premium_index(self):
        return [
            {
                "symbol": "ETHUSDT",
                "markPrice": "101",
                "indexPrice": "100",
                "lastFundingRate": "0.00020",
                "nextFundingTime": 1_800_000_000_000,
            }
        ]

    def get_funding_rate_info(self):
        return []

    def get_24h_tickers(self):
        return [{"symbol": "ETHUSDT", "quoteVolume": "50000000"}]


class FakeMarketDataGateway:
    def __init__(self) -> None:
        self.calls: list[InstrumentId] = []

    def get_order_book(self, instrument: InstrumentId, depth: int | None = None):
        self.calls.append(instrument)
        if instrument.market == "MARGIN":
            bids = (OrderBookLevel("99.9", "10"),)
            asks = (OrderBookLevel("100", "10"),)
        else:
            bids = (OrderBookLevel("100.25", "10"),)
            asks = (OrderBookLevel("100.5", "10"),)
        return OrderBookSnapshot(instrument, bids=bids, asks=asks)


class FakeNotifier:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.calls: list[dict[str, object]] = []

    def send_embed(
        self,
        title: str,
        description: str = "",
        color: int = 0,
        fields=None,
    ) -> bool:
        self.calls.append(
            {
                "title": title,
                "description": description,
                "color": color,
                "fields": fields,
            }
        )
        return True


def settings(**kwargs: object) -> Settings:
    return Settings(
        binance_api_key="",
        binance_api_secret="",
        funding_min_annualized_rate=Decimal("0.10"),
        funding_min_quote_volume_24h=Decimal("3000000"),
        **kwargs,
    )


def candidate() -> FundingCandidate:
    return FundingCandidate(
        symbol="ETHUSDT",
        funding_rate="0.00020",
        funding_interval_hours=8,
        next_funding_at=datetime(2027, 1, 1, 8, tzinfo=timezone.utc),
        mark_price="101",
        index_price="100",
        quote_volume_24h="50000000",
        spot_ask="100",
        perpetual_bid="100.25",
    )


def test_scan_once_filters_universe_and_enriches_executable_basis() -> None:
    spot_api = FakeSpotApi()
    usd_m_api = FakeUsdMApi()
    market_data = FakeMarketDataGateway()
    monitor = FundingRateMonitor(
        spot_api=spot_api,
        usd_m_api=usd_m_api,
        market_data_gateway=market_data,
        notifier=FakeNotifier(),
        settings=settings(),
        now=lambda: NOW,
    )

    report = monitor.scan_once()
    monitor.scan_once()

    assert report.scanned_symbol_count == 1
    assert [item.symbol for item in report.candidates] == ["ETHUSDT"]
    assert report.candidates[0].entry_basis_pct == Decimal("0.0025")
    assert [item.market for item in market_data.calls[:2]] == [
        "MARGIN",
        "USD_M_PERPETUAL",
    ]
    assert spot_api.exchange_info_calls == 1
    assert usd_m_api.exchange_info_calls == 1


def test_discord_summary_contains_monitor_values() -> None:
    report = FundingScanReport(
        scanned_at=NOW,
        scanned_symbol_count=20,
        candidates=(candidate(),),
    )

    title, description, color, fields = discord_summary(report)

    assert title == "CHOXR Funding Monitor — Binance"
    assert "顯示候選：1 / 掃描 20" in description
    assert color == 0x2ECC71
    assert fields[0]["name"] == "#1 ETHUSDT"
    assert "簡單年化：21.90%" in fields[0]["value"]
    assert "進場 basis：+0.250%" in fields[0]["value"]


def test_notification_is_sent_on_change_and_periodic_heartbeat_only() -> None:
    notifier = FakeNotifier()
    monitor = FundingRateMonitor(
        spot_api=FakeSpotApi(),
        usd_m_api=FakeUsdMApi(),
        market_data_gateway=FakeMarketDataGateway(),
        notifier=notifier,
        settings=settings(funding_summary_interval_seconds=1_800),
        now=lambda: NOW,
    )
    first = FundingScanReport(NOW, 20, (candidate(),))
    unchanged = FundingScanReport(NOW + timedelta(minutes=5), 20, (candidate(),))
    heartbeat = FundingScanReport(NOW + timedelta(minutes=31), 20, (candidate(),))

    assert monitor.notify_if_due(first) is True
    assert monitor.notify_if_due(unchanged) is False
    assert monitor.notify_if_due(heartbeat) is True
    assert len(notifier.calls) == 2


def test_disabled_notifier_never_sends() -> None:
    notifier = FakeNotifier(enabled=False)
    monitor = FundingRateMonitor(
        spot_api=FakeSpotApi(),
        usd_m_api=FakeUsdMApi(),
        market_data_gateway=FakeMarketDataGateway(),
        notifier=notifier,
        settings=settings(),
        now=lambda: NOW,
    )

    assert monitor.notify_if_due(FundingScanReport(NOW, 0, ())) is False
    assert notifier.calls == []


def test_retry_delay_is_exponential_and_capped_at_scan_interval() -> None:
    assert FundingRateMonitor.retry_delay_seconds(1, max_delay=300) == 30
    assert FundingRateMonitor.retry_delay_seconds(2, max_delay=300) == 60
    assert FundingRateMonitor.retry_delay_seconds(5, max_delay=300) == 300
    assert FundingRateMonitor.retry_delay_seconds(8, max_delay=300) == 300


def test_public_monitor_builder_does_not_require_binance_credentials() -> None:
    monitor = build_funding_rate_monitor(settings())

    assert monitor.notifier_enabled is False
