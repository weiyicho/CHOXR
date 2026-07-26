from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest

from adapters.binance.gateways.market_data_gateway import BinanceMarketDataGateway
from adapters.binance.gateways.account_gateway import (
    ClassicPortfolioMarginAccountGateway,
)
from adapters.binance.gateways.order_event_stream import (
    PortfolioMarginOrderEventStream,
    StreamLifecycleKind,
    StreamLifecycleSignal,
)
from adapters.binance.gateways.trading_gateway import (
    ClassicPortfolioMarginMarginTradingGateway,
    ClassicPortfolioMarginTradingRouter,
    ClassicPortfolioMarginUsdMTradingGateway,
)
from adapters.binance.transport.errors import (
    BinanceAuthenticationError,
    BinanceRequestError,
    ErrorContext,
    UnknownExecutionOutcome,
)
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderState, OrderType, Side, TimeInForce
from engine.domain.order_event import OrderEventKind
from engine.ports.trading_gateway import (
    OrderSubmissionRejected,
    UnknownSubmissionState,
)
from adapters.binance.config import BinanceAccountMode


class FakeMarketApi:
    def get_order_book(self, symbol, limit):
        return {
            "lastUpdateId": 10,
            "bids": [["3199.99", "1"]],
            "asks": [["3200.00", "2"]],
        }

    def get_exchange_info(self, symbol=None):
        return {
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "status": "TRADING",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDT",
                    "filters": [
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {
                            "filterType": "LOT_SIZE",
                            "stepSize": "0.001",
                            "minQty": "0.001",
                            "maxQty": "1000",
                        },
                        {
                            "filterType": "MARKET_LOT_SIZE",
                            "stepSize": "0.01",
                            "minQty": "0.01",
                            "maxQty": "250",
                        },
                        {
                            "filterType": "NOTIONAL",
                            "minNotional": "5",
                            "maxNotional": "500000",
                        },
                    ],
                }
            ]
        }


class FakePortfolioApi:
    def __init__(self, *, unknown=False, rejected=False):
        self.calls = []
        self.unknown = unknown
        self.rejected = rejected

    def get_account(self):
        self.calls.append({"get_account": True})
        return {
            "accountEquity": "1000",
            "actualEquity": "1000",
            "totalAvailableBalance": "900",
            "accountInitialMargin": "100",
            "accountMaintMargin": "10",
            "uniMMR": "100",
        }

    def get_um_symbol_config(self, symbol=None):
        self.calls.append({"get_um_symbol_config": symbol})
        return [{"symbol": symbol or "ETHUSDT", "leverage": 5}]

    def change_um_initial_leverage(self, *, symbol, leverage):
        self.calls.append(
            {
                "change_um_initial_leverage": {
                    "symbol": symbol,
                    "leverage": leverage,
                }
            }
        )
        return {"symbol": symbol, "leverage": leverage}

    def place_um_order(self, **kwargs):
        self.calls.append(kwargs)
        if self.unknown:
            raise UnknownExecutionOutcome(
                ErrorContext("POST", "/papi/v1/um/order", client_order_id=kwargs["client_order_id"])
            )
        if self.rejected:
            raise BinanceAuthenticationError(
                ErrorContext(
                    "POST",
                    "/papi/v1/um/order",
                    status_code=401,
                    code=-2015,
                    message="Invalid API-key, IP, or permissions for action",
                    client_order_id=kwargs["client_order_id"],
                )
            )
        return {
            "symbol": kwargs["symbol"],
            "orderId": 77,
            "clientOrderId": kwargs["client_order_id"],
            "status": "NEW",
            "side": kwargs["side"],
            "type": kwargs["order_type"],
            "origQty": str(kwargs["quantity"]),
            "executedQty": "0",
            "cumQuote": "0",
            "price": str(kwargs["price"]),
            "avgPrice": "0",
            "reduceOnly": kwargs["reduce_only"],
            "positionSide": "BOTH",
        }


