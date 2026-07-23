from __future__ import annotations

import hashlib
import hmac
from urllib.parse import urlencode

import pytest
import requests

from adapters.binance.config import BinanceConfig
from adapters.binance.transport.auth import HmacSigner
from adapters.binance.transport.clock import ServerClock
from adapters.binance.transport.errors import (
    BinanceRateLimitError,
    BinanceServerError,
    UnknownExecutionOutcome,
)
from adapters.binance.transport.rest_client import BinanceRestClient

from .support import FakeResponse, FakeSession


def config() -> BinanceConfig:
    return BinanceConfig(api_key="test-key", api_secret="test-secret")


def test_signed_request_uses_decimal_safe_query_and_captures_rate_headers():
    session = FakeSession(
        [
            FakeResponse(
                200,
                {"ok": True},
                {
                    "X-MBX-USED-WEIGHT-1M": "17",
                    "X-MBX-ORDER-COUNT-10S": "2",
                },
            )
        ]
    )
    clock = ServerClock(lambda: 1_700_000_000.0)
    client = BinanceRestClient(
        "https://papi.binance.com", config(), session=session, clock=clock
    )

    assert client.request(
        "GET", "/papi/v1/account", signed=True, side_effect=False
    ) == {"ok": True}

    sent = session.calls[0]
    unsigned = {
        "timestamp": 1_700_000_000_000,
        "recvWindow": 5_000,
    }
    expected = hmac.new(
        b"test-secret", urlencode(unsigned).encode(), hashlib.sha256
    ).hexdigest()
    assert sent["headers"] == {"X-MBX-APIKEY": "test-key"}
    assert sent["params"] == {**unsigned, "signature": expected}
    assert client.last_rate_limit.used_weights["x-mbx-used-weight-1m"] == 17
    assert client.last_rate_limit.order_counts["x-mbx-order-count-10s"] == 2


def test_write_timeout_is_unknown_and_is_not_retried():
    session = FakeSession([requests.Timeout("network timed out")])
    client = BinanceRestClient("https://papi.binance.com", config(), session=session)

    with pytest.raises(UnknownExecutionOutcome) as caught:
        client.request(
            "POST",
            "/papi/v1/um/order",
            {"newClientOrderId": "execution-1"},
            signed=True,
            side_effect=True,
            client_order_id="execution-1",
        )

    assert caught.value.context.client_order_id == "execution-1"
    assert len(session.calls) == 1


def test_write_503_unknown_message_is_unknown_and_is_not_retried():
    session = FakeSession(
        [
            FakeResponse(
                503,
                {
                    "msg": (
                        "Unknown error, please check your request or try again later."
                    )
                },
            )
        ]
    )
    client = BinanceRestClient("https://papi.binance.com", config(), session=session)

    with pytest.raises(UnknownExecutionOutcome):
        client.request(
            "POST", "/papi/v1/um/order", signed=True, side_effect=True
        )
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (None, "Service Unavailable."),
        (None, "Internal error; unable to process your request. Please try again."),
        (-1008, "Request throttled by system-level protection."),
    ],
)
def test_known_failure_503_is_retryable_server_error_but_not_retried_by_transport(
    code,
    message,
):
    payload = {"msg": message}
    if code is not None:
        payload["code"] = code
    session = FakeSession([FakeResponse(503, payload)])
    client = BinanceRestClient("https://papi.binance.com", config(), session=session)

    with pytest.raises(BinanceServerError) as caught:
        client.request(
            "POST", "/papi/v1/um/order", signed=True, side_effect=True
        )

    assert caught.value.retryable is True
    assert len(session.calls) == 1


def test_read_minus_1007_is_retryable_server_error_not_unknown_execution():
    session = FakeSession(
        [FakeResponse(504, {"code": -1007, "msg": "Timeout waiting for response"})]
    )
    client = BinanceRestClient("https://papi.binance.com", config(), session=session)

    with pytest.raises(BinanceServerError):
        client.request(
            "GET", "/papi/v1/um/order", signed=True, side_effect=False
        )


def test_write_minus_1007_remains_unknown_execution_outcome():
    session = FakeSession(
        [FakeResponse(504, {"code": -1007, "msg": "Timeout waiting for response"})]
    )
    client = BinanceRestClient("https://papi.binance.com", config(), session=session)

    with pytest.raises(UnknownExecutionOutcome):
        client.request(
            "POST", "/papi/v1/um/order", signed=True, side_effect=True
        )


def test_429_preserves_retry_after_for_runtime_backoff():
    session = FakeSession(
        [FakeResponse(429, {"code": -1003, "msg": "Too many requests"}, {"Retry-After": "3"})]
    )
    client = BinanceRestClient("https://api.binance.com", config(), session=session)

    with pytest.raises(BinanceRateLimitError) as caught:
        client.request("GET", "/api/v3/time", side_effect=False)
    assert caught.value.context.retry_after_seconds == 3


def test_minus_1021_syncs_clock_and_retries_once():
    session = FakeSession(
        [
            FakeResponse(400, {"code": -1021, "msg": "outside recvWindow"}),
            FakeResponse(200, {"ok": True}),
        ]
    )
    sync_calls = []
    client = BinanceRestClient(
        "https://papi.binance.com",
        config(),
        session=session,
        clock_sync=lambda: sync_calls.append(True),
    )

    assert client.request(
        "GET", "/papi/v1/account", signed=True, side_effect=False
    ) == {"ok": True}
    assert sync_calls == [True]
    assert len(session.calls) == 2


def test_signing_percent_encodes_space_plus_and_non_ascii_before_hmac():
    params = {
        "symbol": "１２３４５６",
        "note": "space + plus",
        "timestamp": 1_700_000_000_000,
    }
    signed = HmacSigner("test-secret").sign(params)
    expected_query = (
        "symbol=%EF%BC%91%EF%BC%92%EF%BC%93%EF%BC%94%EF%BC%95%EF%BC%96"
        "&note=space+%2B+plus&timestamp=1700000000000"
    )
    expected_signature = hmac.new(
        b"test-secret",
        expected_query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert signed.query_string == expected_query
    assert signed.parameters["signature"] == expected_signature

    prepared_url = requests.Request(
        "GET",
        "https://api.binance.com/api/v3/order",
        params=signed.parameters,
    ).prepare().url
    actual_query = prepared_url.split("?", 1)[1].rsplit("&signature=", 1)[0]
    assert actual_query == expected_query
