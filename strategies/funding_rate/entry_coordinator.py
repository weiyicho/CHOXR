"""Coordinate the strategy-specific maker-perpetual/taker-Spot entry."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from engine.domain.instrument import InstrumentId, SymbolRules
from engine.domain.order import OrderRecord, Side
from engine.planning import MarketOrderPlan, MarketOrderPlanner, MarketOrderRequest


@dataclass(frozen=True)
class SpotHedgePlan:
    source_perpetual_client_order_id: str
    cumulative_perpetual_fill: Decimal
    previously_hedged_quantity: Decimal
    incremental_hedge_quantity: Decimal
    market_order: MarketOrderPlan


class FundingEntryCoordinator:
    """Create a Spot taker hedge for each new perpetual maker fill.

    ``previously_hedged_quantity`` is explicit so a durable strategy session can
    restore progress after restart. Replaying the same cumulative fill produces
    no new order. The generated client order ID is deterministic for the source
    order and cumulative fill.
    """

    def __init__(self, market_planner: MarketOrderPlanner | None = None) -> None:
        self._market_planner = market_planner or MarketOrderPlanner()

    def plan_spot_hedge(
        self,
        *,
        perpetual_order: OrderRecord,
        spot_instrument: InstrumentId,
        spot_rules: SymbolRules,
        previously_hedged_quantity: Decimal | int | float | str,
    ) -> SpotHedgePlan | None:
        hedged = (
            previously_hedged_quantity
            if isinstance(previously_hedged_quantity, Decimal)
            else Decimal(str(previously_hedged_quantity))
        )
        cumulative = perpetual_order.cumulative_quantity
        if hedged < 0:
            raise ValueError("previously hedged quantity cannot be negative")
        if hedged > cumulative:
            raise ValueError("hedged quantity exceeds observed perpetual fills")

        incremental = cumulative - hedged
        if incremental == 0:
            return None
        if spot_rules.instrument != spot_instrument:
            raise ValueError("Spot rules do not match the Spot instrument")
        if perpetual_order.intent.instrument == spot_instrument:
            raise ValueError("Spot and perpetual legs must be different instruments")

        client_order_id = self._hedge_client_order_id(
            perpetual_order.intent.client_order_id,
            cumulative,
        )
        market_order = self._market_planner.plan(
            MarketOrderRequest(
                execution_id=perpetual_order.intent.execution_id,
                client_order_id=client_order_id,
                instrument=spot_instrument,
                side=Side.BUY,
                desired_quantity=incremental,
                symbol_rules=spot_rules,
                reason="funding_rate_spot_hedge",
            )
        )
        return SpotHedgePlan(
            source_perpetual_client_order_id=perpetual_order.intent.client_order_id,
            cumulative_perpetual_fill=cumulative,
            previously_hedged_quantity=hedged,
            incremental_hedge_quantity=market_order.normalized_quantity,
            market_order=market_order,
        )

    @staticmethod
    def _hedge_client_order_id(
        perpetual_client_order_id: str,
        cumulative_fill: Decimal,
    ) -> str:
        key = f"{perpetual_client_order_id}:{cumulative_fill}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return f"frh-{digest}"
