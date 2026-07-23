"""Generic pre-trade risk contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from engine.domain.account import AccountSnapshot


ZERO = Decimal("0")
ONE = Decimal("1")


def _decimal(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: Decimal | None = None
    max_gross_notional: Decimal | None = None
    max_instrument_notional: Decimal | None = None
    max_available_capital_fraction: Decimal = ONE
    min_remaining_available_capital: Decimal = ZERO
    allowed_venues: tuple[str, ...] = ()
    allowed_markets: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "max_order_notional",
            "max_gross_notional",
            "max_instrument_notional",
        ):
            value = getattr(self, name)
            if value is not None:
                value = _decimal(value)
                object.__setattr__(self, name, value)
                if value <= ZERO:
                    raise ValueError(f"{name} must be positive")
        object.__setattr__(
            self,
            "max_available_capital_fraction",
            _decimal(self.max_available_capital_fraction),
        )
        object.__setattr__(
            self,
            "min_remaining_available_capital",
            _decimal(self.min_remaining_available_capital),
        )
        if not ZERO < self.max_available_capital_fraction <= ONE:
            raise ValueError("max_available_capital_fraction must be in (0, 1]")
        if self.min_remaining_available_capital < ZERO:
            raise ValueError("min_remaining_available_capital cannot be negative")


@dataclass(frozen=True)
class RiskContext:
    """Current exposure and capital estimates needed for one decision.

    Risk deliberately does not guess leverage or margin rules.  A market/account
    adapter may provide ``required_capital`` and ``available_capital``.  For a
    simple cash order the conservative defaults are full order notional and the
    available quote balance.
    """

    account: AccountSnapshot
    quote_asset: str
    current_gross_notional: Decimal = ZERO
    current_instrument_notional: Decimal = ZERO
    reference_price: Decimal | None = None
    required_capital: Decimal | None = None
    available_capital: Decimal | None = None
    increases_exposure: bool = True

    def __post_init__(self) -> None:
        if not self.quote_asset.strip():
            raise ValueError("quote_asset is required")
        for name in (
            "current_gross_notional",
            "current_instrument_notional",
            "reference_price",
            "required_capital",
            "available_capital",
        ):
            value = getattr(self, name)
            if value is not None:
                value = _decimal(value)
                object.__setattr__(self, name, value)
                if value < ZERO:
                    raise ValueError(f"{name} cannot be negative")


@dataclass(frozen=True)
class RiskViolation:
    code: str
    message: str


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    order_notional: Decimal
    required_capital: Decimal
    available_capital: Decimal
    projected_gross_notional: Decimal
    projected_instrument_notional: Decimal
    violations: tuple[RiskViolation, ...] = ()

    @property
    def violation_codes(self) -> tuple[str, ...]:
        return tuple(violation.code for violation in self.violations)
