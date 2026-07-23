"""Classic Portfolio Margin user-data listen-key lifecycle."""

from __future__ import annotations

from ..transport.rest_client import BinanceRestClient


class PortfolioMarginUserStreamApi:
    def __init__(self, client: BinanceRestClient):
        self._client = client

    def start(self) -> str:
        data = self._client.request(
            "POST",
            "/papi/v1/listenKey",
            api_key=True,
            side_effect=False,
        )
        return str(data["listenKey"])

    def keepalive(self) -> None:
        self._client.request(
            "PUT",
            "/papi/v1/listenKey",
            api_key=True,
            side_effect=False,
        )

    def close(self) -> None:
        self._client.request(
            "DELETE",
            "/papi/v1/listenKey",
            api_key=True,
            side_effect=False,
        )
