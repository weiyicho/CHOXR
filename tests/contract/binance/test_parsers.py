from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.binance.parsers.accounts import parse_account, parse_funding_income
from adapters.binance.parsers.order_books import parse_order_book
from adapters.binance.parsers.order_events import parse_order_event
from adapters.binance.parsers.orders import parse_margin_order, parse_um_order
from adapters.binance.parsers.symbol_rules import parse_exchange_info


def exchange_info_payload():
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
                        "minQty": "0.001",
                        "maxQty": "1000",
                        "stepSize": "0.001",
                    },
                    {
                        "filterType": "MARKET_LOT_SIZE",
                        "minQty": "0.01",
                        "maxQty": "250",
                        "stepSize": "0.01",
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


def test_exchange_info_and_order_book_preserve_decimal_strings():
    rules = parse_exchange_info(exchange_info_payload(), "ETHUSDT")
    book = parse_order_book(
        "ETHUSDT",
        {
            "lastUpdateId": 42,
            "bids": [["3210.01", "1.250"]],
            "asks": [["3210.02", "0.750"]],
        },
    )

    assert rules.price_tick == Decimal("0.01")
    assert rules.quantity_step == Decimal("0.001")
    assert rules.min_notional == Decimal("5")
    assert rules.max_notional == Decimal("500000")
    assert rules.market_max_quantity == Decimal("250")
    assert book.bids[0].quantity == Decimal("1.250")
    assert book.asks[0].price == Decimal("3210.02")


def test_zero_market_lot_rules_fall_back_to_general_lot_size():
    payload = exchange_info_payload()
    market_lot_size = next(
        item
        for item in payload["symbols"][0]["filters"]
        if item["filterType"] == "MARKET_LOT_SIZE"
    )
    market_lot_size.update(
        {
            "minQty": "0.00000000",
            "maxQty": "2829.36596416",
            "stepSize": "0.00000000",
        }
    )

    rules = parse_exchange_info(payload, "ETHUSDT")

    assert rules.market_quantity_step is None
    assert rules.market_min_quantity is None
    assert rules.market_max_quantity == Decimal("2829.36596416")


def test_margin_and_um_order_responses_map_to_one_snapshot_shape():
    common = {
        "symbol": "ETHUSDT",
        "orderId": 10,
        "clientOrderId": "order-1",
        "status": "PARTIALLY_FILLED",
        "side": "BUY",
        "type": "LIMIT",
        "origQty": "0.100",
        "executedQty": "0.025",
        "price": "3200",
    }
    margin = parse_margin_order({**common, "cummulativeQuoteQty": "80"})
    um = parse_um_order(
        {
            **common,
            "cumQuote": "80",
            "avgPrice": "3200",
            "reduceOnly": True,
            "positionSide": "BOTH",
        }
    )

    assert margin.average_price == Decimal("3200")
    assert um.average_price == Decimal("3200")
    assert um.reduce_only is True
    assert um.leaves_quantity == Decimal("0.075")


def test_um_new_order_result_accepts_cum_qty_without_executed_qty():
    order = parse_um_order(
        {
            "symbol": "ETHUSDT",
            "orderId": 11,
            "clientOrderId": "um-1",
            "status": "PARTIALLY_FILLED",
            "side": "SELL",
            "type": "LIMIT",
            "origQty": "0.100",
            "cumQty": "0.025",
            "cumQuote": "80",
            "price": "3200",
            "avgPrice": "3200",
        }
    )

    assert order.executed_quantity == Decimal("0.025")
    assert order.leaves_quantity == Decimal("0.075")


def test_filled_market_response_with_zero_price_stays_unpriced_until_query():
    order = parse_um_order(
        {
            "symbol": "DOGEUSDT",
            "orderId": 12,
            "clientOrderId": "um-market-1",
            "status": "FILLED",
            "side": "BUY",
            "type": "MARKET",
            "origQty": "69",
            "executedQty": "69",
            "cumQuote": "0",
            "avgPrice": "0",
            "price": "0",
        }
    )

    assert order.executed_quantity == Decimal("69")
    assert order.average_price is None


def test_user_stream_parses_margin_and_um_partial_fills():
    margin = parse_order_event(
        {
            "e": "executionReport",
            "E": 1_700_000_000_000,
            "T": 1_700_000_000_001,
            "s": "ETHUSDT",
            "c": "spot-1",
            "C": "",
            "i": 10,
            "S": "BUY",
            "o": "MARKET",
            "x": "TRADE",
            "X": "PARTIALLY_FILLED",
            "q": "0.1",
            "l": "0.025",
            "z": "0.025",
            "L": "3200",
            "Z": "80",
            "t": 7,
            "n": "0.000025",
            "N": "ETH",
            "r": "NONE",
        }
    )
    um = parse_order_event(
        {
            "e": "ORDER_TRADE_UPDATE",
            "E": 1_700_000_000_000,
            "T": 1_700_000_000_001,
            "o": {
                "s": "ETHUSDT",
                "c": "um-1",
                "i": 11,
                "S": "SELL",
                "o": "LIMIT",
                "x": "TRADE",
                "X": "PARTIALLY_FILLED",
                "q": "0.1",
                "l": "0.025",
                "z": "0.025",
                "L": "3201",
                "ap": "3201",
                "t": 8,
                "n": "0.0125",
                "N": "USDT",
                "R": False,
                "ps": "BOTH",
            },
        }
    )

    assert margin.market == "MARGIN"
    assert margin.average_price == Decimal("3200")
    assert margin.last_executed_quantity == Decimal("0.025")
    assert margin.last_executed_price == Decimal("3200")
    assert margin.trade_id == 7
    assert margin.commission == Decimal("0.000025")
    assert margin.commission_asset == "ETH"
    assert um.market == "USD_M_FUTURES"
    assert um.cumulative_quantity == Decimal("0.025")
    assert um.last_executed_quantity == Decimal("0.025")
    assert um.last_executed_price == Decimal("3201")
    assert um.trade_id == 8
    assert um.commission == Decimal("0.0125")
    assert um.commission_asset == "USDT"


def test_user_stream_order_event_allows_missing_trade_metadata():
    event = parse_order_event(
        {
            "e": "executionReport",
            "E": 1_700_000_000_000,
            "s": "ETHUSDT",
            "c": "spot-1",
            "i": 10,
            "S": "BUY",
            "o": "LIMIT",
            "x": "NEW",
            "X": "NEW",
            "q": "0.1",
            "z": "0",
            "Z": "0",
            "r": "NONE",
        }
    )

    assert event.last_executed_quantity is None
    assert event.last_executed_price is None
    assert event.trade_id is None
    assert event.commission is None
    assert event.commission_asset is None


@pytest.mark.parametrize("field_name", ["l", "L", "n"])
def test_user_stream_order_event_rejects_negative_trade_decimals(field_name):
    payload = {
        "e": "executionReport",
        "E": 1_700_000_000_000,
        "s": "ETHUSDT",
        "c": "spot-1",
        "i": 10,
        "S": "BUY",
        "o": "MARKET",
        "x": "TRADE",
        "X": "PARTIALLY_FILLED",
        "q": "0.1",
        "l": "0.025",
        "z": "0.025",
        "L": "3200",
        "Z": "80",
        "t": 7,
        "n": "0.000025",
        "N": "ETH",
        "r": "NONE",
    }
    payload[field_name] = "-0.01"

    with pytest.raises(ValueError, match="cannot be negative"):
        parse_order_event(payload)


def test_funding_parser_excludes_non_funding_income():
    parsed = parse_funding_income(
        [
            {
                "symbol": "ETHUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "1.25",
                "asset": "USDT",
                "time": 100,
                "tranId": "900719925474099312345",
                "tradeId": "",
            },
            {
                "symbol": "ETHUSDT",
                "incomeType": "COMMISSION",
                "income": "-0.1",
                "asset": "USDT",
                "time": 101,
            },
        ]
    )

    assert len(parsed) == 1
    assert parsed[0].income == Decimal("1.25")
    assert parsed[0].transaction_id == "900719925474099312345"


def test_papi_account_parser_only_uses_documented_account_fields():
    account = parse_account(
        {
            "accountEquity": "1000",
            "actualEquity": "990",
            "totalAvailableBalance": "900",
            "accountInitialMargin": "100",
            "accountMaintMargin": "10",
            "uniMMR": "100",
            "accountStatus": "NORMAL",
        }
    )

    assert account.account_equity == Decimal("1000")
    assert account.account_status == "NORMAL"
    assert not hasattr(account, "unrealized_pnl")
