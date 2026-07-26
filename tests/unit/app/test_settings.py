from decimal import Decimal

import pytest

from app.settings import Settings


def test_live_trading_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHOXR_LIVE_TRADING", raising=False)
    settings = Settings.from_environment()

    assert settings.live_trading_enabled is False
    with pytest.raises(RuntimeError, match="live trading is disabled"):
        settings.require_live_trading()


def test_discord_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DISCORD_WEBHOOK_URL",
        "https://discord.com/api/webhooks/example/token",
    )
    monkeypatch.setenv("CHOXR_DISCORD_NOTIFICATIONS", "true")

    settings = Settings.from_environment()

    assert settings.discord_webhook_url.endswith("/example/token")
    assert settings.discord_notifications_enabled is True


def test_funding_monitor_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHOXR_FUNDING_SCAN_INTERVAL_SECONDS", "60")
    monkeypatch.setenv("CHOXR_FUNDING_MIN_ANNUALIZED_RATE", "0.15")
    monkeypatch.setenv("CHOXR_FUNDING_MIN_QUOTE_VOLUME_24H", "5000000")
    monkeypatch.setenv("CHOXR_FUNDING_TOP_N", "5")
    monkeypatch.setenv("CHOXR_FUNDING_CAPITAL", "75.5")
    monkeypatch.setenv("CHOXR_FUNDING_LEVERAGE", "4")

    settings = Settings.from_environment()

    assert settings.funding_scan_interval_seconds == 60
    assert settings.funding_min_annualized_rate == Decimal("0.15")
    assert settings.funding_min_quote_volume_24h == Decimal("5000000")
    assert settings.funding_top_n == 5
    assert settings.funding_capital == Decimal("75.5")
    assert settings.funding_leverage == 4


def test_funding_monitor_scans_hourly_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CHOXR_FUNDING_SCAN_INTERVAL_SECONDS", raising=False)

    settings = Settings.from_environment()

    assert settings.funding_scan_interval_seconds == 3_600


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"funding_scan_interval_seconds": 0}, "scan_interval"),
        ({"funding_min_annualized_rate": "-0.1"}, "annualized_rate"),
        ({"funding_min_quote_volume_24h": "-1"}, "quote_volume"),
        ({"funding_top_n": 11}, "top_n"),
        ({"funding_capital": "0"}, "funding_capital"),
        ({"funding_leverage": 126}, "funding_leverage"),
    ],
)
def test_invalid_funding_monitor_settings_fail_fast(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        Settings(
            binance_api_key="",
            binance_api_secret="",
            **kwargs,
        )
