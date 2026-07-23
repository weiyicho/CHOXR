"""HMAC SHA-256 signing for Binance SIGNED endpoints."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping
from urllib.parse import urlencode


def parameter_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return value.value
    return value


def clean_parameters(params: Mapping[str, object] | None) -> dict[str, object]:
    return {
        key: parameter_value(value)
        for key, value in (params or {}).items()
        if value is not None
    }


@dataclass(frozen=True, slots=True)
class SignedParameters:
    query_string: str
    parameters: dict[str, object]


class HmacSigner:
    def __init__(self, secret_key: str):
        self._secret_key = secret_key.encode("utf-8")

    def sign(self, params: Mapping[str, object]) -> SignedParameters:
        cleaned = clean_parameters(params)
        query = urlencode(cleaned)
        signature = hmac.new(
            self._secret_key,
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return SignedParameters(
            query_string=query,
            parameters={**cleaned, "signature": signature},
        )
