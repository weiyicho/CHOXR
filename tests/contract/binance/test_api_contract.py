from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.binance.api.account_profile import PortfolioAccountProfileApi
from adapters.binance.api.portfolio_margin import PortfolioMarginApi
from adapters.binance.api.spot_api import SpotApi
from adapters.binance.api.usd_m_api import UsdMApi
from adapters.binance.api.user_stream import PortfolioMarginUserStreamApi

from .support import RecordingRestClient


def test_market_data_uses_distinct_spot_and_um_depth_routes():
    spot_client = RecordingRestClient([{"lastUpdateId": 1, "bids": [], "asks": []}])
    um_client = RecordingRestClient([{"lastUpdateId": 2, "bids": [], "asks": []}])

    SpotApi(spot_client).get_order_book("ETHUSDT", 100)
    UsdMApi(um_client).get_order_book("ETHUSDT", 100)

    assert spot_client.calls[0]["path"] == "/api/v3/depth"
    assert um_client.calls[0]["path"] == "/fapi/v1/depth"


def test_spot_depth_accepts_the_documented_integer_range():
    client = RecordingRestClient(
        [
            {"lastUpdateId": 1, "bids": [], "asks": []},
            {"lastUpdateId": 2, "bids": [], "asks": []},
        ]
    )
    api = SpotApi(client)

    api.get_order_book("ETHUSDT", 1)
    api.get_order_book("ETHUSDT", 5_000)

    assert [call["params"]["limit"] for call in client.calls] == [1, 5_000]
    with pytest.raises(ValueError, match="between 1 and 5000"):
        api.get_order_book("ETHUSDT", 0)
    with pytest.raises(ValueError, match="between 1 and 5000"):
        api.get_order_book("ETHUSDT", 5_001)


def test_classic_pm_margin_order_contract_uses_no_side_effect():
    client = RecordingRestClient([{"symbol": "ETHUSDT", "orderId": 10}])
    api = PortfolioMarginApi(client)

    api.place_margin_order(
        symbol="ETHUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("0.125"),
        client_order_id="fund-spot-1",
    )

    call = client.calls[0]
    assert (call["method"], call["path"]) == (
        "POST",
        "/papi/v1/margin/order",
    )
    assert call["params"]["quantity"] == "0.125"
    assert call["params"]["sideEffectType"] == "NO_SIDE_EFFECT"
    assert call["params"]["newClientOrderId"] == "fund-spot-1"
    assert call["signed"] is True
    assert call["side_effect"] is True


def test_classic_pm_um_limit_order_contract_keeps_client_id_and_reduce_only():
    client = RecordingRestClient([{"symbol": "ETHUSDT", "orderId": 11}])
    api = PortfolioMarginApi(client)

    api.place_um_order(
        symbol="ETHUSDT",
        side="SELL",
        order_type="LIMIT",
        quantity="0.125",
        price="3210.50",
        time_in_force="GTX",
        reduce_only=False,
        client_order_id="fund-perp-1",
    )

    call = client.calls[0]
    assert call["path"] == "/papi/v1/um/order"
    assert call["params"]["price"] == "3210.50"
    assert call["params"]["timeInForce"] == "GTX"
    assert call["params"]["reduceOnly"] is False
    assert call["client_order_id"] == "fund-perp-1"


def test_query_cancel_open_and_fills_use_documented_classic_pm_routes():
    client = RecordingRestClient([{} for _ in range(8)])
    api = PortfolioMarginApi(client)

    api.query_margin_order("ETHUSDT", client_order_id="spot-1")
    api.cancel_margin_order("ETHUSDT", client_order_id="spot-1")
    api.list_margin_open_orders("ETHUSDT")
    api.list_margin_fills("ETHUSDT", order_id=1)
    api.query_um_order("ETHUSDT", client_order_id="um-1")
    api.cancel_um_order("ETHUSDT", client_order_id="um-1")
    api.list_um_open_orders("ETHUSDT")
    api.list_um_fills("ETHUSDT")

    assert [(call["method"], call["path"]) for call in client.calls] == [
        ("GET", "/papi/v1/margin/order"),
        ("DELETE", "/papi/v1/margin/order"),
        ("GET", "/papi/v1/margin/openOrders"),
        ("GET", "/papi/v1/margin/myTrades"),
        ("GET", "/papi/v1/um/order"),
        ("DELETE", "/papi/v1/um/order"),
        ("GET", "/papi/v1/um/openOrders"),
        ("GET", "/papi/v1/um/userTrades"),
    ]


def test_account_position_and_funding_routes_are_papi_not_fapi():
    client = RecordingRestClient([{}, [], [], []])
    api = PortfolioMarginApi(client)
    api.get_account()
    api.get_balances()
    api.get_um_positions("ETHUSDT")
    api.list_funding_income(symbol="ETHUSDT")

    assert [call["path"] for call in client.calls] == [
        "/papi/v1/account",
        "/papi/v1/balance",
        "/papi/v1/um/positionRisk",
        "/papi/v1/um/income",
    ]
    assert client.calls[-1]["params"]["incomeType"] == "FUNDING_FEE"


def test_filtered_papi_balance_object_is_normalized_to_a_list():
    payload = {"asset": "USDT", "totalWalletBalance": "100"}
    client = RecordingRestClient([payload])

    assert PortfolioMarginApi(client).get_balances("USDT") == [payload]
    assert client.calls[0]["params"] == {"asset": "USDT"}


def test_papi_user_stream_lifecycle_is_api_key_authenticated_not_signed():
    client = RecordingRestClient([{"listenKey": "listen-key"}, {}, {}])
    api = PortfolioMarginUserStreamApi(client)

    assert api.start() == "listen-key"
    api.keepalive()
    api.close()

    assert [call["method"] for call in client.calls] == ["POST", "PUT", "DELETE"]
    assert all(call["path"] == "/papi/v1/listenKey" for call in client.calls)
    assert all(call["api_key"] is True for call in client.calls)
    assert all(call["side_effect"] is False for call in client.calls)


def test_account_profile_discriminator_is_signed_read_only_sapi():
    client = RecordingRestClient([{"accountType": "PM_2"}])

    assert PortfolioAccountProfileApi(client).get_account_profile() == {
        "accountType": "PM_2"
    }
    assert client.calls == [
        {
            "method": "GET",
            "path": "/sapi/v1/portfolio/account",
            "params": {},
            "signed": True,
            "side_effect": False,
        }
    ]