class FakeSplitTradingApi:
    """Records which Portfolio Margin order family each gateway touches."""

    def __init__(self):
        self.calls = []

    @staticmethod
    def _order_payload(
        *,
        symbol="ETHUSDT",
        client_order_id="order-1",
        status="NEW",
        side="BUY",
        order_type="LIMIT",
        quantity="0.1",
        price="3200",
        reduce_only=False,
    ):
        return {
            "symbol": symbol,
            "orderId": 77,
            "clientOrderId": client_order_id,
            "status": status,
            "side": side,
            "type": order_type,
            "origQty": str(quantity),
            "executedQty": "0",
            "cumQuote": "0",
            "price": str(price or "0"),
            "avgPrice": "0",
            "reduceOnly": reduce_only,
            "positionSide": "BOTH",
        }

    def place_margin_order(self, **kwargs):
        self.calls.append(("place_margin_order", kwargs))
        return self._order_payload(
            symbol=kwargs["symbol"],
            client_order_id=kwargs["client_order_id"],
            side=kwargs["side"],
            order_type=kwargs["order_type"],
            quantity=kwargs["quantity"],
            price=kwargs["price"],
        )

    def query_margin_order(self, symbol, *, client_order_id):
        self.calls.append(
            (
                "query_margin_order",
                {"symbol": symbol, "client_order_id": client_order_id},
            )
        )
        return self._order_payload(
            symbol=symbol,
            client_order_id=client_order_id,
        )

    def cancel_margin_order(self, symbol, *, client_order_id):
        self.calls.append(
            (
                "cancel_margin_order",
                {"symbol": symbol, "client_order_id": client_order_id},
            )
        )
        return self._order_payload(
            symbol=symbol,
            client_order_id=client_order_id,
            status="CANCELED",
        )

    def list_margin_open_orders(self, symbol=None):
        self.calls.append(("list_margin_open_orders", {"symbol": symbol}))
        return [
            self._order_payload(
                symbol=symbol or "ETHUSDT",
                client_order_id="spot-open-1",
            )
        ]

    def place_um_order(self, **kwargs):
        self.calls.append(("place_um_order", kwargs))
        return self._order_payload(
            symbol=kwargs["symbol"],
            client_order_id=kwargs["client_order_id"],
            side=kwargs["side"],
            order_type=kwargs["order_type"],
            quantity=kwargs["quantity"],
            price=kwargs["price"],
            reduce_only=kwargs["reduce_only"],
        )

    def query_um_order(self, symbol, *, client_order_id):
        self.calls.append(
            (
                "query_um_order",
                {"symbol": symbol, "client_order_id": client_order_id},
            )
        )
        return self._order_payload(
            symbol=symbol,
            client_order_id=client_order_id,
        )

    def cancel_um_order(self, symbol, *, client_order_id):
        self.calls.append(
            (
                "cancel_um_order",
                {"symbol": symbol, "client_order_id": client_order_id},
            )
        )
        return self._order_payload(
            symbol=symbol,
            client_order_id=client_order_id,
            status="CANCELED",
        )

    def list_um_open_orders(self, symbol=None):
        self.calls.append(("list_um_open_orders", {"symbol": symbol}))
        return [
            self._order_payload(
                symbol=symbol or "ETHUSDT",
                client_order_id="um-open-1",
            )
        ]


class FakeUserStreamApi:
    def __init__(self, listen_keys=None):
        self.calls = []
        self.listen_keys = list(listen_keys or ["listen-key"])
        self.keepalive_called = asyncio.Event()

    def start(self):
        self.calls.append("start")
        return self.listen_keys.pop(0)

    def keepalive(self):
        self.calls.append("keepalive")
        self.keepalive_called.set()

    def close(self):
        self.calls.append("close")


class FakeWebSocket:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self._block_forever = asyncio.Event()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.messages:
            return self.messages.pop(0)
        await self._block_forever.wait()
        raise StopAsyncIteration


class DisconnectingFakeWebSocket:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class FakeConnectContext:
    def __init__(self, websocket=None, error=None, entered=None):
        self.websocket = websocket
        self.error = error
        self.entered = entered

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        if self.entered is not None:
            self.entered.set()
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakeConnector:
    def __init__(self, contexts):
        self.contexts = list(contexts)
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.contexts.pop(0)


