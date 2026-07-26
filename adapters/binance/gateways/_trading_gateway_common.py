from __future__ import annotations

from decimal import Decimal

from engine.domain.instrument import InstrumentId
from engine.domain.order import (
    OrderIntent,
    OrderRecord,
    OrderState,
    OrderType,
    Side,
    TimeInForce,
)

from ..parsers.models import OrderSnapshot


_STATE = {
    "PENDING_NEW": OrderState.SUBMITTING,
    "NEW": OrderState.NEW,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "FILLED": OrderState.FILLED,
    "CANCELED": OrderState.CANCELED,
    "CANCELLED": OrderState.CANCELED,
    "REJECTED": OrderState.REJECTED,
    "EXPIRED": OrderState.EXPIRED,
    "EXPIRED_IN_MATCH": OrderState.EXPIRED,
}


def reconstructed_intent(
    instrument: InstrumentId,
    snapshot: OrderSnapshot,
) -> OrderIntent:
    order_type = (
        OrderType(snapshot.order_type)
        if snapshot.order_type in {"MARKET", "LIMIT"}
        else OrderType.LIMIT
    )
    price = snapshot.price if order_type is OrderType.LIMIT else None
    if order_type is OrderType.LIMIT and price <= 0 and snapshot.average_price:
        price = snapshot.average_price
    if order_type is OrderType.LIMIT and (price is None or price <= 0):
        price = Decimal("0.00000001")
    return OrderIntent(
        execution_id="exchange-reconciliation",
        client_order_id=snapshot.client_order_id,
        instrument=instrument,
        side=Side(snapshot.side),
        quantity=snapshot.original_quantity,
        order_type=order_type,
        price=price,
        time_in_force=TimeInForce.GTC if order_type is OrderType.LIMIT else None,
        reduce_only=snapshot.reduce_only,
        reason="exchange_reconciliation",
    )


def order_record(intent: OrderIntent, snapshot: OrderSnapshot) -> OrderRecord:
    return OrderRecord(
        intent=intent,
        state=_STATE.get(snapshot.status, OrderState.UNKNOWN),
        exchange_order_id=str(snapshot.exchange_order_id),
        cumulative_quantity=snapshot.executed_quantity,
        average_price=snapshot.average_price,
    )
