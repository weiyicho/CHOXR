"""Small synchronous REST transport with explicit side-effect semantics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import requests

from ..config import BinanceConfig
from .auth import HmacSigner, clean_parameters
from .clock import ServerClock
from .errors import (
    BinanceNetworkError,
    ErrorContext,
    UnknownExecutionOutcome,
    error_for_response,
)
from .rate_limit import RateLimitSnapshot, RateLimitState


class BinanceRestClient:
    """Transport used by one Binance REST base URL.

    A write request is attempted exactly once.  The only transport-level replay
    is a single ``-1021`` retry after clock synchronization; Binance rejects an
    invalid timestamp before applying the requested operation.
    """

    def __init__(
        self,
        base_url: str,
        config: BinanceConfig,
        *,
        session: Any | None = None,
        clock: ServerClock | None = None,
        rate_limits: RateLimitState | None = None,
        clock_sync: Callable[[], object] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._config = config
        self._session = session or requests.Session()
        self.clock = clock or ServerClock()
        self.rate_limits = rate_limits or RateLimitState()
        self._clock_sync = clock_sync
        self._signer = HmacSigner(config.api_secret)

    @property
    def last_rate_limit(self) -> RateLimitSnapshot:
        return self.rate_limits.last

    def set_clock_sync(self, clock_sync: Callable[[], object]) -> None:
        self._clock_sync = clock_sync

    def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, object] | None = None,
        *,
        signed: bool = False,
        api_key: bool = False,
        side_effect: bool | None = None,
        client_order_id: str | None = None,
    ) -> Any:
        method = method.upper()
        if not path.startswith("/"):
            raise ValueError("Binance API path must start with '/'")
        is_side_effect = method in {"POST", "PUT", "DELETE"} if side_effect is None else side_effect

        response, data = self._request_once(
            method,
            path,
            params,
            signed=signed,
            api_key=api_key,
            side_effect=is_side_effect,
            client_order_id=client_order_id,
        )
        context = self._error_context(
            method,
            path,
            response.status_code,
            data,
            client_order_id,
        )
        if context is not None and context.code == -1021 and signed and self._clock_sync:
            self._clock_sync()
            response, data = self._request_once(
                method,
                path,
                params,
                signed=signed,
                api_key=api_key,
                side_effect=is_side_effect,
                client_order_id=client_order_id,
            )
            context = self._error_context(
                method,
                path,
                response.status_code,
                data,
                client_order_id,
            )

        if context is not None:
            raise error_for_response(context, side_effect=is_side_effect)
        return data

    def _request_once(
        self,
        method: str,
        path: str,
        params: Mapping[str, object] | None,
        *,
        signed: bool,
        api_key: bool,
        side_effect: bool,
        client_order_id: str | None,
    ) -> tuple[Any, Any]:
        request_params = clean_parameters(params)
        if signed:
            request_params["timestamp"] = self.clock.now_ms()
            request_params.setdefault("recvWindow", self._config.recv_window_ms)
            request_params = self._signer.sign(request_params).parameters

        headers: dict[str, str] = {}
        if signed or api_key:
            headers["X-MBX-APIKEY"] = self._config.api_key

        try:
            response = self._session.request(
                method,
                f"{self.base_url}{path}",
                params=request_params,
                headers=headers,
                timeout=self._config.timeout_seconds,
            )
        except requests.RequestException as exc:
            context = ErrorContext(
                method=method,
                path=path,
                message=str(exc) or exc.__class__.__name__,
                client_order_id=client_order_id,
            )
            if side_effect:
                raise UnknownExecutionOutcome(context) from exc
            raise BinanceNetworkError(context) from exc

        self.rate_limits.observe(response.headers)
        try:
            data = response.json()
        except ValueError as exc:
            context = ErrorContext(
                method=method,
                path=path,
                status_code=response.status_code,
                message=getattr(response, "text", "non-JSON response"),
                retry_after_seconds=self.last_rate_limit.retry_after_seconds,
                client_order_id=client_order_id,
            )
            raise error_for_response(context, side_effect=side_effect) from exc
        return response, data

    def _error_context(
        self,
        method: str,
        path: str,
        status_code: int,
        data: Any,
        client_order_id: str | None,
    ) -> ErrorContext | None:
        code: int | None = None
        message = ""
        if isinstance(data, dict):
            raw_code = data.get("code")
            if isinstance(raw_code, int):
                code = raw_code
            message = str(data.get("msg", ""))

        is_error_code = code is not None and code < 0
        if status_code < 400 and not is_error_code:
            return None
        return ErrorContext(
            method=method,
            path=path,
            status_code=status_code,
            code=code,
            message=message,
            retry_after_seconds=self.last_rate_limit.retry_after_seconds,
            client_order_id=client_order_id,
        )