def um_trade_update():
    return {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1_700_000_000_000,
        "T": 1_700_000_000_001,
        "o": {
            "s": "ETHUSDT",
            "c": "fund-perp-1",
            "i": 77,
            "S": "SELL",
            "o": "LIMIT",
            "x": "TRADE",
            "X": "PARTIALLY_FILLED",
            "q": "0.1",
            "l": "0.025",
            "z": "0.025",
            "L": "3200",
            "ap": "3200",
            "t": 9,
            "n": "0.0125",
            "N": "USDT",
            "R": False,
            "ps": "BOTH",
        },
    }


async def run_sync_inline(function, *args):
    return function(*args)


class FakeAccountProfileApi:
    def __init__(self, account_type="PM_2"):
        self.account_type = account_type
        self.calls = 0

    def get_account_profile(self):
        self.calls += 1
        return {"accountType": self.account_type}


def test_market_data_gateway_maps_binance_payload_to_engine_models():
    native = FakeMarketApi()
    gateway = BinanceMarketDataGateway(native, native)
    instrument = InstrumentId("binance", "USD_M_FUTURES", "ETHUSDT")

    book = gateway.get_order_book(instrument, 100)
    rules = gateway.get_symbol_rules(instrument)

    assert book.best_bid.price == Decimal("3199.99")
    assert book.best_ask.price == Decimal("3200.00")
    assert rules.tick_size == Decimal("0.01")
    assert rules.step_size == Decimal("0.001")
    assert rules.market_quantity_increment == Decimal("0.01")
    assert rules.market_min_quantity == Decimal("0.01")
    assert rules.market_max_quantity == Decimal("250")
    assert rules.max_notional == Decimal("500000")
    assert rules.trading_enabled is True


def test_market_data_gateway_disables_non_trading_symbol():
    class DisabledMarketApi(FakeMarketApi):
        def get_exchange_info(self, symbol=None):
            payload = super().get_exchange_info(symbol)
            payload["symbols"][0]["status"] = "CANCEL_ONLY"
            return payload

    native = DisabledMarketApi()
    gateway = BinanceMarketDataGateway(native, native)
    instrument = InstrumentId("binance", "SPOT", "ETHUSDT")

    assert gateway.get_symbol_rules(instrument).trading_enabled is False


def test_account_gateway_preflight_verifies_pm_2_then_reads_papi_account():
    papi = FakePortfolioApi()
    profile = FakeAccountProfileApi("PM_2")
    market = BinanceMarketDataGateway(FakeMarketApi(), FakeMarketApi())
    gateway = ClassicPortfolioMarginAccountGateway(papi, market, profile)

    assert gateway.verify_configured_mode(
        BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN
    ) is BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN
    assert profile.calls == 1
    assert papi.calls == [{"get_account": True}]


def test_account_gateway_reads_current_um_leverage_without_mutation():
    papi = FakePortfolioApi()
    market = BinanceMarketDataGateway(FakeMarketApi(), FakeMarketApi())
    gateway = ClassicPortfolioMarginAccountGateway(papi, market)
    instrument = InstrumentId("binance", "USD_M_PERPETUAL", "ETHUSDT")

    assert gateway.get_um_symbol_leverage(instrument) == 5
    assert papi.calls == [{"get_um_symbol_config": "ETHUSDT"}]


def test_account_gateway_changes_um_leverage_and_validates_response():
    papi = FakePortfolioApi()
    market = BinanceMarketDataGateway(FakeMarketApi(), FakeMarketApi())
    gateway = ClassicPortfolioMarginAccountGateway(papi, market)
    instrument = InstrumentId("binance", "USD_M_PERPETUAL", "ETHUSDT")

    assert gateway.set_um_symbol_leverage(instrument, 5) == 5
    assert papi.calls == [
        {
            "change_um_initial_leverage": {
                "symbol": "ETHUSDT",
                "leverage": 5,
            }
        }
    ]


