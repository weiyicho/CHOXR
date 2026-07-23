"""Read-only market data needed by planners and pricing policies."""

from __future__ import annotations

from typing import Optional, Protocol

from engine.domain.instrument import InstrumentId, OrderBookSnapshot, SymbolRules


class MarketDataGateway(Protocol):
    def get_order_book(
        self,
        instrument: InstrumentId,
        depth: Optional[int] = None,
    ) -> OrderBookSnapshot: ...

    def get_symbol_rules(self, instrument: InstrumentId) -> SymbolRules: ...
