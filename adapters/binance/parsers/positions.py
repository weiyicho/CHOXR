from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import PositionSnapshot


def _decimal(payload: dict[str, Any], *keys: str, default: str = "0") -> Decimal:
    for key in keys:
        if key in payload and payload[key] not in {None, ""}:
            return Decimal(str(payload[key]))
    return Decimal(default)


def parse_um_positions(
    payloads: list[dict[str, Any]],
) -> tuple[PositionSnapshot, ...]:
    positions: list[PositionSnapshot] = []
    for item in payloads:
        liquidation = _decimal(item, "liquidationPrice")
        leverage_value = item.get("leverage")
        positions.append(
            PositionSnapshot(
                symbol=str(item["symbol"]),
                quantity=_decimal(item, "positionAmt"),
                position_side=str(item.get("positionSide", "BOTH")),
                entry_price=_decimal(item, "entryPrice"),
                mark_price=_decimal(item, "markPrice"),
                notional=_decimal(item, "notional"),
                unrealized_pnl=_decimal(
                    item, "unRealizedProfit", "unrealizedProfit"
                ),
                liquidation_price=liquidation if liquidation > 0 else None,
                leverage=int(leverage_value) if leverage_value is not None else None,
                update_time_ms=(
                    int(item["updateTime"])
                    if item.get("updateTime") is not None
                    else None
                ),
            )
        )
    return tuple(positions)
