"""Typed failure categories used by execution recovery."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ErrorContext:
    method: str
    path: str
    status_code: int | None = None
    code: int | None = None
    message: str = ""
    retry_after_seconds: float | None = None
    client_order_id: str | None = None


class BinanceError(RuntimeError):
    def __init__(self, context: ErrorContext):
        self.context = context
        details = context.message or "Binance request failed"
        if context.code is not None:
            details = f"[{context.code}] {details}"
        super().__init__(f"{context.method} {context.path}: {details}")


class BinanceRequestError(BinanceError):
    pass


class BinanceAuthenticationError(BinanceError):
    pass


class BinanceRateLimitError(BinanceError):
    pass


class BinanceIpBanError(BinanceRateLimitError):
    pass


class BinanceServerError(BinanceError):
    """A definite server-side failure that an upper layer may retry safely."""

    retryable = True


class BinanceNetworkError(BinanceError):
    pass


class UnknownExecutionOutcome(BinanceError):
    """A side-effect request may have reached Binance's matching engine."""


_UNKNOWN_503_MESSAGE = "unknown error, please check your request or try again later"


def _is_unknown_503(context: ErrorContext) -> bool:
    return (
        context.status_code == 503
        and _UNKNOWN_503_MESSAGE in context.message.lower()
    )


def error_for_response(context: ErrorContext, *, side_effect: bool) -> BinanceError:
    if context.code in {-1006, -1007}:
        return (
            UnknownExecutionOutcome(context)
            if side_effect
            else BinanceServerError(context)
        )
    if context.status_code == 418:
        return BinanceIpBanError(context)
    if context.status_code == 429:
        return BinanceRateLimitError(context)
    if context.status_code in {401, 403} or context.code in {-2014, -2015}:
        return BinanceAuthenticationError(context)
    if context.status_code is not None and context.status_code >= 500:
        if side_effect and _is_unknown_503(context):
            return UnknownExecutionOutcome(context)
        return BinanceServerError(context)
    return BinanceRequestError(context)
