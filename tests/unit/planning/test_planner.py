from decimal import Decimal

import pytest

from engine.domain.account import AccountSnapshot, BalanceSnapshot
from engine.domain.instrument import (
    InstrumentId,
    OrderBookLevel,
    OrderBookSnapshot,
    SymbolRules,
)
from engine.domain.order import OrderType, Side, TimeInForce
from engine.planning import (
    CapitalBudget,
    OrderPlanner,
    PlanningRequest,
    SymbolNormalizationError,
)


def test_planner_turns_budget_account_book_and_rules_into_exact_intent() -> None:
    instrument = InstrumentId("binance", "SPOT", "ETHUSDT")
    account = AccountSnapshot(
        venue="binance",
        balances=(BalanceSnapshot("USDT", "1000", "1000"),),
        positions=(),
    )
    order_book = OrderBookSnapshot(
        instrument,
        bids=(OrderBookLevel("100", "5"),),
        asks=(OrderBookLevel("101", "5"),),
    )
    symbol_rules = SymbolRules(
        instrument,
        "ETH",
        "USDT",
        price_increment="0.1",
        quantity_increment="0.1",
        min_quantity="0.1",
        min_notional="5",
    )

    plan = OrderPlanner().plan(
        PlanningRequest(
            execution_id="execution-1",
            client_order_id="execution-1-order-1",
            instrument=instrument,
            side=Side.BUY,
            budget=CapitalBudget("250", "USDT"),
            account=account,
            order_book=order_book,
            symbol_rules=symbol_rules,
        )
    )

    assert plan.normalized_price == Decimal("100")
    assert plan.raw_quantity == Decimal("2.5")
    assert plan.normalized_quantity == Decimal("2.5")
    assert plan.order_notional == Decimal("250.0")
    assert plan.intent.order_type is OrderType.LIMIT
    assert plan.intent.time_in_force is TimeInForce.GTC
    assert plan.intent.post_only is True
    assert plan.intent.price == Decimal("100")
    assert plan.intent.quantity == Decimal("2.5")


def test_maker_planner_fails_closed_when_trading_is_disabled() -> None:
    instrument = InstrumentId("any-venue", "SPOT", "ETHUSD")
    account = AccountSnapshot(
        venue="any-venue",
        balances=(BalanceSnapshot("USD", "1000", "1000"),),
    )
    order_book = OrderBookSnapshot(
        instrument,
        bids=(OrderBookLevel("100", "5"),),
        asks=(OrderBookLevel("101", "5"),),
    )
    rules = SymbolRules(
        instrument,
        "ETH",
        "USD",
        price_increment="0.1",
        quantity_increment="0.1",
        min_quantity="0.1",
        min_notional="5",
        trading_enabled=False,
    )

    with pytest.raises(SymbolNormalizationError, match="trading is disabled"):
        OrderPlanner().plan(
            PlanningRequest(
                execution_id="execution-1",
                client_order_id="execution-1-order-1",
                instrument=instrument,
                side=Side.BUY,
                budget=CapitalBudget("250", "USD"),
                account=account,
                order_book=order_book,
                symbol_rules=rules,
            )
        )