def test_account_gateway_reconciles_an_uncertain_leverage_change():
    class AppliedThenTimedOutPortfolioApi(FakePortfolioApi):
        def __init__(self):
            super().__init__()
            self.leverage = 13

        def get_um_symbol_config(self, symbol=None):
            self.calls.append({"get_um_symbol_config": symbol})
            return [
                {
                    "symbol": symbol or "ETHUSDT",
                    "leverage": self.leverage,
                }
            ]

        def change_um_initial_leverage(self, *, symbol, leverage):
            self.calls.append(
                {
                    "change_um_initial_leverage": {
                        "symbol": symbol,
                        "leverage": leverage,
                    }
                }
            )
            self.leverage = leverage
            raise UnknownExecutionOutcome(
                ErrorContext("POST", "/papi/v1/um/leverage")
            )

    papi = AppliedThenTimedOutPortfolioApi()
    market = BinanceMarketDataGateway(FakeMarketApi(), FakeMarketApi())
    gateway = ClassicPortfolioMarginAccountGateway(papi, market)
    instrument = InstrumentId("binance", "USD_M_PERPETUAL", "ETHUSDT")

    assert gateway.set_um_symbol_leverage(instrument, 5) == 5
    assert papi.calls[-1] == {"get_um_symbol_config": "ETHUSDT"}


def _margin_market_intent(client_order_id="fund-spot-1"):
    return OrderIntent(
        execution_id="execution-1",
        client_order_id=client_order_id,
        instrument=InstrumentId("binance", "MARGIN", "ETHUSDT"),
        side=Side.BUY,
        quantity=Decimal("0.1"),
        order_type=OrderType.MARKET,
    )


def _um_maker_intent(client_order_id="fund-perp-1"):
    return OrderIntent(
        execution_id="execution-1",
        client_order_id=client_order_id,
        instrument=InstrumentId("binance", "USD_M_FUTURES", "ETHUSDT"),
        side=Side.SELL,
        quantity=Decimal("0.1"),
        order_type=OrderType.LIMIT,
        price=Decimal("3200"),
        time_in_force=TimeInForce.GTC,
        post_only=True,
    )


def _trading_router(api):
    return ClassicPortfolioMarginTradingRouter(
        margin_gateway=ClassicPortfolioMarginMarginTradingGateway(api),
        usd_m_gateway=ClassicPortfolioMarginUsdMTradingGateway(api),
    )


def test_margin_trading_gateway_only_uses_margin_order_endpoints():
    api = FakeSplitTradingApi()
    gateway = ClassicPortfolioMarginMarginTradingGateway(api)
    intent = _margin_market_intent()

    submitted = gateway.submit_order(intent)
    queried = gateway.get_order(intent.instrument, intent.client_order_id)
    canceled = gateway.cancel_order(intent.instrument, intent.client_order_id)
    open_orders = gateway.list_open_orders(intent.instrument)

    assert submitted.intent is intent
    assert queried is not None
    assert canceled.state is OrderState.CANCELED
    assert open_orders[0].intent.instrument.market == "MARGIN"
    assert [name for name, _ in api.calls] == [
        "place_margin_order",
        "query_margin_order",
        "cancel_margin_order",
        "list_margin_open_orders",
    ]
    assert api.calls[0][1]["side_effect_type"] == "NO_SIDE_EFFECT"


def test_usd_m_trading_gateway_only_uses_um_order_endpoints():
    api = FakeSplitTradingApi()
    gateway = ClassicPortfolioMarginUsdMTradingGateway(api)
    intent = _um_maker_intent()

    submitted = gateway.submit_order(intent)
    queried = gateway.get_order(intent.instrument, intent.client_order_id)
    canceled = gateway.cancel_order(intent.instrument, intent.client_order_id)
    open_orders = gateway.list_open_orders(intent.instrument)

    assert submitted.intent is intent
    assert queried is not None
    assert canceled.state is OrderState.CANCELED
    assert open_orders[0].intent.instrument.market == "USD_M_FUTURES"
    assert [name for name, _ in api.calls] == [
        "place_um_order",
        "query_um_order",
        "cancel_um_order",
        "list_um_open_orders",
    ]
    assert api.calls[0][1]["time_in_force"] == "GTX"


