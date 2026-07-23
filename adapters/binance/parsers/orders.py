from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import FillSnapshot, OrderSnapshot, ZERO


def _decimal(payload: dict[str, Any], *keys: str, default: str = "0") -> Decimal:
    for key in keys:
        if key in payload and payload[key] not in {None, ""}:
            return Decimal(str(payload[key]))
    return Decimal(default)


def _average_price(
    payload: dict[str, Any], executed: Decimal, cumulative_quote: Decimal
) -> Decimal | None:
    explicit = _decimal(payload, "avgPrice")
    if explicit > ZERO:
        return explicit
    if executed > ZERO and cumulative_quote > ZERO:
        return cumulative_quote / executed
    return None


def _parse_order(payload: dict[str, Any], market: str) -> OrderSnapshot:
    original = _decimal(payload, "origQty", "origQuantity")
    executed = _decimal(payload, "executedQty", "executedQuantity", "cumQty")
    cumulative_quote = _decimal(
        payload,
        "cummulativeQuoteQty",
        "cumQuote",
        "cumQuoteQty",
    )
    return OrderSnapshot(
        market=market,
        symbol=str(payload["symbol"]),
        exchange_order_id=int(payload["orderId"]),
        client_order_id=str(payload.get("clientOrderId", "")),
        status=str(payload.get("status", "UNKNOWN")),
        side=str(payload.get("side", "")),
        order_type=str(payload.get("type", payload.get("origType", ""))),
        original_quantity=original,
        executed_quantity=executed,
        cumulative_quote_quantity=cumulative_quote,
        price=_decimal(payload, "price"),
        average_price=_average_price(payload, executed, cumulative_quote),
        reduce_only=bool(payload.get("reduceOnly", False)),
        position_side=(
            str(payload["positionSide"]) if "positionSide" in payload else None
        ),
        update_time_ms=(
            int(payload.get("updateTime", payload.get("time")))
            if payload.get("updateTime", payload.get("time")) is not None
            else None
        ),
    )


def parse_margin_order(payload: dict[str, Any]) -> OrderSnapshot:
    return _parse_order(payload, "MARGIN")


def parse_um_order(payload: dict[str, Any]) -> OrderSnapshot:
    return _parse_order(payload, "USD_M_FUTURES")


def parse_order_fills(
    payloads: list[dict[str, Any]],
    market: str,
) -> tuple[FillSnapshot, ...]:
    result: list[FillSnapshot] = []
    for item in payloads:
        qty = _decimal(item, "qty")
        price = _decimal(item, "price")
        result.append(
            FillSnapshot(
                market=market,
                symbol=str(item["symbol"]),
                trade_id=int(item.get("id", item.get("tradeId"))),
                exchange_order_id=int(item["orderId"]),
                price=price,
                quantity=qty,
                quote_quantity=_decimal(item, "quoteQty", default=str(price * qty)),
                commission=_decimal(item, "commission"),
                commission_asset=str(item.get("commissionAsset", "")),
                realized_pnl=(
                    _decimal(item, "realizedPnl")
                    if "realizedPnl" in item
                    else None
                ),
                time_ms=int(item["time"]),
                buyer=bool(item["buyer"]) if "buyer" in item else None,
                maker=bool(item["maker"]) if "maker" in item else None,
            )
        )
    return tuple(result)
