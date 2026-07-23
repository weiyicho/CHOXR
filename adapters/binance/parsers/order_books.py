from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import OrderBookSnapshot, PriceLevel


def _levels(values: list[list[str]]) -> tuple[PriceLevel, ...]:
    return tuple(PriceLevel(Decimal(price), Decimal(quantity)) for price, quantity in values)


def parse_order_book(symbol: str, payload: dict[str, Any]) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol=symbol,
        last_update_id=int(payload["lastUpdateId"]),
        bids=_levels(payload.get("bids", [])),
        asks=_levels(payload.get("asks", [])),
        event_time_ms=int(payload["E"]) if "E" in payload else None,
        transaction_time_ms=int(payload["T"]) if "T" in payload else None,
    )
