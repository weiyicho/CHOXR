from decimal import Decimal

import pytest

from engine.domain.instrument import InstrumentId, SymbolRules
from engine.domain.order import OrderIntent, OrderRecord, OrderState, Side
from strategies.funding_rate import FundingEntryCoordinator


PERPETUAL = InstrumentId("binance", "USD_M_PERPETUAL", "ETHUSDT")
SPOT = InstrumentId("binance", "MARGIN_SPOT", "ETHUSDT")
SPOT_RULES = SymbolRules(
    instrument=SPOT,
    base_asset="ETH",
    quote_asset="USDT",
    price_increment=Decimal("0.01"),
    quantity_increment=Decimal("0.001"),
    min_quantity=Decimal("0.001"),
)


def perpetual_order(cumulative: str) -> OrderRecord:
    return OrderRecord(
        intent=OrderIntent(
            execution_id="funding-entry-1",
            client_order_id="perp-maker-1",
            instrument=PERPETUAL,
            side=Side.SELL,
            quantity=Decimal("1"),
        ),
        state=OrderState.PARTIALLY_FILLED,
        cumulative_quantity=Decimal(cumulative),
    )


def test_each_new_perpetual_fill_creates_only_the_incremental_spot_hedge() -> None:
    coordinator = FundingEntryCoordinator()

    first = coordinator.plan_spot_hedge(
        perpetual_order=perpetual_order("0.4"),
        spot_instrument=SPOT,
        spot_rules=SPOT_RULES,
        previously_hedged_quantity="0",
    )
    second = coordinator.plan_spot_hedge(
        perpetual_order=perpetual_order("0.6"),
        spot_instrument=SPOT,
        spot_rules=SPOT_RULES,
        previously_hedged_quantity="0.4",
    )

    assert first.market_order.intent.quantity == Decimal("0.4")
    assert second.market_order.intent.quantity == Decimal("0.2")
    assert first.market_order.intent.side is Side.BUY
    assert first.market_order.intent.instrument == SPOT


def test_replayed_cumulative_fill_does_not_create_another_spot_order() -> None:
    result = FundingEntryCoordinator().plan_spot_hedge(
        perpetual_order=perpetual_order("0.4"),
        spot_instrument=SPOT,
        spot_rules=SPOT_RULES,
        previously_hedged_quantity="0.4",
    )

    assert result is None


def test_hedged_quantity_cannot_exceed_observed_fill() -> None:
    with pytest.raises(ValueError, match="exceeds observed"):
        FundingEntryCoordinator().plan_spot_hedge(
            perpetual_order=perpetual_order("0.4"),
            spot_instrument=SPOT,
            spot_rules=SPOT_RULES,
            previously_hedged_quantity="0.5",
        )
