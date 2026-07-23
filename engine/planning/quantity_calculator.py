"""Pure notional-to-quantity calculation."""

from __future__ import annotations

from decimal import Decimal


class QuantityCalculator:
    def from_notional(self, notional: Decimal, price: Decimal) -> Decimal:
        if notional <= 0:
            raise ValueError("notional must be positive")
        if price <= 0:
            raise ValueError("price must be positive")
        return notional / price
