"""Decimal helpers shared by the domain model.

Trading quantities and prices must never pass through binary floating-point
arithmetic inside the engine.  Adapters may accept exchange payloads as strings
and normalize them with :func:`as_decimal` at the domain boundary.
"""

from __future__ import annotations

from decimal import Decimal


ZERO = Decimal("0")


def as_decimal(value: Decimal | int | float | str) -> Decimal:
    """Return *value* as a :class:`Decimal` without float-rounding surprises."""

    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
