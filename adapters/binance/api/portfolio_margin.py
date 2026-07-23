"""Documented Classic Portfolio Margin REST operations required by CHOXR."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from ..transport.rest_client import BinanceRestClient


DecimalLike = Decimal | str | int
_UM_CLIENT_ORDER_ID = re.compile(r"^[.A-Z:/a-z0-9_-]{1,32}$")
_MARGIN_CLIENT_ORDER_ID = re.compile(r"^[.A-Z:/a-z0-9_-]{1,36}$")


def _decimal_string(value: DecimalLike) -> str:
    parsed = Decimal(str(value))
    if parsed <= 0:
        raise ValueError("quantity and price values must be positive")
    return format(parsed, "f")


def _order_reference(
    order_id: int | None,
    client_order_id: str | None,
) -> dict[str, object]:
    if (order_id is None) == (client_order_id is None):
        raise ValueError("exactly one of order_id or client_order_id is required")
    if order_id is not None:
        return {"orderId": order_id}
    if not client_order_id:
        raise ValueError("client_order_id cannot be blank")
    return {"origClientOrderId": client_order_id}


def _validate_limit(
    order_type: str,
    price: DecimalLike | None,
    time_in_force: str | None,
) -> tuple[str | None, str | None]:
    normalized_type = order_type.upper()
    if normalized_type == "LIMIT":
        if price is None or time_in_force is None:
            raise ValueError("LIMIT order requires price and time_in_force")
        return _decimal_string(price), time_in_force.upper()
    if price is not None or time_in_force is not None:
        raise ValueError("price/time_in_force are only supported here for LIMIT orders")
    return None, None


class PortfolioMarginApi:
    """Raw PAPI functions; payloads stay native until parser/gateway boundary."""

    def __init__(self, client: BinanceRestClient):
        self._client = client

    # Margin asset leg -------------------------------------------------
    def place_margin_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: DecimalLike,
        client_order_id: str,
        price: DecimalLike | None = None,
        time_in_force: str | None = None,
        side_effect_type: str = "NO_SIDE_EFFECT",
        new_order_response_type: str = "FULL",
    ) -> dict[str, Any]:
        if not _MARGIN_CLIENT_ORDER_ID.fullmatch(client_order_id):
            raise ValueError("invalid Margin newClientOrderId")
        price_value, tif_value = _validate_limit(order_type, price, time_in_force)
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": _decimal_string(quantity),
            "price": price_value,
            "timeInForce": tif_value,
            "sideEffectType": side_effect_type,
            "newClientOrderId": client_order_id,
            "newOrderRespType": new_order_response_type,
        }
        return self._client.request(
            "POST",
            "/papi/v1/margin/order",
            params,
            signed=True,
            side_effect=True,
            client_order_id=client_order_id,
        )

    def query_margin_order(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"symbol": symbol, **_order_reference(order_id, client_order_id)}
        return self._client.request(
            "GET", "/papi/v1/margin/order", params, signed=True, side_effect=False
        )

    def cancel_margin_order(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        client_order_id: str | None = None,
        cancel_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "symbol": symbol,
            **_order_reference(order_id, client_order_id),
            "newClientOrderId": cancel_client_order_id,
        }
        return self._client.request(
            "DELETE",
            "/papi/v1/margin/order",
            params,
            signed=True,
            side_effect=True,
            client_order_id=client_order_id,
        )

    def list_margin_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return self._client.request(
            "GET",
            "/papi/v1/margin/openOrders",
            {"symbol": symbol},
            signed=True,
            side_effect=False,
        )

    def list_margin_fills(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        from_id: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._client.request(
            "GET",
            "/papi/v1/margin/myTrades",
            {
                "symbol": symbol,
                "orderId": order_id,
                "startTime": start_time,
                "endTime": end_time,
                "fromId": from_id,
                "limit": limit,
            },
            signed=True,
            side_effect=False,
        )

    # USD-M perpetual leg ---------------------------------------------
    def place_um_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str,
        quantity: DecimalLike,
        client_order_id: str,
        price: DecimalLike | None = None,
        time_in_force: str | None = None,
        reduce_only: bool = False,
        position_side: str = "BOTH",
        new_order_response_type: str = "RESULT",
    ) -> dict[str, Any]:
        if not _UM_CLIENT_ORDER_ID.fullmatch(client_order_id):
            raise ValueError("invalid UM newClientOrderId")
        price_value, tif_value = _validate_limit(order_type, price, time_in_force)
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "positionSide": position_side,
            "timeInForce": tif_value,
            "quantity": _decimal_string(quantity),
            "reduceOnly": reduce_only,
            "price": price_value,
            "newClientOrderId": client_order_id,
            "newOrderRespType": new_order_response_type,
        }
        return self._client.request(
            "POST",
            "/papi/v1/um/order",
            params,
            signed=True,
            side_effect=True,
            client_order_id=client_order_id,
        )

    def query_um_order(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"symbol": symbol, **_order_reference(order_id, client_order_id)}
        return self._client.request(
            "GET", "/papi/v1/um/order", params, signed=True, side_effect=False
        )

    def cancel_um_order(
        self,
        symbol: str,
        *,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"symbol": symbol, **_order_reference(order_id, client_order_id)}
        return self._client.request(
            "DELETE",
            "/papi/v1/um/order",
            params,
            signed=True,
            side_effect=True,
            client_order_id=client_order_id,
        )

    def list_um_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return self._client.request(
            "GET",
            "/papi/v1/um/openOrders",
            {"symbol": symbol},
            signed=True,
            side_effect=False,
        )

    def list_um_fills(
        self,
        symbol: str,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
        from_id: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._client.request(
            "GET",
            "/papi/v1/um/userTrades",
            {
                "symbol": symbol,
                "startTime": start_time,
                "endTime": end_time,
                "fromId": from_id,
                "limit": limit,
            },
            signed=True,
            side_effect=False,
        )

    # Account truth ----------------------------------------------------
    def get_account(self) -> dict[str, Any]:
        return self._client.request(
            "GET", "/papi/v1/account", signed=True, side_effect=False
        )

    def get_balances(self, asset: str | None = None) -> list[dict[str, Any]]:
        payload = self._client.request(
            "GET",
            "/papi/v1/balance",
            {"asset": asset},
            signed=True,
            side_effect=False,
        )
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return [payload]
        raise TypeError("unexpected /papi/v1/balance response shape")

    def get_um_positions(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return self._client.request(
            "GET",
            "/papi/v1/um/positionRisk",
            {"symbol": symbol},
            signed=True,
            side_effect=False,
        )

    def get_um_account(self) -> dict[str, Any]:
        return self._client.request(
            "GET", "/papi/v1/um/account", signed=True, side_effect=False
        )

    def get_um_account_config(self) -> dict[str, Any]:
        return self._client.request(
            "GET", "/papi/v1/um/accountConfig", signed=True, side_effect=False
        )

    def get_um_symbol_config(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return self._client.request(
            "GET",
            "/papi/v1/um/symbolConfig",
            {"symbol": symbol},
            signed=True,
            side_effect=False,
        )

    def get_um_position_mode(self) -> dict[str, Any]:
        return self._client.request(
            "GET",
            "/papi/v1/um/positionSide/dual",
            signed=True,
            side_effect=False,
        )

    def list_um_income(
        self,
        *,
        symbol: str | None = None,
        income_type: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._client.request(
            "GET",
            "/papi/v1/um/income",
            {
                "symbol": symbol,
                "incomeType": income_type,
                "startTime": start_time,
                "endTime": end_time,
                "page": page,
                "limit": limit,
            },
            signed=True,
            side_effect=False,
        )

    def list_funding_income(
        self,
        *,
        symbol: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.list_um_income(
            symbol=symbol,
            income_type="FUNDING_FEE",
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def collect_futures_funds(self) -> dict[str, Any]:
        """Manual recovery command; normal runtime may use UI auto aggregation."""

        return self._client.request(
            "POST",
            "/papi/v1/auto-collection",
            signed=True,
            side_effect=True,
        )