def test_specialized_trading_gateways_reject_the_wrong_market_family():
    api = FakeSplitTradingApi()
    margin_gateway = ClassicPortfolioMarginMarginTradingGateway(api)
    usd_m_gateway = ClassicPortfolioMarginUsdMTradingGateway(api)

    with pytest.raises(ValueError):
        margin_gateway.submit_order(_um_maker_intent())
    with pytest.raises(ValueError):
        usd_m_gateway.submit_order(_margin_market_intent())

    assert api.calls == []


def test_trading_router_routes_each_market_to_its_specialized_gateway():
    api = FakeSplitTradingApi()
    margin_gateway = ClassicPortfolioMarginMarginTradingGateway(api)
    usd_m_gateway = ClassicPortfolioMarginUsdMTradingGateway(api)
    router = ClassicPortfolioMarginTradingRouter(
        margin_gateway=margin_gateway,
        usd_m_gateway=usd_m_gateway,
    )
    margin_intent = _margin_market_intent()
    um_intent = _um_maker_intent()

    router.submit_order(margin_intent)
    router.submit_order(um_intent)
    router.get_order(margin_intent.instrument, margin_intent.client_order_id)
    router.get_order(um_intent.instrument, um_intent.client_order_id)
    router.cancel_order(margin_intent.instrument, margin_intent.client_order_id)
    router.cancel_order(um_intent.instrument, um_intent.client_order_id)
    open_orders = router.list_open_orders()

    assert [name for name, _ in api.calls] == [
        "place_margin_order",
        "place_um_order",
        "query_margin_order",
        "query_um_order",
        "cancel_margin_order",
        "cancel_um_order",
        "list_margin_open_orders",
        "list_um_open_orders",
    ]
    assert [record.intent.instrument.market for record in open_orders] == [
        "MARGIN",
        "USD_M_FUTURES",
    ]


def test_post_only_um_intent_becomes_gtx_and_returns_engine_order_record():
    api = FakePortfolioApi()
    gateway = _trading_router(api)
    intent = OrderIntent(
        execution_id="execution-1",
        client_order_id="fund-perp-1",
        instrument=InstrumentId("binance", "USD_M_FUTURES", "ETHUSDT"),
        side=Side.SELL,
        quantity=Decimal("0.1"),
        order_type=OrderType.LIMIT,
        price=Decimal("3200"),
        time_in_force=TimeInForce.GTC,
        post_only=True,
    )

    record = gateway.submit_order(intent)

    assert api.calls[0]["time_in_force"] == "GTX"
    assert record.intent is intent
    assert record.state is OrderState.NEW
    assert record.exchange_order_id == "77"


def test_unknown_transport_outcome_becomes_engine_unknown_submission_state():
    gateway = _trading_router(FakePortfolioApi(unknown=True))
    intent = OrderIntent(
        execution_id="execution-1",
        client_order_id="fund-perp-1",
        instrument=InstrumentId("binance", "USD_M_FUTURES", "ETHUSDT"),
        side=Side.SELL,
        quantity="0.1",
    )

    with pytest.raises(UnknownSubmissionState) as caught:
        gateway.submit_order(intent)
    assert caught.value.client_order_id == "fund-perp-1"


def test_authoritative_binance_error_becomes_engine_submission_rejection():
    gateway = _trading_router(FakePortfolioApi(rejected=True))
    intent = OrderIntent(
        execution_id="execution-1",
        client_order_id="fund-perp-1",
        instrument=InstrumentId("binance", "USD_M_FUTURES", "ETHUSDT"),
        side=Side.SELL,
        quantity="0.1",
    )

    with pytest.raises(OrderSubmissionRejected) as caught:
        gateway.submit_order(intent)

    assert caught.value.client_order_id == "fund-perp-1"
    assert caught.value.reason == (
        "POST /papi/v1/um/order: [-2015] "
        "Invalid API-key, IP, or permissions for action"
    )


