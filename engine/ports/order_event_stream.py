"""Streaming boundary for normalized exchange order events."""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from engine.domain.order_event import OrderEvent


class OrderEventStream(Protocol):
    def events(self) -> AsyncIterator[OrderEvent]: ...
