"""Public Spot market-data API used for the asset leg's price planning."""

from __future__ import annotations

from typing import Any

from ..transport.rest_client import BinanceRestClient


class SpotApi:
    def __init__(self, client: BinanceRestClient):
        self._client = client

    def get_server_time(self) -> int:
        data = self._client.request("GET", "/api/v3/time", side_effect=False)
        return int(data["serverTime"])

    def get_exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"symbol": symbol} if symbol else None
        return self._client.request(
            "GET", "/api/v3/exchangeInfo", params, side_effect=False
        )

    def get_order_book(self, symbol: str, limit: int = 100) -> dict[str, Any]:
        if not symbol:
            raise ValueError("symbol is required")
        if not 1 <= limit <= 5_000:
            raise ValueError("Spot depth limit must be between 1 and 5000")
        return self._client.request(
            "GET",
            "/api/v3/depth",
            {"symbol": symbol, "limit": limit},
            side_effect=False,
        )