def test_order_event_stream_maps_native_partial_fill_to_domain_event():
    async def scenario():
        api = FakeUserStreamApi()
        stream = PortfolioMarginOrderEventStream(api, "wss://fstream.binance.com/pm")
        assert stream.start() == "listen-key"
        assert stream.stream_base_url == "wss://fstream.binance.com/pm"
        assert stream.websocket_url == (
            "wss://fstream.binance.com/pm/ws/listen-key"
        )
        assert stream.feed_native_event({"e": "ACCOUNT_UPDATE"}) is None
        stream.feed_native_event(um_trade_update())
        iterator = stream.events()
        event = await anext(iterator)
        assert event.kind is OrderEventKind.TRADE
        assert event.client_order_id == "fund-perp-1"
        assert event.cumulative_quantity == Decimal("0.025")
        assert event.last_executed_quantity == Decimal("0.025")
        assert event.last_executed_price == Decimal("3200")
        assert event.trade_id == "9"
        assert event.commission == Decimal("0.0125")
        assert event.commission_asset == "USDT"
        assert event.reconciled_state is OrderState.PARTIALLY_FILLED
        stream.close()

    asyncio.run(scenario())


def test_order_event_id_does_not_collide_when_binance_reuses_ids_across_symbols():
    stream = PortfolioMarginOrderEventStream(
        FakeUserStreamApi(),
        "wss://fstream.binance.com/pm",
    )
    eth_payload = um_trade_update()
    btc_payload = um_trade_update()
    btc_payload["o"]["s"] = "BTCUSDT"

    eth_event = stream.feed_native_event(eth_payload)
    btc_event = stream.feed_native_event(btc_payload)

    assert eth_event is not None
    assert btc_event is not None
    assert eth_event.event_id != btc_event.event_id
    assert eth_event.event_id == (
        "USD_M_FUTURES:ETHUSDT:77:fund-perp-1:9:TRADE:"
        "1700000000001:1700000000000"
    )
    assert btc_event.event_id == (
        "USD_M_FUTURES:BTCUSDT:77:fund-perp-1:9:TRADE:"
        "1700000000001:1700000000000"
    )


def test_network_reconnects_with_bounded_backoff_and_filters_non_order_events():
    async def scenario():
        api = FakeUserStreamApi()
        socket = FakeWebSocket(
            [
                json.dumps({"e": "ACCOUNT_UPDATE", "E": 1}),
                json.dumps(um_trade_update()),
            ]
        )
        connector = FakeConnector(
            [
                FakeConnectContext(error=OSError("temporary disconnect")),
                FakeConnectContext(websocket=socket),
            ]
        )
        blocked = asyncio.Event()
        sleep_calls = []

        async def sleep(delay):
            sleep_calls.append(delay)
            if delay == 1:
                return
            await blocked.wait()

        stream = PortfolioMarginOrderEventStream(
            api,
            "wss://fstream.binance.com/pm",
            connector=connector,
            sleep=sleep,
            run_sync=run_sync_inline,
        )
        producer = asyncio.create_task(stream.run_network())
        event = await asyncio.wait_for(anext(stream.events()), timeout=1)
        assert event.client_order_id == "fund-perp-1"
        stream.request_stop()
        await asyncio.wait_for(producer, timeout=1)

        assert [call["url"] for call in connector.calls] == [
            "wss://fstream.binance.com/pm/ws/listen-key",
            "wss://fstream.binance.com/pm/ws/listen-key",
        ]
        assert sleep_calls[0] == 1
        assert max(stream._reconnect_backoff_seconds) == 30
        assert api.calls == ["start", "close"]

    asyncio.run(scenario())


