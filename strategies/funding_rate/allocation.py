"""Capital allocation specific to a delta-neutral funding position."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


def _decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class FundingAllocation:
    """Capital and matched base quantity approved for one funding position."""

    available_capital: Decimal
    deployed_capital: Decimal
    spot_notional: Decimal
    futures_margin: Decimal
    futures_notional: Decimal
    reference_price: Decimal
    futures_reference_price: Decimal
    base_quantity: Decimal
    futures_leverage: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "available_capital",
            "deployed_capital",
            "spot_notional",
            "futures_margin",
            "futures_notional",
            "reference_price",
            "futures_reference_price",
            "base_quantity",
            "futures_leverage",
        ):
            object.__setattr__(self, field_name, _decimal(getattr(self, field_name)))

        if self.available_capital < 0 or self.deployed_capital < 0:
            raise ValueError("capital cannot be negative")
        if self.deployed_capital > self.available_capital:
            raise ValueError("deployed capital exceeds available capital")
        if self.reference_price <= 0:
            raise ValueError("Spot reference price must be positive")
        if self.futures_reference_price <= 0:
            raise ValueError("futures reference price must be positive")
        if self.futures_leverage <= 0:
            raise ValueError("futures leverage must be positive")
        if self.base_quantity < 0:
            raise ValueError("base quantity cannot be negative")

    @property
    def spot_quantity(self) -> Decimal:
        """Positive Spot BUY quantity before exchange filter rounding."""

        return self.base_quantity

    @property
    def futures_quantity(self) -> Decimal:
        """Positive perpetual SELL quantity before exchange filter rounding."""

        return self.base_quantity


class FundingCapitalAllocator:
    """Split capital between Spot cash and perpetual initial margin.

    For Spot ask ``Ps``, perpetual bid ``Pf``, leverage ``L`` and deployable
    capital ``C``, matched base quantity is ``C / (Ps + Pf / L)``.  This uses
    the same base quantity for both legs while accounting for the small price
    difference between Spot and perpetual. Exchange filters and final quantity
    rounding are handled later by the generic planner.
    """

    def allocate(
        self,
        *,
        available_capital: Decimal | int | float | str,
        capital_fraction: Decimal | int | float | str,
        futures_leverage: Decimal | int | float | str,
        reference_price: Decimal | int | float | str,
        futures_reference_price: Decimal | int | float | str | None = None,
    ) -> FundingAllocation:
        available = _decimal(available_capital)
        fraction = _decimal(capital_fraction)
        leverage = _decimal(futures_leverage)
        spot_price = _decimal(reference_price)
        futures_price = (
            spot_price
            if futures_reference_price is None
            else _decimal(futures_reference_price)
        )

        if available < 0:
            raise ValueError("available capital cannot be negative")
        if not Decimal("0") <= fraction <= Decimal("1"):
            raise ValueError("capital fraction must be between zero and one")
        if leverage <= 0:
            raise ValueError("futures leverage must be positive")
        if spot_price <= 0:
            raise ValueError("Spot reference price must be positive")
        if futures_price <= 0:
            raise ValueError("futures reference price must be positive")

        deployed = available * fraction
        base_quantity = deployed / (spot_price + futures_price / leverage)
        spot_notional = base_quantity * spot_price
        futures_notional = base_quantity * futures_price
        futures_margin = futures_notional / leverage

        return FundingAllocation(
            available_capital=available,
            deployed_capital=deployed,
            spot_notional=spot_notional,
            futures_margin=futures_margin,
            futures_notional=futures_notional,
            reference_price=spot_price,
            futures_reference_price=futures_price,
            base_quantity=base_quantity,
            futures_leverage=leverage,
        )
