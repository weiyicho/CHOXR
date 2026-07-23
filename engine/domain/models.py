"""Compatibility import surface for the generic domain models.

New code should import from the focused modules (``order``, ``position``,
``instrument`` and ``account``).  This module intentionally contains no
strategy-specific execution target or Binance market assumptions.
"""

from ._numbers import ZERO, as_decimal
from .account import AccountSnapshot, BalanceSnapshot
from .instrument import InstrumentId, OrderBookLevel, OrderBookSnapshot, SymbolRules
from .order import (
    OrderIntent,
    OrderRecord,
    OrderState,
    OrderType,
    Side,
    TimeInForce,
)
from .order_event import OrderEvent, OrderEventKind
from .position import PositionSnapshot, PositionTarget

__all__ = [
    "AccountSnapshot",
    "BalanceSnapshot",
    "InstrumentId",
    "OrderBookLevel",
    "OrderBookSnapshot",
    "OrderEvent",
    "OrderEventKind",
    "OrderIntent",
    "OrderRecord",
    "OrderState",
    "OrderType",
    "PositionSnapshot",
    "PositionTarget",
    "Side",
    "SymbolRules",
    "TimeInForce",
    "ZERO",
    "as_decimal",
]
