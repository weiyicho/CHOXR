import pytest

from app.settings import Settings


def test_live_trading_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHOXR_LIVE_TRADING", raising=False)
    settings = Settings.from_environment()

    assert settings.live_trading_enabled is False
    with pytest.raises(RuntimeError, match="live trading is disabled"):
        settings.require_live_trading()