def test_network_lifecycle_signals_connected_reconnecting_reconnected_and_stopped():
    async def scenario():
        api = FakeUserStreamApi()
        second_connection_entered = asyncio.Event()
        connector = FakeConnector(
            [
                FakeConnectContext(websocket=DisconnectingFakeWebSocket()),
                FakeConnectContext(
                    websocket=FakeWebSocket(),
                    entered=second_connection_entered,
                ),
            ]
        )
        blocked = asyncio.Event()

        async def sleep(delay):
            if delay == 1:
                return
            await blocked.wait()

        stream = PortfolioMarginOrderEventStream(
            api,
            "wss://fstream.binance.com/pm",
            connector=connector,
            sleep=sleep,
            run_sync=run_sync_inline,
        )
        producer = asyncio.create_task(stream.run_network())
        await asyncio.wait_for(second_connection_entered.wait(), timeout=1)
        stream.request_stop()
        await asyncio.wait_for(producer, timeout=1)

        lifecycle = [signal async for signal in stream.lifecycle_events()]
        assert all(isinstance(signal, StreamLifecycleSignal) for signal in lifecycle)
        assert [signal.kind for signal in lifecycle] == [
            StreamLifecycleKind.CONNECTED,
            StreamLifecycleKind.RECONNECTING,
            StreamLifecycleKind.RECONNECTED,
            StreamLifecycleKind.STOPPED,
        ]
        assert lifecycle[0].connection_sequence == 1
        assert lifecycle[1].reason == "stream_disconnected"
        assert lifecycle[1].reconnect_attempt == 1
        assert lifecycle[1].retry_delay_seconds == 1
        assert lifecycle[2].connection_sequence == 2
        assert stream.lifecycle_state is lifecycle[-1]

    asyncio.run(scenario())


def test_lifecycle_publishing_does_not_need_a_consumer_to_reconnect():
    async def scenario():
        api = FakeUserStreamApi()
        connected = asyncio.Event()
        failures = [
            FakeConnectContext(error=OSError(f"disconnect-{index}"))
            for index in range(100)
        ]
        connector = FakeConnector(
            [
                *failures,
                FakeConnectContext(
                    websocket=FakeWebSocket(),
                    entered=connected,
                ),
            ]
        )

        async def sleep(delay):
            return

        stream = PortfolioMarginOrderEventStream(
            api,
            "wss://fstream.binance.com/pm",
            connector=connector,
            sleep=sleep,
            run_sync=run_sync_inline,
        )
        producer = asyncio.create_task(stream.run_network())
        await asyncio.wait_for(connected.wait(), timeout=1)
        stream.request_stop()
        await asyncio.wait_for(producer, timeout=1)

        assert len(connector.calls) == 101
        assert stream.lifecycle_state is not None
        assert stream.lifecycle_state.kind is StreamLifecycleKind.STOPPED

    asyncio.run(scenario())


def test_network_keeps_listen_key_alive_before_sixty_minutes(capsys):
    async def scenario():
        api = FakeUserStreamApi()
        connector = FakeConnector(
            [FakeConnectContext(websocket=FakeWebSocket())]
        )
        blocked = asyncio.Event()
        keepalive_sleep_count = 0

        async def sleep(delay):
            nonlocal keepalive_sleep_count
            if delay == 45 * 60 and keepalive_sleep_count == 0:
                keepalive_sleep_count += 1
                return
            await blocked.wait()

        stream = PortfolioMarginOrderEventStream(
            api,
            "wss://fstream.binance.com/pm",
            connector=connector,
            sleep=sleep,
            run_sync=run_sync_inline,
        )
        producer = asyncio.create_task(stream.run_network())
        await asyncio.wait_for(api.keepalive_called.wait(), timeout=1)
        stream.request_stop()
        await asyncio.wait_for(producer, timeout=1)

        assert "keepalive" in api.calls

    asyncio.run(scenario())
    output = capsys.readouterr().out
    assert "[FUNDING][WS] listen key created (value hidden)" in output
    assert "[FUNDING][WS] listen key keepalive succeeded" in output
    assert "listen-key" not in output


def test_network_rotates_websocket_after_twelve_hours():
    async def scenario():
        api = FakeUserStreamApi(["listen-key-1"])
        second_connection_entered = asyncio.Event()
        connector = FakeConnector(
            [
                FakeConnectContext(websocket=FakeWebSocket()),
                FakeConnectContext(
                    websocket=FakeWebSocket(),
                    entered=second_connection_entered,
                ),
            ]
        )
        blocked = asyncio.Event()
        rotation_fired = False

        async def sleep(delay):
            nonlocal rotation_fired
            if delay == 12 * 60 * 60 and not rotation_fired:
                rotation_fired = True
                return
            await blocked.wait()

        stream = PortfolioMarginOrderEventStream(
            api,
            "wss://fstream.binance.com/pm",
            connector=connector,
            sleep=sleep,
            run_sync=run_sync_inline,
        )
        producer = asyncio.create_task(stream.run_network())
        await asyncio.wait_for(second_connection_entered.wait(), timeout=1)
        stream.request_stop()
        await asyncio.wait_for(producer, timeout=1)

        assert [call["url"] for call in connector.calls] == [
            "wss://fstream.binance.com/pm/ws/listen-key-1",
            "wss://fstream.binance.com/pm/ws/listen-key-1",
        ]
        assert api.calls == ["start", "close"]

    asyncio.run(scenario())


