"""Commands and queries required to execute orders at any venue."""

from __future__ import annotations

from typing import Optional, Protocol

from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord


class UnknownSubmissionState(RuntimeError):
    """A side-effect request may or may not have been accepted.

    The caller must reconcile by the same ``client_order_id``. It must not
    create a fresh ID and blindly repeat a submit or cancel command.
    """

    def __init__(self, client_order_id: str):
        super().__init__(f"submission state is unknown for {client_order_id}")
        self.client_order_id = client_order_id


class OrderSubmissionRejected(RuntimeError):
    """The venue definitively refused an order submission.

    Unlike :class:`UnknownSubmissionState`, the request produced an
    authoritative error response and therefore must not be reconciled or
    blindly retried.  The execution service records a terminal ``REJECTED``
    transition using the same client order ID.
    """

    def __init__(self, client_order_id: str, reason: str):
        normalized_reason = reason.strip() or "exchange rejected order submission"
        super().__init__(normalized_reason)
        self.client_order_id = client_order_id
        self.reason = normalized_reason


class TradingGateway(Protocol):
    def submit_order(self, intent: OrderIntent) -> OrderRecord: ...

    def get_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> Optional[OrderRecord]: ...

    def cancel_order(
        self,
        instrument: InstrumentId,
        client_order_id: str,
    ) -> OrderRecord: ...

    def list_open_orders(
        self,
        instrument: Optional[InstrumentId] = None,
    ) -> tuple[OrderRecord, ...]: ...
