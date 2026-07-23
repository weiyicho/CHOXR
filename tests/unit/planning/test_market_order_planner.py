from decimal import Decimal

import pytest

from engine.domain.instrument import InstrumentId, SymbolRules
from engine.domain.order import OrderType, Side
from engine.planning import (
    MarketOrderPlanner,
    MarketOrderRequest,
    SymbolNormalizationError,
)


def symbol_rules(
    min_quantity: str = "0.005",
    *,
    market_quantity_increment: str | None = None,
    market_min_quantity: str | None = None,
    market_max_quantity: str | None = None,
    trading_enabled: bool = True,
) -> SymbolRules:
    instrument = InstrumentId("binance", "SPOT", "ETHUSDT")
    return SymbolRules(
        instrument,
        "ETH",
        "USDT",
        price_increment="0.01",
        quantity_increment="0.005",
        min_quantity=min_quantity,
        market_quantity_increment=market_quantity_increment,
        market_min_quantity=market_min_quantity,
        market_max_quantity=market_max_quantity,
        min_notional="5",
        trading_enabled=trading_enabled,
    )


def test_market_planner_normalizes_exact_quantity_without_funding_semantics() -> None:
    rules = symbol_rules()
    plan = MarketOrderPlanner().plan(
        MarketOrderRequest(
            execution_id="execution-1",
            client_order_id="execution-1-spot-hedge",
            instrument=rules.instrument,
            side=Side.BUY,
            desired_quantity="1.019",
            symbol_rules=rules,
            reason="external_fill_hedge",
        )
    )

    assert plan.normalized_quantity == Decimal("1.015")
    assert plan.intent.quantity == Decimal("1.015")
    assert plan.intent.order_type is OrderType.MARKET
    assert plan.intent.price is None
    assert plan.intent.post_only is False


def test_market_planner_rejects_quantity_below_minimum_after_rounding() -> None:
    rules = symbol_rules(min_quantity="0.01")
    with pytest.raises(SymbolNormalizationError, match="min_quantity"):
        MarketOrderPlanner().plan(
            MarketOrderRequest(
                execution_id="execution-1",
                client_order_id="execution-1-order-1",
                instrument=rules.instrument,
                side=Side.SELL,
                desired_quantity="0.009",
                symbol_rules=rules,
            )
        )


def test_market_planner_prefers_distinct_market_quantity_constraints() -> None:
    rules = symbol_rules(
        market_quantity_increment="0.01",
        market_min_quantity="0.01",
        market_max_quantity="1",
    )
    plan = MarketOrderPlanner().plan(
        MarketOrderRequest(
            execution_id="execution-1",
            client_order_id="execution-1-order-1",
            instrument=rules.instrument,
            side=Side.BUY,
            desired_quantity="1.019",
            symbol_rules=rules,
        )
    )

    assert plan.normalized_quantity == Decimal("1.0")
    assert plan.intent.quantity == Decimal("1.0")


def test_market_planner_fails_closed_when_trading_is_disabled() -> None:
    rules = symbol_rules(trading_enabled=False)
    with pytest.raises(SymbolNormalizationError, match="trading is disabled"):
        MarketOrderPlanner().plan(
            MarketOrderRequest(
                execution_id="execution-1",
                client_order_id="execution-1-order-1",
                instrument=rules.instrument,
                side=Side.BUY,
                desired_quantity="1",
                symbol_rules=rules,
            )
        )
