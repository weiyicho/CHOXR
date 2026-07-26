"""Pure order-sequencing decisions for funding-rate entry."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol

from engine.domain.order_event import OrderEventKind

from .hedge import HedgeDecision


ZERO = Decimal("0")
DecimalLike = Decimal | int | float | str


def _decimal(value: DecimalLike, field_name: str) -> Decimal:
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


class FundingOrderRole(str, Enum):
    """Role played by the order which emitted the committed event."""

    MAKER = "MAKER"
    HEDGE = "HEDGE"


class FundingCommandKind(str, Enum):
    """Side-effect request selected by a funding execution policy."""

    SUBMIT_HEDGE = "SUBMIT_HEDGE"
    CANCEL_MAKER = "CANCEL_MAKER"
    RECONCILE = "RECONCILE"
    MARK_OPEN = "MARK_OPEN"
    PAUSE = "PAUSE"
    RECOVER = "RECOVER"


@dataclass(frozen=True)
class FundingPolicyCommand:
    """One immutable request for the strategy worker to dispatch."""

    kind: FundingCommandKind
    quantity: Decimal | None = None
    reason: str = ""
    source_event_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", FundingCommandKind(self.kind))
        object.__setattr__(self, "reason", self.reason.strip())
        if self.source_event_id is not None:
            event_id = self.source_event_id.strip()
            if not event_id:
                raise ValueError("source_event_id cannot be blank")
            object.__setattr__(self, "source_event_id", event_id)
        if self.quantity is not None:
            quantity = _decimal(self.quantity, "quantity")
            if quantity <= ZERO:
                raise ValueError("command quantity must be positive")
            object.__setattr__(self, "quantity", quantity)
        if (
            self.kind is FundingCommandKind.SUBMIT_HEDGE
            and self.quantity is None
        ):
            raise ValueError("SUBMIT_HEDGE requires a quantity")
        if (
            self.kind is not FundingCommandKind.SUBMIT_HEDGE
            and self.quantity is not None
        ):
            raise ValueError(f"{self.kind.value} cannot specify a quantity")


@dataclass(frozen=True)
class FundingPolicyContext:
    """Committed state used for one policy decision.

    Quantity normalization belongs to ``FundingHedgeCalculator``. This context
    only adds event role, maker lifecycle, and the risk limit needed to choose
    the next commands.
    """

    event_role: FundingOrderRole
    event_kind: OrderEventKind
    maker_terminal: bool
    maker_remaining_quantity: Decimal
    hedge: HedgeDecision
    reference_price: Decimal
    max_unhedged_notional: Decimal
    session_status: str = "ENTERING"
    source_event_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_role", FundingOrderRole(self.event_role))
        object.__setattr__(self, "event_kind", OrderEventKind(self.event_kind))
        if not isinstance(self.maker_terminal, bool):
            raise TypeError("maker_terminal must be a bool")
        if not isinstance(self.hedge, HedgeDecision):
            raise TypeError("hedge must be a HedgeDecision")

        for field_name in (
            "maker_remaining_quantity",
            "reference_price",
            "max_unhedged_notional",
        ):
            object.__setattr__(
                self,
                field_name,
                _decimal(getattr(self, field_name), field_name),
            )
        if self.maker_remaining_quantity < ZERO:
            raise ValueError("maker_remaining_quantity cannot be negative")
        if self.reference_price <= ZERO:
            raise ValueError("reference_price must be positive")
        if self.max_unhedged_notional < ZERO:
            raise ValueError("max_unhedged_notional cannot be negative")

        status = self.session_status.strip().upper()
        if not status:
            raise ValueError("session_status is required")
        object.__setattr__(self, "session_status", status)
        if self.source_event_id is not None:
            event_id = self.source_event_id.strip()
            if not event_id:
                raise ValueError("source_event_id cannot be blank")
            object.__setattr__(self, "source_event_id", event_id)


class FundingExecutionPolicy(Protocol):
    """Select commands from committed strategy state without doing I/O."""

    def decide(
        self,
        context: FundingPolicyContext,
    ) -> tuple[FundingPolicyCommand, ...]: ...


class PerpetualMakerSpotTakerPolicy:
    """Enter with a perpetual maker and incrementally hedge on Spot."""

    _ACTIVE_STATUSES = frozenset({"ENTERING", "HEDGING"})
    _DECISION_EVENTS = frozenset(
        {
            OrderEventKind.TRADE,
            OrderEventKind.CANCELED,
            OrderEventKind.EXPIRED,
            OrderEventKind.RECONCILED,
        }
    )

    def decide(
        self,
        context: FundingPolicyContext,
    ) -> tuple[FundingPolicyCommand, ...]:
        if context.session_status not in self._ACTIVE_STATUSES:
            return ()

        if (
            context.event_role is FundingOrderRole.HEDGE
            and context.event_kind is OrderEventKind.REJECTED
        ):
            return self._stop_and_inspect(
                context,
                recovery_kind=FundingCommandKind.PAUSE,
                reason="hedge order rejected",
            )

        if context.event_kind is OrderEventKind.REQUEST_TIMED_OUT:
            return (
                self._command(
                    FundingCommandKind.RECONCILE,
                    context,
                    "order request timed out",
                ),
                self._command(
                    FundingCommandKind.PAUSE,
                    context,
                    "wait for reconciliation before another decision",
                ),
            )

        if (
            context.event_role is FundingOrderRole.HEDGE
            and context.event_kind
            in {OrderEventKind.CANCELED, OrderEventKind.EXPIRED}
        ):
            return self._stop_and_inspect(
                context,
                recovery_kind=FundingCommandKind.RECOVER,
                reason="hedge terminated before confirmed neutrality",
            )

        if (
            context.event_role is FundingOrderRole.MAKER
            and context.event_kind is OrderEventKind.REJECTED
        ):
            return (
                self._command(
                    FundingCommandKind.RECONCILE,
                    context,
                    "maker order rejected",
                ),
                self._command(
                    FundingCommandKind.PAUSE,
                    context,
                    "entry cannot continue without its maker leg",
                ),
            )

        if context.event_kind not in self._DECISION_EVENTS:
            return ()

        commands: list[FundingPolicyCommand] = []
        if self._unhedged_notional(context) > context.max_unhedged_notional:
            if self._maker_can_be_canceled(context):
                commands.append(
                    self._command(
                        FundingCommandKind.CANCEL_MAKER,
                        context,
                        "maximum unhedged notional exceeded",
                    )
                )

        # Serialize Spot hedge submissions. The calculator already reserves
        # pending quantity, while this guard also prevents a replay from
        # dispatching another order before the pending one is resolved.
        if (
            context.hedge.pending_quantity == ZERO
            and context.hedge.tradable_quantity > ZERO
        ):
            commands.append(
                self._command(
                    FundingCommandKind.SUBMIT_HEDGE,
                    context,
                    "cover confirmed perpetual fills",
                    quantity=context.hedge.tradable_quantity,
                )
            )
            return tuple(commands)

        if context.hedge.pending_quantity > ZERO:
            return tuple(commands)

        if context.maker_terminal and context.hedge.within_tolerance:
            commands.append(
                self._command(
                    FundingCommandKind.MARK_OPEN,
                    context,
                    "maker is terminal and confirmed delta is within tolerance",
                )
            )
            return tuple(commands)

        if (
            context.maker_terminal
            and not context.hedge.within_tolerance
            and context.hedge.tradable_quantity == ZERO
        ):
            commands.extend(
                (
                    self._command(
                        FundingCommandKind.RECONCILE,
                        context,
                        "terminal maker left non-tradable residual delta",
                    ),
                    self._command(
                        FundingCommandKind.RECOVER,
                        context,
                        "terminal residual is outside delta tolerance",
                    ),
                )
            )

        return tuple(commands)

    @staticmethod
    def _unhedged_notional(context: FundingPolicyContext) -> Decimal:
        underhedged_quantity = max(ZERO, -context.hedge.net_delta)
        return underhedged_quantity * context.reference_price

    @staticmethod
    def _maker_can_be_canceled(context: FundingPolicyContext) -> bool:
        return (
            not context.maker_terminal
            and context.maker_remaining_quantity > ZERO
        )

    def _stop_and_inspect(
        self,
        context: FundingPolicyContext,
        *,
        recovery_kind: FundingCommandKind,
        reason: str,
    ) -> tuple[FundingPolicyCommand, ...]:
        commands: list[FundingPolicyCommand] = []
        if self._maker_can_be_canceled(context):
            commands.append(
                self._command(
                    FundingCommandKind.CANCEL_MAKER,
                    context,
                    reason,
                )
            )
        commands.extend(
            (
                self._command(FundingCommandKind.RECONCILE, context, reason),
                self._command(recovery_kind, context, reason),
            )
        )
        return tuple(commands)

    @staticmethod
    def _command(
        kind: FundingCommandKind,
        context: FundingPolicyContext,
        reason: str,
        *,
        quantity: Decimal | None = None,
    ) -> FundingPolicyCommand:
        return FundingPolicyCommand(
            kind=kind,
            quantity=quantity,
            reason=reason,
            source_event_id=context.source_event_id,
        )
