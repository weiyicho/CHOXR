from decimal import Decimal

import pytest

from strategies.funding_rate.hedge import (
    FundingHedgeCalculator,
    HedgeCalculationInput,
)


def hedge_input(**overrides: str) -> HedgeCalculationInput:
    values = {
        "perpetual_filled_quantity": "0.6",
        "spot_confirmed_quantity": "0.4",
        "spot_base_commission": "0",
        "spot_pending_quantity": "0",
        "reference_price": "100",
        "quantity_step": "0.001",
        "min_quantity": "0.001",
        "min_notional": "0",
        "delta_tolerance": "0.0001",
    }
    values.update(overrides)
    return HedgeCalculationInput(**values)


def test_partial_cumulative_fill_produces_incremental_spot_quantity() -> None:
    decision = FundingHedgeCalculator().calculate(hedge_input())

    assert decision.target_spot_quantity == Decimal("0.6")
    assert decision.spot_net_quantity == Decimal("0.4")
    assert decision.net_delta == Decimal("-0.2")
    assert decision.uncovered_quantity == Decimal("0.2")
    assert decision.tradable_quantity == Decimal("0.2")
    assert decision.dust_quantity == Decimal("0.0")
    assert decision.estimated_notional == Decimal("20.0")
    assert decision.within_tolerance is False


def test_pending_hedge_reservation_prevents_duplicate_quantity() -> None:
    decision = FundingHedgeCalculator().calculate(
        hedge_input(spot_pending_quantity="0.2")
    )

    assert decision.pending_quantity == Decimal("0.2")
    assert decision.uncovered_quantity == Decimal("0")
    assert decision.tradable_quantity == Decimal("0")
    assert decision.dust_quantity == Decimal("0")
    # Pending orders are reservations, not confirmed delta.
    assert decision.net_delta == Decimal("-0.2")
    assert decision.within_tolerance is False


def test_base_asset_commission_reduces_confirmed_net_spot() -> None:
    decision = FundingHedgeCalculator().calculate(
        hedge_input(
            perpetual_filled_quantity="1",
            spot_confirmed_quantity="1",
            spot_base_commission="0.001",
            reference_price="10000",
        )
    )

    assert decision.spot_net_quantity == Decimal("0.999")
    assert decision.net_delta == Decimal("-0.001")
    assert decision.tradable_quantity == Decimal("0.001")
    assert decision.estimated_notional == Decimal("10.000")


def test_below_min_notional_is_kept_as_dust() -> None:
    decision = FundingHedgeCalculator().calculate(
        hedge_input(
            perpetual_filled_quantity="0.42",
            spot_confirmed_quantity="0.4",
            quantity_step="0.01",
            min_quantity="0.01",
            min_notional="5",
        )
    )

    assert decision.uncovered_quantity == Decimal("0.02")
    assert decision.estimated_notional == Decimal("2.00")
    assert decision.tradable_quantity == Decimal("0")
    assert decision.dust_quantity == Decimal("0.02")


def test_uncovered_quantity_is_rounded_down_to_market_step() -> None:
    decision = FundingHedgeCalculator().calculate(
        hedge_input(
            perpetual_filled_quantity="0.41234",
            spot_confirmed_quantity="0.4",
            quantity_step="0.001",
        )
    )

    assert decision.uncovered_quantity == Decimal("0.01234")
    assert decision.tradable_quantity == Decimal("0.012")
    assert decision.dust_quantity == Decimal("0.00034")


def test_overhedged_position_does_not_create_a_buy_action() -> None:
    decision = FundingHedgeCalculator().calculate(
        hedge_input(
            perpetual_filled_quantity="1",
            spot_confirmed_quantity="1.1",
            delta_tolerance="0.01",
        )
    )

    assert decision.net_delta == Decimal("0.1")
    assert decision.uncovered_quantity == Decimal("0")
    assert decision.tradable_quantity == Decimal("0")
    assert decision.dust_quantity == Decimal("0")
    assert decision.within_tolerance is False


def test_small_actual_delta_can_be_within_tolerance_while_remaining_dust() -> None:
    decision = FundingHedgeCalculator().calculate(
        hedge_input(
            perpetual_filled_quantity="1",
            spot_confirmed_quantity="0.9995",
            quantity_step="0.001",
            delta_tolerance="0.001",
        )
    )

    assert decision.net_delta == Decimal("-0.0005")
    assert decision.tradable_quantity == Decimal("0")
    assert decision.dust_quantity == Decimal("0.0005")
    assert decision.within_tolerance is True


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("perpetual_filled_quantity", "-0.1", "cannot be negative"),
        ("spot_confirmed_quantity", "-0.1", "cannot be negative"),
        ("spot_base_commission", "-0.1", "cannot be negative"),
        ("spot_pending_quantity", "-0.1", "cannot be negative"),
        ("reference_price", "0", "must be positive"),
        ("quantity_step", "0", "must be positive"),
        ("min_quantity", "-0.1", "cannot be negative"),
        ("min_notional", "-0.1", "cannot be negative"),
        ("delta_tolerance", "-0.1", "cannot be negative"),
        ("reference_price", "NaN", "must be finite"),
    ],
)
def test_invalid_inputs_are_rejected(
    field_name: str,
    value: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        FundingHedgeCalculator().calculate(
            hedge_input(**{field_name: value})
        )


def test_base_commission_cannot_exceed_confirmed_quantity() -> None:
    with pytest.raises(ValueError, match="cannot exceed"):
        hedge_input(
            spot_confirmed_quantity="0.01",
            spot_base_commission="0.02",
        )
