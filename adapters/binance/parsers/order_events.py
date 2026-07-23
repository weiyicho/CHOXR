from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import OrderEventSnapshot, ZERO


def _decimal(payload: dict[str, Any], key: str, default: str = "0") -> Decimal:
    value = payload.get(key, default)
    return Decimal(str(value if value not in {None, ""} else default))


def parse_order_event(payload: dict[str, Any]) -> OrderEventSnapshot:
    event_type = str(payload.get("e", ""))
    if event_type == "executionReport":
        executed = _decimal(payload, "z")
        cumulative_quote = _decimal(payload, "Z")
        average = cumulative_quote / executed if executed > ZERO else None
        return OrderEventSnapshot(
            market="MARGIN",
            event_type=event_type,
            event_time_ms=int(payload["E"]),
            transaction_time_ms=int(payload["T"]) if "T" in payload else None,
            symbol=str(payload["s"]),
            client_order_id=str(payload.get("c", "")),
            original_client_order_id=str(payload["C"]) if payload.get("C") else None,
            exchange_order_id=int(payload["i"]),
            side=str(payload["S"]),
            order_type=str(payload["o"]),
            execution_type=str(payload["x"]),
            status=str(payload["X"]),
            original_quantity=_decimal(payload, "q"),
            last_executed_quantity=_decimal(payload, "l"),
            cumulative_quantity=executed,
            last_executed_price=_decimal(payload, "L"),
            average_price=average,
            trade_id=int(payload["t"]) if int(payload.get("t", -1)) >= 0 else None,
            reject_reason=str(payload["r"]) if payload.get("r") not in {None, "NONE"} else None,
        )

    if event_type == "ORDER_TRADE_UPDATE":
        order = payload["o"]
        average = _decimal(order, "ap")
        return OrderEventSnapshot(
            market="USD_M_FUTURES",
            event_type=event_type,
            event_time_ms=int(payload["E"]),
            transaction_time_ms=int(payload["T"]) if "T" in payload else None,
            symbol=str(order["s"]),
            client_order_id=str(order.get("c", "")),
            original_client_order_id=None,
            exchange_order_id=int(order["i"]),
            side=str(order["S"]),
            order_type=str(order["o"]),
            execution_type=str(order["x"]),
            status=str(order["X"]),
            original_quantity=_decimal(order, "q"),
            last_executed_quantity=_decimal(order, "l"),
            cumulative_quantity=_decimal(order, "z"),
            last_executed_price=_decimal(order, "L"),
            average_price=average if average > ZERO else None,
            trade_id=int(order["t"]) if int(order.get("t", -1)) >= 0 else None,
            reject_reason=(
                str(order["r"]) if order.get("r") not in {None, "NONE"} else None
            ),
            reduce_only=bool(order.get("R", False)),
            position_side=str(order.get("ps", "BOTH")),
        )

    raise ValueError(f"unsupported Binance order event: {event_type!r}")
