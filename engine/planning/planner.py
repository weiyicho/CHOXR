"""Composition root for generic account-aware order planning."""

from __future__ import annotations

from engine.domain.order import OrderIntent, OrderType, TimeInForce

from .capital_sizer import CapitalSizer
from .maker_price_policy import MakerPricePolicy
from .models import ExecutionPlan, PlanningRequest
from .price_policy import PricePolicy
from .quantity_calculator import QuantityCalculator
from .symbol_normalizer import SymbolNormalizer


class OrderPlanner:
    def __init__(
        self,
        *,
        capital_sizer: CapitalSizer | None = None,
        quantity_calculator: QuantityCalculator | None = None,
        price_policy: PricePolicy | None = None,
        normalizer: SymbolNormalizer | None = None,
    ) -> None:
        self._capital_sizer = capital_sizer or CapitalSizer()
        self._quantity_calculator = quantity_calculator or QuantityCalculator()
        self._price_policy = price_policy or MakerPricePolicy()
        self._normalizer = normalizer or SymbolNormalizer()

    def plan(self, request: PlanningRequest) -> ExecutionPlan:
        self._normalizer.ensure_trading_enabled(request.symbol_rules)
        allocation = self._capital_sizer.size(request.account, request.budget)
        quote = self._price_policy.quote(
            request.order_book,
            request.side,
            request.symbol_rules,
            request.price_parameters,
        )
        price = self._normalizer.normalize_maker_price(
            quote.desired_price,
            request.side,
            request.order_book,
            request.symbol_rules,
        )
        raw_quantity = self._quantity_calculator.from_notional(
            allocation.approved_notional, price
        )
        quantity = self._normalizer.normalize_quantity(
            raw_quantity, request.symbol_rules
        )
        order_notional = self._normalizer.validate_notional(
            price, quantity, request.symbol_rules
        )
        intent = OrderIntent(
            execution_id=request.execution_id,
            client_order_id=request.client_order_id,
            instrument=request.instrument,
            side=request.side,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=price,
            time_in_force=TimeInForce.GTC,
            reduce_only=request.reduce_only,
            post_only=True,
            reason=request.reason,
        )
        return ExecutionPlan(
            request=request,
            allocation=allocation,
            price_quote=quote,
            raw_quantity=raw_quantity,
            normalized_price=price,
            normalized_quantity=quantity,
            order_notional=order_notional,
            intent=intent,
        )
