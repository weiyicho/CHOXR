from __future__ import annotations

from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord
from engine.ports.trading_gateway import (
    OrderSubmissionRejected,
    UnknownSubmissionState,
)

from ..api.portfolio_margin import PortfolioMarginApi
from ..parsers.orders import parse_um_order
from ..transport.errors import (
    BinanceError,
    BinanceRequestError,
    UnknownExecutionOutcome,
)
from ._trading_gateway_common import order_record, reconstructed_intent
from .market_data_gateway import _market_family


class ClassicPortfolioMarginUsdMTradingGateway:
    """Trade the Portfolio Margin USD-M perpetual leg through PAPI."""

    def __init__(self, api: PortfolioMarginApi):
        self._api = api

    def submit_order(self, intent: OrderIntent) -> OrderRecord:
        self._require_supported(intent.instrument)
        time_in_force = (
            "GTX"
            if intent.post_only
            else (intent.time_in_force.value if intent.time_in_force else None)
        )
        try:
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
        except UnknownExecutionOutcome as exc:
            raise UnknownSubmissionState(intent.client_order_id) from exc
        except BinanceError as exc:
            raise OrderSubmissionRejected(intent.client_order_id, str(exc)) from exc
        snapshot = parse_um_order(payload)
        return order_record(intent, snapshot)

    def get_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> OrderRecord | None:
        self._require_supported(instrument)
        try:
            payload = self._api.query_um_order(
                instrument.symbol,
                client_order_id=client_order_id,
            )
        except BinanceRequestError as exc:
            if exc.context.code == -2013:
                return None
            raise
        snapshot = parse_um_order(payload)
        return order_record(reconstructed_intent(instrument, snapshot), snapshot)

    def cancel_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> OrderRecord:
        self._require_supported(instrument)
        try:
            payload = self._api.cancel_um_order(
                instrument.symbol,
                client_order_id=client_order_id,
            )
        except UnknownExecutionOutcome as exc:
            raise UnknownSubmissionState(client_order_id) from exc
        snapshot = parse_um_order(payload)
        return order_record(reconstructed_intent(instrument, snapshot), snapshot)

    def list_open_orders(
        self,
        instrument: InstrumentId | None = None,
    ) -> tuple[OrderRecord, ...]:
        if instrument is not None:
            self._require_supported(instrument)
        payloads = self._api.list_um_open_orders(
            instrument.symbol if instrument is not None else None
        )
        records: list[OrderRecord] = []
        for payload in payloads:
            snapshot = parse_um_order(payload)
            resolved_instrument = instrument or InstrumentId(
                venue="binance",
                market="USD_M_FUTURES",
                symbol=snapshot.symbol,
            )
            records.append(
                order_record(
                    reconstructed_intent(resolved_instrument, snapshot),
                    snapshot,
                )
            )
        return tuple(records)

    @staticmethod
    def _require_supported(instrument: InstrumentId) -> None:
        family = _market_family(instrument)
        if family != "UM":
            raise ValueError(
                "Classic Portfolio Margin USD-M gateway cannot serve "
                f"market {instrument.market!r}"
            )
