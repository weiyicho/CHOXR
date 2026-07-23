"""Exact-quantity planning for generic market/taker orders."""

from __future__ import annotations

from engine.domain.order import OrderIntent, OrderType

from .models import MarketOrderPlan, MarketOrderRequest
from .symbol_normalizer import SymbolNormalizer


class MarketOrderPlanner:
    """Normalize an exact desired quantity and emit a MARKET intent.

    A market order has no exact pre-trade price, so min/max-notional validation
    belongs in the pre-trade risk step using a fresh reference price.  Quantity
    filters are enforced here before an intent can reach execution.
    """

    def __init__(self, normalizer: SymbolNormalizer | None = None) -> None:
        self._normalizer = normalizer or SymbolNormalizer()

    def plan(self, request: MarketOrderRequest) -> MarketOrderPlan:
        self._normalizer.ensure_trading_enabled(request.symbol_rules)
        quantity = self._normalizer.normalize_market_quantity(
            request.desired_quantity, request.symbol_rules
        )
        intent = OrderIntent(
            execution_id=request.execution_id,
            client_order_id=request.client_order_id,
            instrument=request.instrument,
            side=request.side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            reduce_only=request.reduce_only,
            reason=request.reason,
        )
        return MarketOrderPlan(
            request=request,
            normalized_quantity=quantity,
            intent=intent,
        )
