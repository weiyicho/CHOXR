from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

import strategies.funding_rate.monitor as monitor_module
from strategies.funding_rate.monitor import (
    FundingRateMonitor,
    FundingScanReport,
    build_funding_order_plan,
    build_funding_rate_monitor,
    render_console_report,
    render_funding_table_image,
    write_funding_order_plan,
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

    def send_picture(
        self,
        picture_path: str | Path,
        username: str | None = None,
    ) -> bool:
        path = Path(picture_path)
        self.calls.append(
            {
                "filename": path.name,
                "content": path.read_bytes(),
                "username": username,
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


def test_console_report_contains_monitor_values() -> None:
    report = FundingScanReport(
        scanned_at=NOW,
        scanned_symbol_count=20,
        candidates=(candidate(),),
    )

    rendered = render_console_report(report)

    assert "CHOXR Funding Monitor — Binance" in rendered
    assert "顯示候選：1 / 掃描 20" in rendered
    assert "Symbol" in rendered
    assert "Funding/Int" in rendered
    assert "Annual" in rendered
    assert "24h Vol" in rendered
    assert "ETHUSDT" in rendered
    assert "0.0200%/8h" in rendered
    assert "21.90%" in rendered
    assert "$50.0M" in rendered
    assert "+0.250%" in rendered
    assert "01/01 16:00" in rendered


def test_funding_table_image_is_valid_png(tmp_path: Path) -> None:
    report = FundingScanReport(
        scanned_at=NOW,
        scanned_symbol_count=20,
        candidates=(candidate(),),
    )
    image_path = tmp_path / "funding.png"

    assert render_funding_table_image(
        report,
        image_path,
        settings=settings(),
    ) == image_path

    with Image.open(image_path) as image:
        assert image.format == "PNG"
        assert image.size == (1_400, 474)


def test_notification_is_sent_for_every_scan_report() -> None:
    notifier = FakeNotifier()
    monitor = FundingRateMonitor(
        spot_api=FakeSpotApi(),
        usd_m_api=FakeUsdMApi(),
        market_data_gateway=FakeMarketDataGateway(),
        notifier=notifier,
        settings=settings(),
        now=lambda: NOW,
    )
    report = FundingScanReport(NOW, 20, (candidate(),))

    assert monitor.notify(report) is True
    assert monitor.notify(report) is True
    assert len(notifier.calls) == 2
    assert notifier.calls[0]["filename"] == "funding-opportunities.png"
    assert notifier.calls[0]["content"].startswith(b"\x89PNG")


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

    assert monitor.notify(FundingScanReport(NOW, 0, ())) is False
    assert notifier.calls == []


def test_order_plan_selects_best_executable_candidate_and_sizes_both_legs() -> None:
    report = FundingScanReport(
        scanned_at=NOW,
        scanned_symbol_count=20,
        candidates=(candidate(),),
    )

    plan = build_funding_order_plan(
        report,
        available_capital="50",
        futures_leverage="5",
    )

    assert plan["status"] == "READY"
    assert plan["selected_symbols"] == ["ETHUSDT"]
    assert plan["candidate"]["rank"] == 1
    allocation = plan["allocation"]
    spot = allocation["spot_leg"]
    perpetual = allocation["perpetual_leg"]
    assert spot["side"] == "BUY"
    assert perpetual["side"] == "SELL"
    assert spot["quantity"] == perpetual["quantity"]
    assert Decimal(spot["notional"]) + Decimal(
        perpetual["initial_margin"]
    ) == Decimal("50")
    assert Decimal(spot["notional"]) == (
        Decimal(spot["quantity"]) * Decimal("100")
    )
    assert Decimal(perpetual["notional"]) == (
        Decimal(perpetual["quantity"]) * Decimal("100.25")
    )


def test_order_plan_skips_candidate_without_executable_prices() -> None:
    unavailable = replace(
        candidate(),
        symbol="BTCUSDT",
        spot_ask=None,
        perpetual_bid=None,
    )
    report = FundingScanReport(
        scanned_at=NOW,
        scanned_symbol_count=20,
        candidates=(unavailable, candidate()),
        basis_error_count=1,
    )

    plan = build_funding_order_plan(report)

    assert plan["status"] == "READY"
    assert plan["selected_symbols"] == ["ETHUSDT"]
    assert plan["candidate"]["rank"] == 2


def test_no_candidate_plan_replaces_previous_ready_plan(
    tmp_path: Path,
) -> None:
    output_path = (
        tmp_path
        / "strategies"
        / "funding_rate"
        / "runtime"
        / "order_plan.json"
    )
    ready = build_funding_order_plan(
        FundingScanReport(NOW, 20, (candidate(),))
    )
    no_candidate = build_funding_order_plan(
        FundingScanReport(NOW, 20, ())
    )

    write_funding_order_plan(ready, output_path)
    write_funding_order_plan(no_candidate, output_path)

    stored = json.loads(output_path.read_text(encoding="utf-8"))
    assert stored["status"] == "NO_CANDIDATE"
    assert stored["selected_symbols"] == []
    assert stored["candidate"] is None
    assert stored["allocation"] is None
    assert list(output_path.parent.glob("*.tmp")) == []


def test_monitor_uses_configured_capital_and_leverage_in_saved_plan(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "order_plan.json"
    monitor = FundingRateMonitor(
        spot_api=FakeSpotApi(),
        usd_m_api=FakeUsdMApi(),
        market_data_gateway=FakeMarketDataGateway(),
        notifier=FakeNotifier(enabled=False),
        settings=settings(
            funding_capital=Decimal("75"),
            funding_leverage=3,
        ),
        now=lambda: NOW,
        order_plan_path=output_path,
    )

    monitor.save_order_plan(FundingScanReport(NOW, 20, (candidate(),)))

    stored = json.loads(output_path.read_text(encoding="utf-8"))
    assert stored["allocation"]["capital"]["deployed"] == "75"
    assert stored["allocation"]["perpetual_leg"]["leverage"] == "3"


def test_retry_delay_is_exponential_and_capped_at_scan_interval() -> None:
    assert FundingRateMonitor.retry_delay_seconds(1, max_delay=300) == 30
    assert FundingRateMonitor.retry_delay_seconds(2, max_delay=300) == 60
    assert FundingRateMonitor.retry_delay_seconds(5, max_delay=300) == 300
    assert FundingRateMonitor.retry_delay_seconds(8, max_delay=300) == 300


def test_public_monitor_builder_does_not_require_binance_credentials() -> None:
    monitor = build_funding_rate_monitor(settings())

    assert monitor.notifier_enabled is False


def test_default_order_plan_path_is_inside_funding_strategy() -> None:
    assert monitor_module.DEFAULT_ORDER_PLAN_PATH == (
        Path(monitor_module.__file__).resolve().parent
        / "runtime"
        / "order_plan.json"
    )


def test_once_loads_dotenv_and_sends_enabled_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    report = FundingScanReport(NOW, 0, ())

    class FakeCliMonitor:
        notifier_enabled = True

        def scan_once(self) -> FundingScanReport:
            events.append("scan")
            return report

        def save_order_plan(self, actual_report: FundingScanReport) -> Path:
            assert actual_report is report
            events.append("save_plan")
            return Path("/tmp/order_plan.json")

        def notify(self, actual_report: FundingScanReport) -> bool:
            assert actual_report is report
            events.append("notify")
            return True

    monkeypatch.setattr(
        monitor_module,
        "load_dotenv",
        lambda: events.append("load_dotenv"),
    )
    monkeypatch.setattr(
        monitor_module.Settings,
        "from_environment",
        classmethod(lambda cls: events.append("settings") or settings()),
    )
    monkeypatch.setattr(
        monitor_module,
        "build_funding_rate_monitor",
        lambda actual_settings: (
            events.append("build") or FakeCliMonitor()
        ),
    )

    assert monitor_module.main(["--once"]) == 0
    assert events == [
        "load_dotenv",
        "settings",
        "build",
        "scan",
        "save_plan",
        "notify",
    ]
    output = capsys.readouterr().out
    assert "Order plan: /tmp/order_plan.json" in output
    assert "Discord report: sent" in output
