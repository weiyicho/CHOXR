import pytest

from app.safety import LiveAccountGuard
from app.settings import Settings
from engine.domain.instrument import InstrumentId


class FakeAccountGateway:
    def __init__(self) -> None:
        self.collection_calls = 0
        self.leverage_calls: list[tuple[InstrumentId, int]] = []

    def collect_futures_funds(self) -> dict[str, object]:
        self.collection_calls += 1
        return {"msg": "success"}

    def set_um_symbol_leverage(
        self,
        instrument: InstrumentId,
        leverage: int,
    ) -> int:
        self.leverage_calls.append((instrument, leverage))
        return leverage


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


def test_leverage_change_requires_live_trading() -> None:
    delegate = FakeAccountGateway()
    guard = LiveAccountGuard(delegate, settings(live=False))  # type: ignore[arg-type]
    instrument = InstrumentId(
        "binance",
        "USD_M_PERPETUAL",
        "ETHUSDT",
    )

    with pytest.raises(RuntimeError, match="live trading is disabled"):
        guard.set_um_symbol_leverage(instrument, 5)

    assert delegate.leverage_calls == []


def test_live_leverage_change_delegates_once() -> None:
    delegate = FakeAccountGateway()
    guard = LiveAccountGuard(delegate, settings(live=True))  # type: ignore[arg-type]
    instrument = InstrumentId(
        "binance",
        "USD_M_PERPETUAL",
        "ETHUSDT",
    )

    assert guard.set_um_symbol_leverage(instrument, 5) == 5
    assert delegate.leverage_calls == [(instrument, 5)]