def test_listen_key_expired_event_rebuilds_key_without_entering_order_queue():
    async def scenario():
        api = FakeUserStreamApi(["listen-key-1", "listen-key-2"])
        second_connection_entered = asyncio.Event()
        connector = FakeConnector(
            [
                FakeConnectContext(
                    websocket=FakeWebSocket(
                        [json.dumps({"e": "listenKeyExpired", "E": 1})]
                    )
                ),
                FakeConnectContext(
                    websocket=FakeWebSocket(),
                    entered=second_connection_entered,
                ),
            ]
        )
        blocked = asyncio.Event()

        async def sleep(delay):
            await blocked.wait()

        stream = PortfolioMarginOrderEventStream(
            api,
            "wss://fstream.binance.com/pm",
            connector=connector,
            sleep=sleep,
            run_sync=run_sync_inline,
        )
        producer = asyncio.create_task(stream.run_network())
        await asyncio.wait_for(second_connection_entered.wait(), timeout=1)
        stream.request_stop()
        await asyncio.wait_for(producer, timeout=1)

        assert [call["url"] for call in connector.calls] == [
            "wss://fstream.binance.com/pm/ws/listen-key-1",
            "wss://fstream.binance.com/pm/ws/listen-key-2",
        ]
        assert api.calls == ["start", "close", "start", "close"]
        lifecycle = [signal async for signal in stream.lifecycle_events()]
        assert [signal.kind for signal in lifecycle] == [
            StreamLifecycleKind.CONNECTED,
            StreamLifecycleKind.RECONNECTING,
            StreamLifecycleKind.LISTEN_KEY_REBUILT,
            StreamLifecycleKind.RECONNECTED,
            StreamLifecycleKind.STOPPED,
        ]
        assert lifecycle[1].reason == "listen_key_expired"
        assert lifecycle[2].reason == "listen_key_expired"

    asyncio.run(scenario())


def test_keepalive_minus_1125_rebuilds_expired_listen_key():
    class ExpiringKeepaliveApi(FakeUserStreamApi):
        def keepalive(self):
            self.calls.append("keepalive")
            raise BinanceRequestError(
                ErrorContext(
                    "PUT",
                    "/papi/v1/listenKey",
                    status_code=400,
                    code=-1125,
                    message="This listenKey does not exist.",
                )
            )

    async def scenario():
        api = ExpiringKeepaliveApi(["listen-key-1", "listen-key-2"])
        second_connection_entered = asyncio.Event()
        connector = FakeConnector(
            [
                FakeConnectContext(websocket=FakeWebSocket()),
                FakeConnectContext(
                    websocket=FakeWebSocket(),
                    entered=second_connection_entered,
                ),
            ]
        )
        blocked = asyncio.Event()
        keepalive_fired = False

        async def sleep(delay):
            nonlocal keepalive_fired
            if delay == 45 * 60 and not keepalive_fired:
                keepalive_fired = True
                return
            await blocked.wait()

        stream = PortfolioMarginOrderEventStream(
            api,
            "wss://fstream.binance.com/pm",
            connector=connector,
            sleep=sleep,
            run_sync=run_sync_inline,
        )
        producer = asyncio.create_task(stream.run_network())
        await asyncio.wait_for(second_connection_entered.wait(), timeout=1)
        stream.request_stop()
        await asyncio.wait_for(producer, timeout=1)

        assert [call["url"] for call in connector.calls] == [
            "wss://fstream.binance.com/pm/ws/listen-key-1",
            "wss://fstream.binance.com/pm/ws/listen-key-2",
        ]
        assert api.calls == [
            "start",
            "keepalive",
            "close",
            "start",
            "close",
        ]

    asyncio.run(scenario())
