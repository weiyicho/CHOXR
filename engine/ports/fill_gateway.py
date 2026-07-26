"""Read-only fill history used to repair WebSocket gaps."""

from __future__ import annotations

from typing import Protocol

from engine.domain.instrument import InstrumentId
from engine.domain.order_fill import OrderFill


class OrderFillGateway(Protocol):
    def list_order_fills(
        self,
        instrument: InstrumentId,
        exchange_order_id: str,
    ) -> tuple[OrderFill, ...]: ...
