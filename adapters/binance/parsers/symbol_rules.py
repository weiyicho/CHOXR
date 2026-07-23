from __future__ import annotations

from decimal import Decimal
from typing import Any

from .models import SymbolRules


def _decimal(value: object | None) -> Decimal | None:
    if value in {None, ""}:
        return None
    return Decimal(str(value))


def parse_symbol_rules(payload: dict[str, Any]) -> SymbolRules:
    filters = {item["filterType"]: item for item in payload.get("filters", [])}
    price_filter = filters.get("PRICE_FILTER", {})
    lot_size = filters.get("LOT_SIZE", {})
    market_lot_size = filters.get("MARKET_LOT_SIZE", {})
    notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL") or {}
    min_notional = notional.get("minNotional", notional.get("notional"))
    max_notional = notional.get("maxNotional")
    return SymbolRules(
        symbol=str(payload["symbol"]),
        status=str(payload.get("status", "UNKNOWN")),
        base_asset=str(payload.get("baseAsset", "")),
        quote_asset=str(payload.get("quoteAsset", "")),
        price_tick=Decimal(str(price_filter["tickSize"])),
        quantity_step=Decimal(str(lot_size["stepSize"])),
        min_quantity=Decimal(str(lot_size["minQty"])),
        max_quantity=_decimal(lot_size.get("maxQty")),
        min_notional=_decimal(min_notional),
        max_notional=_decimal(max_notional),
        market_quantity_step=_decimal(market_lot_size.get("stepSize")),
        market_min_quantity=_decimal(market_lot_size.get("minQty")),
        market_max_quantity=_decimal(market_lot_size.get("maxQty")),
    )


def parse_exchange_info(
    payload: dict[str, Any],
    symbol: str | None = None,
) -> SymbolRules | tuple[SymbolRules, ...]:
    symbols = payload.get("symbols", [])
    if symbol is None:
        return tuple(parse_symbol_rules(item) for item in symbols)
    for item in symbols:
        if item.get("symbol") == symbol:
            return parse_symbol_rules(item)
    raise ValueError(f"symbol {symbol!r} is absent from exchangeInfo")
