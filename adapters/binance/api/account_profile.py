"""Read-only account-type discriminator shared by PM and PM Pro."""

from __future__ import annotations

from typing import Any

from ..transport.rest_client import BinanceRestClient


class PortfolioAccountProfileApi:
    """Fetch ``accountType`` from Binance's documented SAPI profile resource."""

    def __init__(self, client: BinanceRestClient):
        self._client = client

    def get_account_profile(self) -> dict[str, Any]:
        return self._client.request(
            "GET",
            "/sapi/v1/portfolio/account",
            signed=True,
            side_effect=False,
        )
