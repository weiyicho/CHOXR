"""Capture Binance rate-limit response headers for runtime policy decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True, slots=True)
class RateLimitSnapshot:
    used_weights: dict[str, int] = field(default_factory=dict)
    order_counts: dict[str, int] = field(default_factory=dict)
    retry_after_seconds: float | None = None


def parse_rate_limit_headers(headers: Mapping[str, str]) -> RateLimitSnapshot:
    normalized = {str(key).lower(): str(value) for key, value in headers.items()}
    used_weights: dict[str, int] = {}
    order_counts: dict[str, int] = {}
    for name, value in normalized.items():
        try:
            parsed = int(value)
        except ValueError:
            continue
        if name.startswith("x-mbx-used-weight"):
            used_weights[name] = parsed
        elif name.startswith("x-mbx-order-count"):
            order_counts[name] = parsed

    retry_after: float | None = None
    if "retry-after" in normalized:
        try:
            retry_after = float(normalized["retry-after"])
        except ValueError:
            retry_after = None

    return RateLimitSnapshot(used_weights, order_counts, retry_after)


class RateLimitState:
    def __init__(self) -> None:
        self._last = RateLimitSnapshot()

    @property
    def last(self) -> RateLimitSnapshot:
        return self._last

    def observe(self, headers: Mapping[str, str]) -> RateLimitSnapshot:
        self._last = parse_rate_limit_headers(headers)
        return self._last
