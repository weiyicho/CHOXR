"""Order lifecycle state machine based on exchange/FIX-style semantics."""

from __future__ import annotations

from datetime import datetime, timezone

from ._numbers import ZERO
from .order import OrderRecord, OrderState
from .order_event import OrderEvent, OrderEventKind


class InvalidOrderTransition(ValueError):
    """Raised when an event is not valid for the current order state."""


class OrderStateMachine:
    """Apply exchange events to one order without double-counting fills."""

    RECONCILABLE_STATES = {
        OrderState.NEW,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
        OrderState.CANCELED,
        OrderState.REJECTED,
        OrderState.EXPIRED,
    }

    def apply(self, order: OrderRecord, event: OrderEvent) -> OrderRecord:
        if (
            event.client_order_id
            and event.client_order_id != order.intent.client_order_id
        ):
            raise InvalidOrderTransition("event belongs to a different client_order_id")
        if order.is_terminal:
            if self._is_idempotent_terminal_replay(order, event):
                self._enrich_terminal_snapshot(order, event)
                order.updated_at = datetime.now(timezone.utc)
                return order
            raise InvalidOrderTransition(
                f"cannot apply {event.kind.value} to terminal {order.state.value}"
            )

        handlers = {
            OrderEventKind.SUBMIT_REQUESTED: self._submit,
            OrderEventKind.ACKNOWLEDGED: self._acknowledge,
            OrderEventKind.TRADE: self._trade,
            OrderEventKind.CANCEL_REQUESTED: self._cancel_requested,
            OrderEventKind.CANCELED: self._canceled,
            OrderEventKind.REJECTED: self._rejected,
            OrderEventKind.EXPIRED: self._expired,
            OrderEventKind.REQUEST_TIMED_OUT: self._timed_out,
            OrderEventKind.RECONCILED: self._reconciled,
        }
        handlers[event.kind](order, event)
        order.updated_at = datetime.now(timezone.utc)
        return order

    @staticmethod
    def _is_idempotent_terminal_replay(
        order: OrderRecord,
        event: OrderEvent,
    ) -> bool:
        if (
            event.kind is OrderEventKind.RECONCILED
            and event.reconciled_state is order.state
            and (
                event.cumulative_quantity is None
                or event.cumulative_quantity == order.cumulative_quantity
            )
        ):
            return True
        if (
            order.state is OrderState.FILLED
            and event.kind is OrderEventKind.TRADE
            and event.cumulative_quantity == order.cumulative_quantity
        ):
            return True
        terminal_event_for_state = {
            OrderState.CANCELED: OrderEventKind.CANCELED,
            OrderState.REJECTED: OrderEventKind.REJECTED,
            OrderState.EXPIRED: OrderEventKind.EXPIRED,
        }
        return (
            terminal_event_for_state.get(order.state) is event.kind
            and (
                event.cumulative_quantity is None
                or event.cumulative_quantity == order.cumulative_quantity
            )
        )

    @staticmethod
    def _enrich_terminal_snapshot(
        order: OrderRecord,
        event: OrderEvent,
    ) -> None:
        """Merge metadata learned after a terminal execution response.

        Binance can acknowledge a fully filled MARKET order with zero or
        missing price fields. A later read-only order query has the same
        terminal state and cumulative quantity but carries the final average
        price. This enrichment must never change state or fill quantity.
        """

        order.exchange_order_id = event.exchange_order_id or order.exchange_order_id
        if event.average_price is not None and event.average_price > ZERO:
            order.average_price = event.average_price
        if order.state is OrderState.REJECTED and event.reason:
            order.rejection_reason = event.reason

    @staticmethod
    def _require(order: OrderRecord, allowed: set[OrderState], event: OrderEvent) -> None:
        if order.state not in allowed:
            raise InvalidOrderTransition(
                f"{event.kind.value} is invalid from {order.state.value}"
            )

    def _submit(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(order, {OrderState.CREATED}, event)
        order.state = OrderState.SUBMITTING

    def _acknowledge(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {
                OrderState.SUBMITTING,
                OrderState.UNKNOWN,
                OrderState.NEW,
                OrderState.PARTIALLY_FILLED,
                OrderState.PENDING_CANCEL,
            },
            event,
        )
        order.exchange_order_id = event.exchange_order_id or order.exchange_order_id
        if order.state in {OrderState.SUBMITTING, OrderState.UNKNOWN}:
            order.state = OrderState.NEW

    def _trade(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {
                OrderState.SUBMITTING,
                OrderState.UNKNOWN,
                OrderState.NEW,
                OrderState.PARTIALLY_FILLED,
                OrderState.PENDING_CANCEL,
            },
            event,
        )
        if event.cumulative_quantity is None:
            raise InvalidOrderTransition("TRADE requires cumulative_quantity")
        if event.cumulative_quantity < order.cumulative_quantity:
            raise InvalidOrderTransition("cumulative fill quantity moved backwards")
        if event.cumulative_quantity > order.intent.quantity:
            raise InvalidOrderTransition("cumulative fill exceeds requested quantity")

        order.exchange_order_id = event.exchange_order_id or order.exchange_order_id
        order.cumulative_quantity = event.cumulative_quantity
        if event.average_price is not None:
            order.average_price = event.average_price

        if order.cumulative_quantity == order.intent.quantity:
            order.state = OrderState.FILLED
        elif order.cumulative_quantity > ZERO:
            order.state = OrderState.PARTIALLY_FILLED
        else:
            order.state = OrderState.NEW

    def _cancel_requested(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {OrderState.NEW, OrderState.PARTIALLY_FILLED},
            event,
        )
        order.state = OrderState.PENDING_CANCEL

    def _canceled(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {
                OrderState.NEW,
                OrderState.PARTIALLY_FILLED,
                OrderState.PENDING_CANCEL,
                OrderState.UNKNOWN,
            },
            event,
        )
        self._apply_observed_fill(order, event)
        order.state = OrderState.CANCELED

    def _rejected(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {OrderState.SUBMITTING, OrderState.UNKNOWN, OrderState.NEW},
            event,
        )
        order.exchange_order_id = event.exchange_order_id or order.exchange_order_id
        order.rejection_reason = event.reason
        order.state = OrderState.REJECTED

    def _expired(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {
                OrderState.NEW,
                OrderState.PARTIALLY_FILLED,
                OrderState.PENDING_CANCEL,
            },
            event,
        )
        self._apply_observed_fill(order, event)
        order.state = OrderState.EXPIRED

    def _timed_out(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {
                OrderState.SUBMITTING,
                OrderState.PENDING_CANCEL,
                OrderState.UNKNOWN,
            },
            event,
        )
        order.state = OrderState.UNKNOWN

    def _reconciled(self, order: OrderRecord, event: OrderEvent) -> None:
        self._require(
            order,
            {
                OrderState.SUBMITTING,
                OrderState.UNKNOWN,
                OrderState.NEW,
                OrderState.PARTIALLY_FILLED,
                OrderState.PENDING_CANCEL,
            },
            event,
        )
        if event.reconciled_state not in self.RECONCILABLE_STATES:
            raise InvalidOrderTransition("RECONCILED requires an exchange order state")
        if (
            event.reconciled_state is OrderState.FILLED
            and event.cumulative_quantity != order.intent.quantity
        ):
            raise InvalidOrderTransition(
                "FILLED reconciliation requires the full cumulative quantity"
            )
        self._apply_observed_fill(order, event)
        order.exchange_order_id = event.exchange_order_id or order.exchange_order_id
        order.state = event.reconciled_state

    @staticmethod
    def _apply_observed_fill(order: OrderRecord, event: OrderEvent) -> None:
        if event.cumulative_quantity is not None:
            if event.cumulative_quantity < order.cumulative_quantity:
                raise InvalidOrderTransition("cumulative fill quantity moved backwards")
            if event.cumulative_quantity > order.intent.quantity:
                raise InvalidOrderTransition("cumulative fill exceeds requested quantity")
            order.cumulative_quantity = event.cumulative_quantity
        if event.average_price is not None:
            order.average_price = event.average_price
        order.exchange_order_id = event.exchange_order_id or order.exchange_order_id
