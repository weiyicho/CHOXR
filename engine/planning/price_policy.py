"""Price-policy boundary used by the generic planner."""

from __future__ import annotations

from typing import Protocol

from engine.domain.instrument import OrderBookSnapshot, SymbolRules
from engine.domain.order import Side

from .models import MakerPriceParameters, PriceQuote


class PricePolicy(Protocol):
    def quote(
        self,
        order_book: OrderBookSnapshot,
        side: Side,
        rules: SymbolRules,
        parameters: MakerPriceParameters,
    ) -> PriceQuote: ...
