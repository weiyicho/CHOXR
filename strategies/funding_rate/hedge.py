"""Pure delta and Spot-hedge calculations for the funding-rate strategy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR


ZERO = Decimal("0")
DecimalLike = Decimal | int | float | str


def _decimal(value: DecimalLike) -> Decimal:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    if not decimal_value.is_finite():
        raise ValueError("hedge calculation values must be finite")
    return decimal_value


@dataclass(frozen=True)
class HedgeCalculationInput:
    """Observed quantities and Spot market constraints for one calculation.

    ``spot_confirmed_quantity`` is the gross base quantity from confirmed Spot
    fills. ``spot_base_commission`` must contain only commission charged in the
    Spot base asset. ``spot_pending_quantity`` reserves already-submitted but
    not-yet-confirmed Spot hedges so a replay cannot plan the same hedge twice.

    ``quantity_step`` and ``min_quantity`` are the effective market-order
    constraints, not necessarily the symbol's regular limit-order constraints.
    """

    perpetual_filled_quantity: Decimal
    spot_confirmed_quantity: Decimal
    spot_base_commission: Decimal
    spot_pending_quantity: Decimal
    reference_price: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    delta_tolerance: Decimal = ZERO

    def __post_init__(self) -> None:
        for field_name in (
            "perpetual_filled_quantity",
            "spot_confirmed_quantity",
            "spot_base_commission",
            "spot_pending_quantity",
            "reference_price",
            "quantity_step",
            "min_quantity",
            "min_notional",
            "delta_tolerance",
        ):
            object.__setattr__(
                self,
                field_name,
                _decimal(getattr(self, field_name)),
            )

        for field_name in (
            "perpetual_filled_quantity",
            "spot_confirmed_quantity",
            "spot_base_commission",
            "spot_pending_quantity",
            "min_quantity",
            "min_notional",
            "delta_tolerance",
        ):
            if getattr(self, field_name) < ZERO:
                raise ValueError(f"{field_name} cannot be negative")

        if self.reference_price <= ZERO:
            raise ValueError("reference_price must be positive")
        if self.quantity_step <= ZERO:
            raise ValueError("quantity_step must be positive")
        if self.spot_base_commission > self.spot_confirmed_quantity:
            raise ValueError(
                "spot_base_commission cannot exceed spot_confirmed_quantity"
            )


@dataclass(frozen=True)
class HedgeDecision:
    """Calculated hedge state without any order-sequencing decision.

    ``net_delta`` uses the base-asset convention ``net Spot - short
    perpetual``. A negative value is underhedged; a positive value is
    overhedged. Pending orders are excluded because they are not confirmed
    exposure yet.

    ``estimated_notional`` is the notional of the step-normalized uncovered
    candidate before minimum filters. It remains informative when the
    candidate is classified entirely as dust.
    """

    target_spot_quantity: Decimal
    spot_net_quantity: Decimal
    pending_quantity: Decimal
    net_delta: Decimal
    uncovered_quantity: Decimal
    tradable_quantity: Decimal
    dust_quantity: Decimal
    estimated_notional: Decimal
    within_tolerance: bool


class FundingHedgeCalculator:
    """Calculate an incremental Spot hedge from confirmed cumulative state."""

    def calculate(
        self,
        calculation_input: HedgeCalculationInput,
    ) -> HedgeDecision:
        target = calculation_input.perpetual_filled_quantity
        spot_net = (
            calculation_input.spot_confirmed_quantity
            - calculation_input.spot_base_commission
        )
        net_delta = spot_net - target
        residual = target - spot_net - calculation_input.spot_pending_quantity
        uncovered = max(ZERO, residual)

        normalized_candidate = self._floor_to_step(
            uncovered,
            calculation_input.quantity_step,
        )
        estimated_notional = (
            normalized_candidate * calculation_input.reference_price
        )
        meets_minimums = (
            normalized_candidate > ZERO
            and normalized_candidate >= calculation_input.min_quantity
            and estimated_notional >= calculation_input.min_notional
        )
        tradable = normalized_candidate if meets_minimums else ZERO

        return HedgeDecision(
            target_spot_quantity=target,
            spot_net_quantity=spot_net,
            pending_quantity=calculation_input.spot_pending_quantity,
            net_delta=net_delta,
            uncovered_quantity=uncovered,
            tradable_quantity=tradable,
            dust_quantity=uncovered - tradable,
            estimated_notional=estimated_notional,
            within_tolerance=(
                abs(net_delta) <= calculation_input.delta_tolerance
            ),
        )

    @staticmethod
    def _floor_to_step(quantity: Decimal, step: Decimal) -> Decimal:
        return (
            (quantity / step).to_integral_value(rounding=ROUND_FLOOR)
            * step
        )
