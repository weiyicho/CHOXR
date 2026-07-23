"""Pure, fail-closed pre-trade risk evaluation."""

from __future__ import annotations

from decimal import Decimal

from engine.domain.order import OrderIntent

from .account_limits import available_quote_capital
from .models import RiskContext, RiskDecision, RiskLimits, RiskViolation, ZERO


class PreTradeRiskCheck:
    def evaluate(
        self, intent: OrderIntent, context: RiskContext, limits: RiskLimits
    ) -> RiskDecision:
        violations: list[RiskViolation] = []
        price = intent.price if intent.price is not None else context.reference_price
        if price is None or price <= ZERO:
            violations.append(
                RiskViolation(
                    "MISSING_REFERENCE_PRICE",
                    "a positive price is required to evaluate order notional",
                )
            )
            order_notional = ZERO
        else:
            order_notional = price * intent.quantity

        if intent.instrument.venue != context.account.venue:
            violations.append(
                RiskViolation(
                    "ACCOUNT_VENUE_MISMATCH",
                    "order venue does not match account venue",
                )
            )
        if limits.allowed_venues and intent.instrument.venue not in limits.allowed_venues:
            violations.append(
                RiskViolation("VENUE_NOT_ALLOWED", "order venue is not allowed")
            )
        if limits.allowed_markets and intent.instrument.market not in limits.allowed_markets:
            violations.append(
                RiskViolation("MARKET_NOT_ALLOWED", "order market is not allowed")
            )

        exposure_change = order_notional if context.increases_exposure else -order_notional
        projected_gross = max(ZERO, context.current_gross_notional + exposure_change)
        projected_instrument = max(
            ZERO, context.current_instrument_notional + exposure_change
        )

        if (
            limits.max_order_notional is not None
            and order_notional > limits.max_order_notional
        ):
            violations.append(
                RiskViolation(
                    "MAX_ORDER_NOTIONAL",
                    f"order notional {order_notional} exceeds limit {limits.max_order_notional}",
                )
            )
        if (
            limits.max_gross_notional is not None
            and projected_gross > limits.max_gross_notional
        ):
            violations.append(
                RiskViolation(
                    "MAX_GROSS_NOTIONAL",
                    f"projected gross {projected_gross} exceeds limit {limits.max_gross_notional}",
                )
            )
        if (
            limits.max_instrument_notional is not None
            and projected_instrument > limits.max_instrument_notional
        ):
            violations.append(
                RiskViolation(
                    "MAX_INSTRUMENT_NOTIONAL",
                    "projected instrument exposure exceeds its limit",
                )
            )

        account_available = available_quote_capital(
            context.account, context.quote_asset
        )
        available = (
            context.available_capital
            if context.available_capital is not None
            else account_available
        )
        if context.increases_exposure:
            required = (
                context.required_capital
                if context.required_capital is not None
                else order_notional
            )
        else:
            required = ZERO

        fraction_cap = available * limits.max_available_capital_fraction
        if required > fraction_cap:
            violations.append(
                RiskViolation(
                    "AVAILABLE_CAPITAL_FRACTION",
                    f"required capital {required} exceeds allowed capital {fraction_cap}",
                )
            )
        if available - required < limits.min_remaining_available_capital:
            violations.append(
                RiskViolation(
                    "MIN_REMAINING_CAPITAL",
                    "order would use protected available capital",
                )
            )

        return RiskDecision(
            approved=not violations,
            order_notional=order_notional,
            required_capital=required,
            available_capital=available,
            projected_gross_notional=projected_gross,
            projected_instrument_notional=projected_instrument,
            violations=tuple(violations),
        )

    def require_approved(
        self, intent: OrderIntent, context: RiskContext, limits: RiskLimits
    ) -> RiskDecision:
        decision = self.evaluate(intent, context, limits)
        if not decision.approved:
            codes = ", ".join(decision.violation_codes)
            raise PreTradeRiskRejected(f"pre-trade risk rejected order: {codes}")
        return decision


class PreTradeRiskRejected(RuntimeError):
    pass
