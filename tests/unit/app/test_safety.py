import pytest

from app.safety import LiveAccountGuard
from app.settings import Settings


class FakeAccountGateway:
    def __init__(self) -> None:
        self.collection_calls = 0

    def collect_futures_funds(self) -> dict[str, object]:
        self.collection_calls += 1
        return {"msg": "success"}


def settings(*, live: bool) -> Settings:
    return Settings("key", "secret", live_trading_enabled=live)


def test_fund_collection_requires_live_mutations_to_be_enabled() -> None:
    delegate = FakeAccountGateway()
    guard = LiveAccountGuard(delegate, settings(live=False))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="live trading is disabled"):
        guard.collect_futures_funds(confirmed_manual_recovery=True)

    assert delegate.collection_calls == 0


def test_fund_collection_requires_explicit_manual_confirmation() -> None:
    delegate = FakeAccountGateway()
    guard = LiveAccountGuard(delegate, settings(live=True))  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="manual recovery only"):
        guard.collect_futures_funds()

    assert delegate.collection_calls == 0


def test_confirmed_manual_collection_delegates_once() -> None:
    delegate = FakeAccountGateway()
    guard = LiveAccountGuard(delegate, settings(live=True))  # type: ignore[arg-type]

    result = guard.collect_futures_funds(confirmed_manual_recovery=True)

    assert result == {"msg": "success"}
    assert delegate.collection_calls == 1
