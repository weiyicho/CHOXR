"""Public USD-M Futures market-data API used for perpetual price planning."""

from __future__ import annotations

from typing import Any

from ..transport.rest_client import BinanceRestClient


class UsdMApi:
    def __init__(self, client: BinanceRestClient):
        self._client = client

    def get_server_time(self) -> int:
        data = self._client.request("GET", "/fapi/v1/time", side_effect=False)
        return int(data["serverTime"])

    def get_exchange_info(self) -> dict[str, Any]:
        return self._client.request(
            "GET", "/fapi/v1/exchangeInfo", side_effect=False
        )

    def get_order_book(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        if not symbol:
            raise ValueError("symbol is required")
        if limit not in {5, 10, 20, 50, 100, 500, 1_000}:
            raise ValueError("unsupported USD-M depth limit")
        return self._client.request(
            "GET",
            "/fapi/v1/depth",
            {"symbol": symbol, "limit": limit},
            side_effect=False,
        )

    def get_premium_index(
        self,
        symbol: str | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Return current mark price, index price and predicted funding data."""

        params = {"symbol": symbol} if symbol else None
        return self._client.request(
            "GET",
            "/fapi/v1/premiumIndex",
            params,
            side_effect=False,
        )

    def get_funding_rate_info(self) -> list[dict[str, Any]]:
        """Return symbols whose funding interval or caps differ from defaults."""

        return self._client.request(
            "GET",
            "/fapi/v1/fundingInfo",
            side_effect=False,
        )

    def get_24h_tickers(
        self,
        symbol: str | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Return USD-M 24-hour rolling ticker statistics."""

        params = {"symbol": symbol} if symbol else None
        return self._client.request(
            "GET",
            "/fapi/v1/ticker/24hr",
            params,
            side_effect=False,
        )
