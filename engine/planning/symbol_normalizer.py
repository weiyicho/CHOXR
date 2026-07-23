"""Decimal-safe exchange-filter normalization."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from engine.domain.instrument import OrderBookSnapshot, SymbolRules
from engine.domain.order import Side


class SymbolNormalizationError(ValueError):
    pass


class SymbolNormalizer:
    @staticmethod
    def ensure_trading_enabled(rules: SymbolRules) -> None:
        if not rules.trading_enabled:
            raise SymbolNormalizationError(
                f"trading is disabled for {rules.instrument.symbol}"
            )

    @staticmethod
    def floor_to_increment(value: Decimal, increment: Decimal) -> Decimal:
        SymbolNormalizer._require_positive_increment(increment)
        return (value / increment).to_integral_value(rounding=ROUND_FLOOR) * increment

    @staticmethod
    def ceil_to_increment(value: Decimal, increment: Decimal) -> Decimal:
        SymbolNormalizer._require_positive_increment(increment)
        return (
            value / increment
        ).to_integral_value(rounding=ROUND_CEILING) * increment

    def normalize_maker_price(
        self,
        desired_price: Decimal,
        side: Side,
        order_book: OrderBookSnapshot,
        rules: SymbolRules,
    ) -> Decimal:
        self.ensure_trading_enabled(rules)
        if desired_price <= 0:
            raise SymbolNormalizationError("desired price must be positive")
        if order_book.instrument != rules.instrument:
            raise SymbolNormalizationError("order book and symbol rules must match")
        if order_book.best_bid is None or order_book.best_ask is None:
            raise SymbolNormalizationError(
                "both bid and ask levels are required for maker pricing"
            )

        tick = rules.price_increment
        if side is Side.BUY:
            rounded = self.floor_to_increment(desired_price, tick)
            highest_maker_price = self.floor_to_increment(
                order_book.best_ask.price - tick, tick
            )
            normalized = min(rounded, highest_maker_price)
            if normalized <= 0 or normalized >= order_book.best_ask.price:
                raise SymbolNormalizationError("no valid post-only BUY price")
        else:
            rounded = self.ceil_to_increment(desired_price, tick)
            lowest_maker_price = self.ceil_to_increment(
                order_book.best_bid.price + tick, tick
            )
            normalized = max(rounded, lowest_maker_price)
            if normalized <= order_book.best_bid.price:
                raise SymbolNormalizationError("no valid post-only SELL price")

        return normalized

    def normalize_quantity(self, raw_quantity: Decimal, rules: SymbolRules) -> Decimal:
        self.ensure_trading_enabled(rules)
        return self._normalize_quantity(
            raw_quantity,
            increment=rules.quantity_increment,
            minimum=rules.min_quantity,
            maximum=rules.max_quantity,
            minimum_name="min_quantity",
        )

    def normalize_market_quantity(
        self, raw_quantity: Decimal, rules: SymbolRules
    ) -> Decimal:
        self.ensure_trading_enabled(rules)
        return self._normalize_quantity(
            raw_quantity,
            increment=rules.effective_market_quantity_increment,
            minimum=rules.effective_market_min_quantity,
            maximum=rules.effective_market_max_quantity,
            minimum_name=(
                "market_min_quantity"
                if rules.market_min_quantity is not None
                else "min_quantity"
            ),
        )

    def _normalize_quantity(
        self,
        raw_quantity: Decimal,
        *,
        increment: Decimal,
        minimum: Decimal,
        maximum: Decimal | None,
        minimum_name: str,
    ) -> Decimal:
        if raw_quantity <= 0:
            raise SymbolNormalizationError("quantity must be positive")

        capped = raw_quantity
        if maximum is not None:
            capped = min(capped, maximum)
        normalized = self.floor_to_increment(capped, increment)

        if normalized <= 0 or normalized < minimum:
            raise SymbolNormalizationError(
                f"quantity {normalized} is below {minimum_name} {minimum}"
            )
        return normalized

    @staticmethod
    def validate_notional(
        price: Decimal, quantity: Decimal, rules: SymbolRules
    ) -> Decimal:
        notional = price * quantity
        if notional < rules.min_notional:
            raise SymbolNormalizationError(
                f"notional {notional} is below min_notional {rules.min_notional}"
            )
        if rules.max_notional is not None and notional > rules.max_notional:
            raise SymbolNormalizationError(
                f"notional {notional} exceeds max_notional {rules.max_notional}"
            )
        return notional

    @staticmethod
    def _require_positive_increment(increment: Decimal) -> None:
        if increment <= 0:
            raise SymbolNormalizationError("increment must be positive")
