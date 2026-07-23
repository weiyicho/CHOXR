"""Order-book-aware maker pricing without exchange-specific assumptions."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from engine.domain.instrument import OrderBookLevel, OrderBookSnapshot, SymbolRules
from engine.domain.order import Side

from .models import MakerPriceParameters, PriceQuote, ZERO


class InvalidOrderBook(ValueError):
    pass


class MakerPricePolicy:
    """Propose a maker price from best levels and OBI/OBIV pressure.

    This class proposes a desired price.  The ``SymbolNormalizer`` remains the
    final authority that rounds it to a valid tick and prevents spread crossing.
    """

    def quote(
        self,
        order_book: OrderBookSnapshot,
        side: Side,
        rules: SymbolRules,
        parameters: MakerPriceParameters,
    ) -> PriceQuote:
        if order_book.instrument != rules.instrument:
            raise ValueError("order book and symbol rules must match")
        self._validate_book(order_book)

        bids = self._depth(order_book.bids, parameters.depth_levels)
        asks = self._depth(order_book.asks, parameters.depth_levels)
        obi = self.order_book_imbalance(bids, asks)
        obiv = self.order_book_value_imbalance(bids, asks)
        combined = (obi + obiv) / Decimal("2")

        pressure_favors_order = (
            side is Side.BUY and combined >= parameters.imbalance_threshold
        ) or (
            side is Side.SELL and combined <= -parameters.imbalance_threshold
        )
        applied_ticks = parameters.improve_ticks
        if pressure_favors_order:
            applied_ticks += parameters.pressure_ticks

        tick_move = rules.price_increment * applied_ticks
        if side is Side.BUY:
            desired = order_book.best_bid.price + tick_move
        else:
            desired = order_book.best_ask.price - tick_move

        return PriceQuote(
            desired_price=desired,
            order_book_imbalance=obi,
            order_book_value_imbalance=obiv,
            combined_imbalance=combined,
            applied_ticks=applied_ticks,
        )

    @staticmethod
    def order_book_imbalance(
        bids: Sequence[OrderBookLevel], asks: Sequence[OrderBookLevel]
    ) -> Decimal:
        bid_quantity = sum((level.quantity for level in bids), ZERO)
        ask_quantity = sum((level.quantity for level in asks), ZERO)
        total = bid_quantity + ask_quantity
        return ZERO if total == ZERO else (bid_quantity - ask_quantity) / total

    @staticmethod
    def order_book_value_imbalance(
        bids: Sequence[OrderBookLevel], asks: Sequence[OrderBookLevel]
    ) -> Decimal:
        bid_value = sum((level.price * level.quantity for level in bids), ZERO)
        ask_value = sum((level.price * level.quantity for level in asks), ZERO)
        total = bid_value + ask_value
        return ZERO if total == ZERO else (bid_value - ask_value) / total

    @staticmethod
    def _depth(
        levels: Sequence[OrderBookLevel], depth_levels: int | None
    ) -> Sequence[OrderBookLevel]:
        return levels if depth_levels is None else levels[:depth_levels]

    @staticmethod
    def _validate_book(order_book: OrderBookSnapshot) -> None:
        if not order_book.bids or not order_book.asks:
            raise InvalidOrderBook("both bid and ask levels are required")
        if order_book.best_bid.price >= order_book.best_ask.price:
            raise InvalidOrderBook("order book is crossed or locked")
