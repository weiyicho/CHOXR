"""Order-book-aware maker pricing without exchange-specific assumptions."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Sequence

from engine.domain.instrument import OrderBookLevel, OrderBookSnapshot, SymbolRules
from engine.domain.order import Side

from .models import MakerPriceParameters, PriceQuote, ZERO


class InvalidOrderBook(ValueError):
    pass


class MakerPricePolicy:
    """Propose a maker price using only exchange-neutral book mathematics.

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
        obi = self.order_book_imbalance(
            bids,
            asks,
            depth_decay=parameters.depth_decay,
        )
        obiv = self.order_book_value_imbalance(
            bids,
            asks,
            depth_decay=parameters.depth_decay,
        )
        combined = self.combine_imbalances(
            obi,
            obiv,
            quantity_weight=parameters.quantity_imbalance_weight,
            value_weight=parameters.value_imbalance_weight,
        )
        directional_pressure = combined if side is Side.BUY else -combined
        pressure_ratio = self.pressure_ratio(
            directional_pressure,
            parameters.imbalance_threshold,
        )
        pressure_ticks = self.scale_pressure_ticks(
            parameters.pressure_ticks,
            pressure_ratio,
        )
        requested_ticks = parameters.improve_ticks + pressure_ticks
        microprice = self.microprice(order_book)
        available_ticks = self.available_improve_ticks(order_book, rules)
        fair_value_ticks = self.fair_value_improve_ticks(
            order_book,
            side,
            rules.price_increment,
            microprice,
        )
        applied_ticks = min(
            requested_ticks,
            available_ticks,
            fair_value_ticks,
        )

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
            directional_pressure=directional_pressure,
            pressure_ratio=pressure_ratio,
            available_improve_ticks=available_ticks,
            applied_ticks=applied_ticks,
            microprice=microprice,
            fair_value_improve_ticks=fair_value_ticks,
        )

    @staticmethod
    def microprice(order_book: OrderBookSnapshot) -> Decimal:
        """Estimate near-term fair value from the best bid/ask queues."""
        MakerPricePolicy._validate_book(order_book)
        best_bid = order_book.best_bid
        best_ask = order_book.best_ask
        total_quantity = best_bid.quantity + best_ask.quantity
        if total_quantity == ZERO:
            return (best_bid.price + best_ask.price) / Decimal("2")
        return (
            best_ask.price * best_bid.quantity
            + best_bid.price * best_ask.quantity
        ) / total_quantity

    @staticmethod
    def order_book_imbalance(
        bids: Sequence[OrderBookLevel],
        asks: Sequence[OrderBookLevel],
        *,
        depth_decay: Decimal = Decimal("1"),
    ) -> Decimal:
        MakerPricePolicy._validate_depth_decay(depth_decay)
        bid_quantity = MakerPricePolicy._weighted_sum(
            bids,
            depth_decay,
            use_notional=False,
        )
        ask_quantity = MakerPricePolicy._weighted_sum(
            asks,
            depth_decay,
            use_notional=False,
        )
        total = bid_quantity + ask_quantity
        return ZERO if total == ZERO else (bid_quantity - ask_quantity) / total

    @staticmethod
    def order_book_value_imbalance(
        bids: Sequence[OrderBookLevel],
        asks: Sequence[OrderBookLevel],
        *,
        depth_decay: Decimal = Decimal("1"),
    ) -> Decimal:
        MakerPricePolicy._validate_depth_decay(depth_decay)
        bid_value = MakerPricePolicy._weighted_sum(
            bids,
            depth_decay,
            use_notional=True,
        )
        ask_value = MakerPricePolicy._weighted_sum(
            asks,
            depth_decay,
            use_notional=True,
        )
        total = bid_value + ask_value
        return ZERO if total == ZERO else (bid_value - ask_value) / total

    @staticmethod
    def combine_imbalances(
        quantity_imbalance: Decimal,
        value_imbalance: Decimal,
        *,
        quantity_weight: Decimal,
        value_weight: Decimal,
    ) -> Decimal:
        if quantity_weight < ZERO or value_weight < ZERO:
            raise ValueError("imbalance weights cannot be negative")
        total_weight = quantity_weight + value_weight
        if total_weight == ZERO:
            raise ValueError("at least one imbalance weight must be positive")
        return (
            quantity_imbalance * quantity_weight
            + value_imbalance * value_weight
        ) / total_weight

    @staticmethod
    def pressure_ratio(
        directional_pressure: Decimal,
        threshold: Decimal,
    ) -> Decimal:
        """Map pressure beyond a deadband onto the closed interval [0, 1]."""
        if not ZERO <= threshold <= Decimal("1"):
            raise ValueError("threshold must be in [0, 1]")
        if directional_pressure <= threshold or threshold == Decimal("1"):
            return ZERO
        return min(
            Decimal("1"),
            (directional_pressure - threshold) / (Decimal("1") - threshold),
        )

    @staticmethod
    def scale_pressure_ticks(maximum_ticks: int, pressure_ratio: Decimal) -> int:
        """Convert continuous pressure to discrete ticks without understating it."""
        if maximum_ticks < 0:
            raise ValueError("maximum_ticks cannot be negative")
        if not ZERO <= pressure_ratio <= Decimal("1"):
            raise ValueError("pressure_ratio must be in [0, 1]")
        if maximum_ticks == 0 or pressure_ratio == ZERO:
            return 0
        scaled = Decimal(maximum_ticks) * pressure_ratio
        return int(scaled.to_integral_value(rounding=ROUND_CEILING))

    @staticmethod
    def available_improve_ticks(
        order_book: OrderBookSnapshot,
        rules: SymbolRules,
    ) -> int:
        """Return the ticks available inside the spread without crossing it."""
        spread = order_book.best_ask.price - order_book.best_bid.price
        spread_ticks = (spread / rules.price_increment).to_integral_value(
            rounding=ROUND_CEILING
        )
        return max(0, int(spread_ticks) - 1)

    @staticmethod
    def fair_value_improve_ticks(
        order_book: OrderBookSnapshot,
        side: Side,
        tick_size: Decimal,
        fair_value: Decimal,
    ) -> int:
        """Return full ticks available before a quote passes fair value."""
        if tick_size <= ZERO:
            raise ValueError("tick_size must be positive")
        distance = (
            fair_value - order_book.best_bid.price
            if side is Side.BUY
            else order_book.best_ask.price - fair_value
        )
        if distance <= ZERO:
            return 0
        ticks = (distance / tick_size).to_integral_value(rounding=ROUND_FLOOR)
        return max(0, int(ticks))

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

    @staticmethod
    def _weighted_sum(
        levels: Sequence[OrderBookLevel],
        depth_decay: Decimal,
        *,
        use_notional: bool,
    ) -> Decimal:
        return sum(
            (
                (depth_decay ** index)
                * level.quantity
                * (level.price if use_notional else Decimal("1"))
                for index, level in enumerate(levels)
            ),
            ZERO,
        )

    @staticmethod
    def _validate_depth_decay(depth_decay: Decimal) -> None:
        if not ZERO < depth_decay <= Decimal("1"):
            raise ValueError("depth_decay must be in (0, 1]")
