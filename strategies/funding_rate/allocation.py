"""Capital allocation specific to a delta-neutral funding position."""

from __future__ import annotations

from decimal import Decimal

from .models import FundingAllocation, _decimal


class FundingCapitalAllocator:
    """Split capital between Spot cash and perpetual initial margin.

    With leverage ``L`` and deployable capital ``C`` the matched notional is
    ``C * L / (L + 1)``.  The remaining ``C / (L + 1)`` is perpetual initial
    margin.  This is funding-strategy allocation; exchange filters and final
    quantity rounding are handled later by the generic planner.
    """

    def allocate(
        self,
        *,
        available_capital: Decimal | int | float | str,
        capital_fraction: Decimal | int | float | str,
        futures_leverage: Decimal | int | float | str,
        reference_price: Decimal | int | float | str,
    ) -> FundingAllocation:
        available = _decimal(available_capital)
        fraction = _decimal(capital_fraction)
        leverage = _decimal(futures_leverage)
        price = _decimal(reference_price)

        if available < 0:
            raise ValueError("available capital cannot be negative")
        if not Decimal("0") <= fraction <= Decimal("1"):
            raise ValueError("capital fraction must be between zero and one")
        if leverage <= 0:
            raise ValueError("futures leverage must be positive")
        if price <= 0:
            raise ValueError("reference price must be positive")

        deployed = available * fraction
        spot_notional = deployed * leverage / (leverage + Decimal("1"))
        futures_margin = deployed - spot_notional
        futures_notional = futures_margin * leverage

        return FundingAllocation(
            available_capital=available,
            deployed_capital=deployed,
            spot_notional=spot_notional,
            futures_margin=futures_margin,
            futures_notional=futures_notional,
            reference_price=price,
            base_quantity=spot_notional / price,
            futures_leverage=leverage,
        )
