from decimal import Decimal

import pytest

from adapters.binance.transport.rest_client import BinanceRestClient
from app import Settings, build_binance_container
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, Side


def test_container_builds_without_network_requests(tmp_path) -> None:
    container = build_binance_container(
        Settings(
            binance_api_key="test-key",
            binance_api_secret="test-secret",
        ),
        database_path=tmp_path / "engine.sqlite3",
    )

    assert container.settings.live_trading_enabled is False
    assert container.order_event_stream.listen_key is None
    assert container.order_repository.list_open() == ()
    assert container.atomic_order_persistence.path.endswith("engine.sqlite3")

    with pytest.raises(RuntimeError, match="live trading is disabled"):
        container.trading_gateway.submit_order(
            OrderIntent(
                execution_id="safety-test",
                client_order_id="safety-test-1",
                instrument=InstrumentId("binance", "MARGIN", "ETHUSDT"),
                side=Side.BUY,
                quantity=Decimal("0.01"),
            )
        )

    with pytest.raises(RuntimeError, match="live trading is disabled"):
        container.account_gateway.collect_futures_funds(
            confirmed_manual_recovery=True
        )


def test_all_binance_rest_clients_share_clock_recovery_callback(
    tmp_path,
    monkeypatch,
) -> None:
    configured: list[tuple[str, object]] = []
    original = BinanceRestClient.set_clock_sync

    def capture(self, callback):
        configured.append((self.base_url, callback))
        original(self, callback)

    monkeypatch.setattr(BinanceRestClient, "set_clock_sync", capture)
    build_binance_container(
        Settings(
            binance_api_key="test-key",
            binance_api_secret="test-secret",
        ),
        database_path=tmp_path / "engine.sqlite3",
    )

    assert [base_url for base_url, _ in configured] == [
        "https://api.binance.com",
        "https://fapi.binance.com",
        "https://papi.binance.com",
    ]
    assert len({id(callback) for _, callback in configured}) == 1
