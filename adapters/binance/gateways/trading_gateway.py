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
from engine.ports.trading_gateway import (
    OrderSubmissionRejected,
    UnknownSubmissionState,
)

from ..api.portfolio_margin import PortfolioMarginApi
from ..parsers.models import OrderSnapshot
from ..parsers.orders import parse_margin_order, parse_um_order
from ..transport.errors import (
    BinanceError,
    BinanceRequestError,
    UnknownExecutionOutcome,
)
from .market_data_gateway import _market_family


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


class ClassicPortfolioMarginTradingGateway:
    def __init__(self, api: PortfolioMarginApi):
        self._api = api

    def submit_order(self, intent: OrderIntent) -> OrderRecord:
        family = _market_family(intent.instrument)
        try:
            if family == "SPOT":
                payload = self._api.place_margin_order(
                    symbol=intent.instrument.symbol,
                    side=intent.side.value,
                    order_type=intent.order_type.value,
                    quantity=intent.quantity,
                    client_order_id=intent.client_order_id,
                    price=intent.price,
                    time_in_force=(
                        intent.time_in_force.value if intent.time_in_force else None
                    ),
                    side_effect_type="NO_SIDE_EFFECT",
                )
                snapshot = parse_margin_order(payload)
            else:
                time_in_force = (
                    "GTX"
                    if intent.post_only
                    else (intent.time_in_force.value if intent.time_in_force else None)
                )
                payload = self._api.place_um_order(
                    symbol=intent.instrument.symbol,
                    side=intent.side.value,
                    order_type=intent.order_type.value,
                    quantity=intent.quantity,
                    client_order_id=intent.client_order_id,
                    price=intent.price,
                    time_in_force=time_in_force,
                    reduce_only=intent.reduce_only,
                )
                snapshot = parse_um_order(payload)
        except UnknownExecutionOutcome as exc:
            raise UnknownSubmissionState(intent.client_order_id) from exc
        except BinanceError as exc:
            # Binance returned an authoritative error response.  No order was
            # accepted, so this is a terminal rejection rather than UNKNOWN.
            raise OrderSubmissionRejected(
                intent.client_order_id,
                str(exc),
            ) from exc
        return self._record(intent, snapshot)

    def get_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> OrderRecord | None:
        family = _market_family(instrument)
        try:
            payload = (
                self._api.query_margin_order(
                    instrument.symbol, client_order_id=client_order_id
                )
                if family == "SPOT"
                else self._api.query_um_order(
                    instrument.symbol, client_order_id=client_order_id
                )
            )
        except BinanceRequestError as exc:
            if exc.context.code == -2013:
                return None
            raise
        snapshot = (
            parse_margin_order(payload) if family == "SPOT" else parse_um_order(payload)
        )
        return self._record(self._reconstructed_intent(instrument, snapshot), snapshot)

    def cancel_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> OrderRecord:
        family = _market_family(instrument)
        try:
            payload = (
                self._api.cancel_margin_order(
                    instrument.symbol, client_order_id=client_order_id
                )
                if family == "SPOT"
                else self._api.cancel_um_order(
                    instrument.symbol, client_order_id=client_order_id
                )
            )
        except UnknownExecutionOutcome as exc:
            raise UnknownSubmissionState(client_order_id) from exc
        snapshot = (
            parse_margin_order(payload) if family == "SPOT" else parse_um_order(payload)
        )
        return self._record(self._reconstructed_intent(instrument, snapshot), snapshot)

    def list_open_orders(
        self,
        instrument: InstrumentId | None = None,
    ) -> tuple[OrderRecord, ...]:
        if instrument is None:
            margin_payloads = self._api.list_margin_open_orders()
            um_payloads = self._api.list_um_open_orders()
            pairs = [
                *((item, "MARGIN") for item in margin_payloads),
                *((item, "UM") for item in um_payloads),
            ]
        else:
            family = _market_family(instrument)
            payloads = (
                self._api.list_margin_open_orders(instrument.symbol)
                if family == "SPOT"
                else self._api.list_um_open_orders(instrument.symbol)
            )
            pairs = [(item, family) for item in payloads]

        records: list[OrderRecord] = []
        for payload, family in pairs:
            snapshot = (
                parse_margin_order(payload)
                if family in {"SPOT", "MARGIN"}
                else parse_um_order(payload)
            )
            resolved_instrument = instrument or InstrumentId(
                venue="binance",
                market="MARGIN" if family in {"SPOT", "MARGIN"} else "USD_M_FUTURES",
                symbol=snapshot.symbol,
            )
            records.append(
                self._record(
                    self._reconstructed_intent(resolved_instrument, snapshot), snapshot
                )
            )
        return tuple(records)

    @staticmethod
    def _reconstructed_intent(
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

    @staticmethod
    def _record(intent: OrderIntent, snapshot: OrderSnapshot) -> OrderRecord:
        return OrderRecord(
            intent=intent,
            state=_STATE.get(snapshot.status, OrderState.UNKNOWN),
            exchange_order_id=str(snapshot.exchange_order_id),
            cumulative_quantity=snapshot.executed_quantity,
            average_price=snapshot.average_price,
        )
