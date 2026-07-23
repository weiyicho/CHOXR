"""Account observations used by generic sizing and risk checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from ._numbers import ZERO, as_decimal
from .instrument import InstrumentId
from .position import PositionSnapshot


@dataclass(frozen=True)
class BalanceSnapshot:
    asset: str
    total: Decimal
    available: Decimal
    locked: Decimal = ZERO
    borrowed: Decimal = ZERO

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset", self.asset.strip())
        for name in ("total", "available", "locked", "borrowed"):
            object.__setattr__(self, name, as_decimal(getattr(self, name)))
        if not self.asset:
            raise ValueError("asset is required")
        if self.locked < ZERO:
            raise ValueError("locked balance cannot be negative")
        if self.borrowed < ZERO:
            raise ValueError("borrowed balance cannot be negative")

    @property
    def net(self) -> Decimal:
        return self.total - self.borrowed


@dataclass(frozen=True)
class AccountSnapshot:
    venue: str
    balances: Tuple[BalanceSnapshot, ...] = ()
    positions: Tuple[PositionSnapshot, ...] = ()
    equity: Optional[Decimal] = None
    available_margin: Optional[Decimal] = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(self, "venue", self.venue.strip())
        object.__setattr__(self, "balances", tuple(self.balances))
        object.__setattr__(self, "positions", tuple(self.positions))
        if not self.venue:
            raise ValueError("venue is required")
        for name in ("equity", "available_margin"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, as_decimal(value))
        assets = [balance.asset for balance in self.balances]
        if len(assets) != len(set(assets)):
            raise ValueError("account snapshot contains duplicate balance assets")
        instruments = [position.instrument for position in self.positions]
        if len(instruments) != len(set(instruments)):
            raise ValueError("account snapshot contains duplicate positions")

    def find_balance(self, asset: str) -> Optional[BalanceSnapshot]:
        return next(
            (balance for balance in self.balances if balance.asset == asset),
            None,
        )

    def find_position(self, instrument: InstrumentId) -> Optional[PositionSnapshot]:
        return next(
            (position for position in self.positions if position.instrument == instrument),
            None,
        )
