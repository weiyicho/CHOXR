from decimal import Decimal

import pytest

from strategies.funding_rate import FundingCapitalAllocator


def test_allocation_matches_spot_and_futures_notional() -> None:
    allocation = FundingCapitalAllocator().allocate(
        available_capital="120",
        capital_fraction="0.5",
        futures_leverage="5",
        reference_price="10",
    )

    assert allocation.deployed_capital == Decimal("60.0")
    assert allocation.spot_notional == Decimal("50.0")
    assert allocation.futures_margin == Decimal("10.0")
    assert allocation.futures_notional == allocation.spot_notional
    assert allocation.base_quantity == Decimal("5.0")


@pytest.mark.parametrize("fraction", ["-0.1", "1.1"])
def test_allocation_rejects_invalid_capital_fraction(fraction: str) -> None:
    with pytest.raises(ValueError):
        FundingCapitalAllocator().allocate(
            available_capital="100",
            capital_fraction=fraction,
            futures_leverage="5",
            reference_price="10",
        )
