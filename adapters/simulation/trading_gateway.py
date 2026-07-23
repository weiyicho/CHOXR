"""Small deterministic TradingGateway; deliberately not a market simulator."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderIntent, OrderRecord, OrderState
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.domain.order_state_machine import OrderStateMachine
from engine.ports.trading_gateway import UnknownSubmissionState


class SimulatedSubmitKind(str, Enum):
    ACKNOWLEDGE = "ACKNOWLEDGE"
    FULL_FILL = "FULL_FILL"
    REJECT = "REJECT"
    TIMEOUT_BEFORE_ACCEPT = "TIMEOUT_BEFORE_ACCEPT"
    TIMEOUT_AFTER_ACCEPT = "TIMEOUT_AFTER_ACCEPT"


@dataclass(frozen=True)
class SimulatedSubmitBehavior:
    kind: SimulatedSubmitKind
    fill_price: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        object.__setattr__(self, "fill_price", Decimal(str(self.fill_price)))
        if self.fill_price <= 0:
            raise ValueError("fill price must be positive")


class SimulatedTradingGateway:
    def __init__(self) -> None:
        self.orders: dict[str, OrderRecord] = {}
        self.submit_calls = 0
        self._behaviors: deque[SimulatedSubmitBehavior] = deque()
        self._state_machine = OrderStateMachine()

    def queue_submit(self, behavior: SimulatedSubmitBehavior) -> None:
        self._behaviors.append(behavior)

    def submit_order(self, intent: OrderIntent) -> OrderRecord:
        self.submit_calls += 1
        existing = self.orders.get(intent.client_order_id)
        if existing is not None:
            if existing.intent != intent:
                raise ValueError("client order ID was reused for another intent")
            return deepcopy(existing)

        behavior = self._behaviors.popleft() if self._behaviors else SimulatedSubmitBehavior(
            SimulatedSubmitKind.ACKNOWLEDGE
        )
        if behavior.kind is SimulatedSubmitKind.TIMEOUT_BEFORE_ACCEPT:
            raise UnknownSubmissionState(intent.client_order_id)

        order = OrderRecord(intent=intent)
        self._state_machine.apply(
            order,
            OrderEvent(OrderEventKind.SUBMIT_REQUESTED, intent.client_order_id),
        )
        if behavior.kind is SimulatedSubmitKind.REJECT:
            self._state_machine.apply(
                order,
                OrderEvent(
                    OrderEventKind.REJECTED,
                    intent.client_order_id,
                    reason="simulated rejection",
                ),
            )
            self.orders[intent.client_order_id] = order
            return deepcopy(order)

        exchange_order_id = f"sim-{len(self.orders) + 1}"
        self._state_machine.apply(
            order,
            OrderEvent(
                OrderEventKind.ACKNOWLEDGED,
                intent.client_order_id,
                exchange_order_id=exchange_order_id,
            ),
        )
        self.orders[intent.client_order_id] = order
        if behavior.kind is SimulatedSubmitKind.FULL_FILL:
            self.fill(
                intent.client_order_id,
                intent.quantity,
                behavior.fill_price,
            )
        if behavior.kind is SimulatedSubmitKind.TIMEOUT_AFTER_ACCEPT:
            raise UnknownSubmissionState(intent.client_order_id)
        return deepcopy(self.orders[intent.client_order_id])

    def get_order(
        self, instrument: InstrumentId, client_order_id: str
    ) -> OrderRecord | None:
        order = self.orders.get(client_order_id)
        if order is not None and order.intent.instrument != instrument:
            raise ValueError("instrument does not match simulated order")
        return deepcopy(order) if order is not None else None

    def cancel_order(
        self, instrument: InstrumentId, client_order_id: str
    ) -> OrderRecord:
        order = self.orders[client_order_id]
        if order.intent.instrument != instrument:
            raise ValueError("instrument does not match simulated order")
        if not order.is_terminal:
            self._state_machine.apply(
                order,
                OrderEvent(OrderEventKind.CANCEL_REQUESTED, client_order_id),
            )
            self._state_machine.apply(
                order,
                OrderEvent(OrderEventKind.CANCELED, client_order_id),
            )
        return deepcopy(order)

    def list_open_orders(
        self, instrument: InstrumentId | None = None
    ) -> tuple[OrderRecord, ...]:
        return tuple(
            deepcopy(order)
            for order in self.orders.values()
            if not order.is_terminal
            and (instrument is None or order.intent.instrument == instrument)
        )

    def fill(
        self,
        client_order_id: str,
        cumulative_quantity: Decimal | str,
        average_price: Decimal | str,
    ) -> OrderEvent:
        order = self.orders[client_order_id]
        event = OrderEvent(
            kind=OrderEventKind.TRADE,
            client_order_id=client_order_id,
            event_id=f"sim-fill-{client_order_id}-{cumulative_quantity}",
            cumulative_quantity=Decimal(str(cumulative_quantity)),
            average_price=Decimal(str(average_price)),
            exchange_order_id=order.exchange_order_id,
        )
        self._state_machine.apply(order, event)
        return event
