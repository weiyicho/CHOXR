"""Durable event-driven orchestration for funding-rate entry."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from decimal import Decimal

from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderRecord, OrderState
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.execution import OrderExecutionService
from engine.ports.fill_gateway import OrderFillGateway
from engine.ports.market_data_gateway import MarketDataGateway
from engine.ports.repositories import OrderEventRepository, OrderRepository

from .execution_policy import (
    FundingCommandKind,
    FundingExecutionPolicy,
    FundingOrderRole,
    FundingPolicyCommand,
    FundingPolicyContext,
    PerpetualMakerSpotTakerPolicy,
)
from .hedge import FundingHedgeCalculator, HedgeCalculationInput
from .order import FundingOrderExecutor
from .session import (
    FundingAction,
    FundingActionRepository,
    FundingActionStatus,
    FundingSession,
    FundingSessionRepository,
    FundingSessionStatus,
)


LOGGER = logging.getLogger(__name__)
ZERO = Decimal("0")
_MAX_DISPATCH_CASCADE = 12
_DEFAULT_FILL_RETRY_INTERVAL_SECONDS = 5.0


def _trace(category: str, message: str, **fields: object) -> None:
    """Emit one compact, secret-free live execution trace."""

    details = " ".join(
        f"{name}={value.value if hasattr(value, 'value') else value}"
        for name, value in fields.items()
        if value is not None
    )
    suffix = f" {details}" if details else ""
    print(f"[FUNDING][{category}] {message}{suffix}", flush=True)


@dataclass(frozen=True)
class FundingDispatchOutcome:
    """Authoritative order snapshots produced by one durable action."""

    action: FundingAction
    orders: tuple[OrderRecord, ...] = ()


class FundingActionDispatcher:
    """Execute persisted policy actions with stable exchange identities."""

    def __init__(
        self,
        *,
        session_repository: FundingSessionRepository,
        action_repository: FundingActionRepository,
        order_repository: OrderRepository,
        order_executor: FundingOrderExecutor,
        execution_service: OrderExecutionService,
    ) -> None:
        self._sessions = session_repository
        self._actions = action_repository
        self._orders = order_repository
        self._order_executor = order_executor
        self._execution = execution_service

    def dispatch(self, action: FundingAction) -> FundingDispatchOutcome:
        _trace(
            "ACTION",
            "dispatch requested",
            action_id=action.action_id,
            type=action.action_type,
            status=action.status,
        )
        current = self._actions.get_action(action.action_id)
        if current is None:
            _trace(
                "ACTION",
                "dispatch rejected",
                action_id=action.action_id,
                reason="action is not persisted",
            )
            raise KeyError(f"unknown funding action: {action.action_id}")
        if current.status is FundingActionStatus.COMPLETED:
            _trace(
                "ACTION",
                "dispatch skipped",
                action_id=current.action_id,
                reason="already completed",
            )
            return FundingDispatchOutcome(current)
        if current.status is FundingActionStatus.FAILED:
            _trace(
                "ACTION",
                "dispatch skipped",
                action_id=current.action_id,
                reason="already failed",
            )
            return FundingDispatchOutcome(current)

        recovering_in_progress = current.status is FundingActionStatus.IN_PROGRESS
        current = self._actions.update_action_status(
            current.action_id,
            FundingActionStatus.IN_PROGRESS,
        )
        _trace(
            "ACTION",
            "action marked in progress",
            action_id=current.action_id,
            type=current.action_type,
        )
        try:
            orders = self._execute(current)
        except Exception as exc:
            _trace(
                "RECOVERY",
                "action execution failed",
                action_id=current.action_id,
                type=current.action_type,
                reason=str(exc),
            )
            LOGGER.exception(
                "funding action %s failed",
                current.action_id,
            )
            if current.action_type == FundingCommandKind.SUBMIT_HEDGE.value:
                failed, recovery_orders = self._fail_hedge_and_stop(
                    current,
                    str(exc),
                )
                return FundingDispatchOutcome(failed, recovery_orders)
            failed = self._actions.update_action_status(
                current.action_id,
                FundingActionStatus.FAILED,
                failure_reason=str(exc),
            )
            self._set_session_status(
                current.execution_id,
                FundingSessionStatus.RECOVERING,
            )
            _trace(
                "RECOVERY",
                "non-hedge action failed; session recovering",
                action_id=failed.action_id,
                execution_id=failed.execution_id,
            )
            return FundingDispatchOutcome(failed)

        if any(order.state is OrderState.UNKNOWN for order in orders):
            unknown_ids = ",".join(
                order.intent.client_order_id
                for order in orders
                if order.state is OrderState.UNKNOWN
            )
            self._set_session_status(
                current.execution_id,
                FundingSessionStatus.PAUSED,
            )
            _trace(
                "RECOVERY",
                "order outcome unknown; session paused",
                action_id=current.action_id,
                client_order_ids=unknown_ids,
                reason="reconcile the same client order id before retry",
            )
            return FundingDispatchOutcome(current, orders)
        if (
            current.action_type == FundingCommandKind.SUBMIT_HEDGE.value
            and any(order.state is OrderState.REJECTED for order in orders)
        ):
            _trace(
                "RECOVERY",
                "Spot hedge rejected",
                action_id=current.action_id,
                reason="cancel maker and reconcile atomically",
            )
            rejected, recovery_orders = self._fail_hedge_and_stop(
                current,
                "exchange rejected order action",
            )
            return FundingDispatchOutcome(
                rejected,
                (*orders, *recovery_orders),
            )

        completed = self._actions.update_action_status(
            current.action_id,
            FundingActionStatus.COMPLETED,
        )
        if (
            recovering_in_progress
            and current.action_type == FundingCommandKind.SUBMIT_HEDGE.value
        ):
            session = self._require_session(current.execution_id)
            if session.status is FundingSessionStatus.PAUSED:
                self._set_session_status(
                    current.execution_id,
                    FundingSessionStatus.HEDGING,
                )
                _trace(
                    "RECOVERY",
                    "same-id reconciliation succeeded; session resumed",
                    action_id=current.action_id,
                    execution_id=current.execution_id,
                )
        _trace(
            "ACTION",
            "dispatch completed",
            action_id=completed.action_id,
            type=completed.action_type,
            order_count=len(orders),
        )
        for order in orders:
            _trace(
                "ORDER",
                "authoritative order state",
                client_order_id=order.intent.client_order_id,
                state=order.state,
                cumulative_quantity=order.cumulative_quantity,
                leaves_quantity=order.leaves_quantity,
            )
        return FundingDispatchOutcome(completed, orders)

    def dispatch_pending(
        self,
        execution_id: str | None = None,
    ) -> tuple[FundingDispatchOutcome, ...]:
        return tuple(
            self.dispatch(action)
            for action in self._actions.list_pending_actions(execution_id)
        )

    def _execute(self, action: FundingAction) -> tuple[OrderRecord, ...]:
        kind = FundingCommandKind(action.action_type)
        session = self._require_session(action.execution_id)

        if kind is FundingCommandKind.SUBMIT_HEDGE:
            if action.client_order_id is None or action.requested_quantity is None:
                raise ValueError("SUBMIT_HEDGE action is missing order fields")
            existing = self._orders.get(action.client_order_id)
            if existing is not None:
                _trace(
                    "ORDER",
                    "existing Spot hedge found",
                    client_order_id=action.client_order_id,
                    state=existing.state,
                    cumulative_quantity=existing.cumulative_quantity,
                )
                if existing.state is OrderState.UNKNOWN:
                    _trace(
                        "RECOVERY",
                        "reconciling UNKNOWN Spot hedge with same id",
                        client_order_id=action.client_order_id,
                    )
                    existing = self._execution.reconcile(action.client_order_id)
                return (existing,)
            _trace(
                "ORDER",
                "preparing Spot MARKET hedge",
                client_order_id=action.client_order_id,
                symbol=session.symbol,
                quantity=action.requested_quantity,
                max_notional=session.capital,
            )
            prepared = self._order_executor.prepare_spot_hedge(
                execution_id=session.execution_id,
                client_order_id=action.client_order_id,
                symbol=session.symbol,
                quantity=action.requested_quantity,
                max_order_notional=session.capital,
            )
            _trace(
                "ORDER",
                "Spot hedge approved; submitting",
                client_order_id=action.client_order_id,
                quantity=action.requested_quantity,
            )
            submitted = self._order_executor.submit_spot_hedge(prepared)
            _trace(
                "ORDER",
                "Spot hedge submit returned",
                client_order_id=submitted.intent.client_order_id,
                state=submitted.state,
                cumulative_quantity=submitted.cumulative_quantity,
            )
            return (submitted,)

        if kind is FundingCommandKind.CANCEL_MAKER:
            if session.maker_client_order_id is None:
                raise ValueError("funding session has no maker order")
            _trace(
                "RECOVERY",
                "canceling remaining Perp maker",
                client_order_id=session.maker_client_order_id,
            )
            canceled = self._execution.cancel(session.maker_client_order_id)
            _trace(
                "ORDER",
                "Perp maker cancel returned",
                client_order_id=canceled.intent.client_order_id,
                state=canceled.state,
                cumulative_quantity=canceled.cumulative_quantity,
            )
            return (canceled,)

        if kind is FundingCommandKind.RECONCILE:
            client_order_ids: list[str] = []
            if session.maker_client_order_id is not None:
                client_order_ids.append(session.maker_client_order_id)
            client_order_ids.extend(
                candidate.client_order_id
                for candidate in self._actions.list_actions(session.execution_id)
                if candidate.action_type == FundingCommandKind.SUBMIT_HEDGE.value
                and candidate.client_order_id is not None
            )
            reconciled: list[OrderRecord] = []
            for client_order_id in dict.fromkeys(client_order_ids):
                if self._orders.get(client_order_id) is None:
                    continue
                _trace(
                    "RECOVERY",
                    "reconciling order through REST",
                    client_order_id=client_order_id,
                )
                reconciled.append(self._execution.reconcile(client_order_id))
            return tuple(reconciled)

        if kind is FundingCommandKind.MARK_OPEN:
            _trace(
                "ACTION",
                "marking funding session OPEN",
                execution_id=session.execution_id,
            )
            self._set_session_status(
                session.execution_id,
                FundingSessionStatus.OPEN,
            )
            return ()

        if kind is FundingCommandKind.PAUSE:
            _trace(
                "RECOVERY",
                "pausing funding session",
                execution_id=session.execution_id,
            )
            self._set_session_status(
                session.execution_id,
                FundingSessionStatus.PAUSED,
            )
            return ()

        if kind is FundingCommandKind.RECOVER:
            _trace(
                "RECOVERY",
                "marking funding session RECOVERING",
                execution_id=session.execution_id,
            )
            self._set_session_status(
                session.execution_id,
                FundingSessionStatus.RECOVERING,
            )
            return ()

        raise ValueError(f"unsupported funding action: {kind.value}")

    def _require_session(self, execution_id: str) -> FundingSession:
        session = self._sessions.get_session(execution_id)
        if session is None:
            raise KeyError(f"unknown funding session: {execution_id}")
        return session

    def _fail_hedge_and_stop(
        self,
        failed_action: FundingAction,
        failure_reason: str,
    ) -> tuple[FundingAction, tuple[OrderRecord, ...]]:
        """Atomically pause/fail, then execute the durable stop outbox."""

        session = self._require_session(failed_action.execution_id)
        recovery_actions: list[FundingAction] = []
        if session.maker_client_order_id is not None:
            for kind in (
                FundingCommandKind.CANCEL_MAKER,
                FundingCommandKind.RECONCILE,
            ):
                digest = hashlib.sha256(
                    (
                        f"{failed_action.action_id}:emergency:{kind.value}"
                    ).encode("utf-8")
                ).hexdigest()[:24]
                recovery_actions.append(
                    FundingAction(
                        action_id=f"fra-{digest}",
                        execution_id=session.execution_id,
                        source_event_id=f"failure:{failed_action.action_id}",
                        action_type=kind.value,
                        client_order_id=session.maker_client_order_id,
                    )
                )
        failed, _, persisted_recovery = self._actions.fail_hedge_and_pause(
            failed_action.action_id,
            failure_reason=failure_reason,
            recovery_actions=tuple(recovery_actions),
        )
        _trace(
            "RECOVERY",
            "hedge failed and session paused atomically",
            action_id=failed_action.action_id,
            execution_id=session.execution_id,
            reason=failure_reason,
            recovery_actions=",".join(
                action.action_type for action in persisted_recovery
            ),
        )
        outcomes: list[OrderRecord] = []
        for recovery_action in persisted_recovery:
            _trace(
                "RECOVERY",
                "dispatching durable recovery action",
                action_id=recovery_action.action_id,
                type=recovery_action.action_type,
            )
            outcome = self.dispatch(
                self._actions.get_action(recovery_action.action_id)
                or recovery_action
            )
            outcomes.extend(outcome.orders)
        return failed, tuple(outcomes)

    def _set_session_status(
        self,
        execution_id: str,
        status: FundingSessionStatus,
    ) -> FundingSession:
        current = self._require_session(execution_id)
        if current.status is status:
            return current
        return self._sessions.update_session_status(execution_id, status)


class FundingStrategyWorker:
    """Turn committed order updates into policy actions and dispatch them."""

    def __init__(
        self,
        *,
        committed_event_queue: asyncio.Queue[OrderEvent],
        session_repository: FundingSessionRepository,
        action_repository: FundingActionRepository,
        order_repository: OrderRepository,
        order_event_repository: OrderEventRepository,
        market_data_gateway: MarketDataGateway,
        fill_gateway: OrderFillGateway | None = None,
        dispatcher: FundingActionDispatcher | None = None,
        policy: FundingExecutionPolicy | None = None,
        hedge_calculator: FundingHedgeCalculator | None = None,
        fill_retry_interval_seconds: float = (
            _DEFAULT_FILL_RETRY_INTERVAL_SECONDS
        ),
    ) -> None:
        self._queue = committed_event_queue
        self._sessions = session_repository
        self._actions = action_repository
        self._orders = order_repository
        self._order_events = order_event_repository
        self._market_data = market_data_gateway
        self._fill_gateway = fill_gateway
        self._dispatcher = dispatcher
        self._policy = policy or PerpetualMakerSpotTakerPolicy()
        self._hedge_calculator = hedge_calculator or FundingHedgeCalculator()
        if fill_retry_interval_seconds <= 0:
            raise ValueError("fill_retry_interval_seconds must be positive")
        self._fill_retry_interval_seconds = fill_retry_interval_seconds

    async def run(self) -> None:
        while True:
            if self._fill_gateway is None:
                event = await self._queue.get()
            else:
                try:
                    event = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=self._fill_retry_interval_seconds,
                    )
                except TimeoutError:
                    await asyncio.to_thread(
                        self.retry_incomplete_fill_history
                    )
                    continue
            try:
                await asyncio.to_thread(self.process_event, event)
            finally:
                self._queue.task_done()

    def process_event(
        self,
        event: OrderEvent,
    ) -> tuple[FundingAction, ...]:
        _trace(
            "EVENT",
            "committed order event received",
            event_id=event.event_id or "(generated locally)",
            kind=event.kind,
            client_order_id=event.client_order_id or "(missing)",
            cumulative_quantity=event.cumulative_quantity,
            reconciled_state=event.reconciled_state,
        )
        try:
            actions = self.plan_event(event)
        except Exception as exc:
            _trace(
                "RECOVERY",
                "planning failed",
                event_id=event.event_id or "(generated locally)",
                reason=str(exc),
            )
            actions = self._planning_failure_actions(event, exc)
            if not actions:
                raise
            if self._dispatcher is not None:
                for action in actions:
                    self._dispatcher.dispatch(action)
            return actions
        if self._dispatcher is None or not actions:
            return actions

        pending = list(actions)
        cascade_count = 0
        while pending:
            cascade_count += 1
            if cascade_count > _MAX_DISPATCH_CASCADE:
                raise RuntimeError("funding action cascade exceeded safety limit")
            action = pending.pop(0)
            outcome = self._dispatcher.dispatch(action)
            for order in outcome.orders:
                synthetic = self._event_from_dispatch(outcome.action, order)
                _trace(
                    "EVENT",
                    "planning from dispatch result",
                    source_action_id=outcome.action.action_id,
                    client_order_id=order.intent.client_order_id,
                    state=order.state,
                )
                pending.extend(self.plan_event(synthetic))
        return actions

    def _planning_failure_actions(
        self,
        event: OrderEvent,
        exc: Exception,
    ) -> tuple[FundingAction, ...]:
        """Durably stop entry when an active hedge decision cannot be made."""

        if not event.client_order_id:
            return ()
        source_order = self._orders.get(event.client_order_id)
        if source_order is None:
            return ()
        session = self._sessions.get_session(source_order.intent.execution_id)
        if session is None or session.status not in {
            FundingSessionStatus.ENTERING,
            FundingSessionStatus.HEDGING,
        }:
            return ()
        try:
            maker = self._maker_order(session)
        except Exception:
            return ()

        source_event_id = (
            event.event_id or self._fallback_event_id(event)
        ) + ":planning-failure"
        commands: list[FundingPolicyCommand] = [
            FundingPolicyCommand(
                FundingCommandKind.PAUSE,
                reason=f"funding decision failed: {exc}",
            )
        ]
        if not maker.is_terminal and maker.leaves_quantity > ZERO:
            commands.append(
                FundingPolicyCommand(
                    FundingCommandKind.CANCEL_MAKER,
                    reason="stop maker after funding decision failure",
                )
            )
        commands.append(
            FundingPolicyCommand(
                FundingCommandKind.RECONCILE,
                reason="inspect orders after funding decision failure",
            )
        )
        actions = tuple(
            self._persist_command(session, command, source_event_id)
            for command in commands
        )
        # Pause locally before any cancel/reconcile response can create a
        # synthetic follow-up decision.
        self._sessions.update_session_status(
            session.execution_id,
            FundingSessionStatus.PAUSED,
        )
        _trace(
            "RECOVERY",
            "planning failure persisted stop sequence",
            execution_id=session.execution_id,
            reason=str(exc),
            actions=",".join(action.action_type for action in actions),
        )
        LOGGER.exception(
            "funding decision failed; session %s paused",
            session.execution_id,
            exc_info=exc,
        )
        return actions

    def plan_event(
        self,
        event: OrderEvent,
    ) -> tuple[FundingAction, ...]:
        if not event.client_order_id:
            _trace(
                "WAIT",
                "event ignored",
                reason="missing client_order_id",
            )
            return ()
        source_order = self._orders.get(event.client_order_id)
        if source_order is None:
            _trace(
                "WAIT",
                "event ignored",
                client_order_id=event.client_order_id,
                reason="order is not owned by this process",
            )
            return ()
        session = self._sessions.get_session(source_order.intent.execution_id)
        if session is None:
            _trace(
                "WAIT",
                "event ignored",
                client_order_id=event.client_order_id,
                reason="no funding session for order",
            )
            return ()
        if session.status not in {
            FundingSessionStatus.ENTERING,
            FundingSessionStatus.HEDGING,
        }:
            _trace(
                "WAIT",
                "event ignored",
                execution_id=session.execution_id,
                status=session.status,
                reason="funding session is not active",
            )
            return ()
        role = self._order_role(session, source_order)
        if role is None:
            _trace(
                "WAIT",
                "event ignored",
                execution_id=session.execution_id,
                client_order_id=event.client_order_id,
                reason="order has no maker or hedge role",
            )
            return ()
        _trace(
            "EVENT",
            "funding order identified",
            execution_id=session.execution_id,
            role=role,
            kind=event.kind,
            client_order_id=event.client_order_id,
        )
        maker = self._maker_order(session)
        if self._fill_gateway is not None:
            # A terminal MARKET REST response can arrive before its trade
            # commission is visible. Do not mark the session OPEN until either
            # WebSocket or REST fill history accounts for every Spot execution.
            # This guard also covers a maker startup event after a process or
            # WebSocket reconnect.
            self.reconcile_fills(session.execution_id)
            if not self._hedge_fill_history_is_complete(session):
                _trace(
                    "WAIT",
                    "decision deferred",
                    execution_id=session.execution_id,
                    reason="Spot fill quantity or commission history is incomplete",
                )
                return ()

        spot_instrument = InstrumentId("binance", "MARGIN", session.symbol)
        rules = self._market_data.get_symbol_rules(spot_instrument)
        order_book = self._market_data.get_order_book(spot_instrument, depth=20)
        if order_book.best_ask is None:
            raise RuntimeError("Spot hedge requires a visible best ask")
        reference_price = order_book.best_ask.price

        spot_confirmed, spot_base_commission, spot_pending = (
            self._spot_hedge_progress(session, rules.base_asset)
        )
        _trace(
            "CALC",
            "hedge inputs",
            execution_id=session.execution_id,
            perp_filled=maker.cumulative_quantity,
            spot_confirmed=spot_confirmed,
            spot_base_commission=spot_base_commission,
            spot_pending=spot_pending,
            reference_price=reference_price,
            quantity_step=rules.effective_market_quantity_increment,
            min_quantity=rules.effective_market_min_quantity,
            min_notional=rules.min_notional,
            delta_tolerance=session.delta_tolerance,
        )
        hedge = self._hedge_calculator.calculate(
            HedgeCalculationInput(
                perpetual_filled_quantity=maker.cumulative_quantity,
                spot_confirmed_quantity=spot_confirmed,
                spot_base_commission=spot_base_commission,
                spot_pending_quantity=spot_pending,
                reference_price=reference_price,
                quantity_step=rules.effective_market_quantity_increment,
                min_quantity=rules.effective_market_min_quantity,
                min_notional=rules.min_notional,
                delta_tolerance=session.delta_tolerance,
            )
        )
        _trace(
            "CALC",
            "hedge result",
            target_spot=hedge.target_spot_quantity,
            spot_net=hedge.spot_net_quantity,
            net_delta=hedge.net_delta,
            uncovered=hedge.uncovered_quantity,
            tradable=hedge.tradable_quantity,
            dust=hedge.dust_quantity,
            pending=hedge.pending_quantity,
            within_tolerance=hedge.within_tolerance,
        )
        source_event_id = event.event_id or self._fallback_event_id(event)
        context = FundingPolicyContext(
            event_role=role,
            event_kind=event.kind,
            maker_terminal=maker.is_terminal,
            maker_remaining_quantity=maker.leaves_quantity,
            hedge=hedge,
            reference_price=reference_price,
            max_unhedged_notional=session.capital,
            session_status=session.status.value,
            source_event_id=source_event_id,
        )
        commands = self._policy.decide(context)
        for command in commands:
            _trace(
                "DECISION",
                "policy command",
                execution_id=session.execution_id,
                command=command.kind,
                quantity=command.quantity,
                reason=command.reason or "(no reason provided)",
            )
        if not commands:
            _trace(
                "WAIT",
                "no policy action",
                execution_id=session.execution_id,
                reason=self._no_action_reason(context),
            )
        planned = tuple(
            self._persist_command(session, command, source_event_id)
            for command in commands
        )
        if (
            any(
                action.action_type == FundingCommandKind.SUBMIT_HEDGE.value
                for action in planned
            )
            and session.status is FundingSessionStatus.ENTERING
        ):
            self._sessions.update_session_status(
                session.execution_id,
                FundingSessionStatus.HEDGING,
            )
        return planned

    def recover_pending_actions(
        self,
        execution_id: str | None = None,
    ) -> tuple[FundingDispatchOutcome, ...]:
        if self._dispatcher is None:
            _trace(
                "WAIT",
                "pending action recovery skipped",
                reason="dispatcher is not configured",
            )
            return ()
        _trace(
            "RECOVERY",
            "recovering persisted pending actions",
            execution_id=execution_id or "all",
        )
        return self._dispatcher.dispatch_pending(execution_id)

    def retry_incomplete_fill_history(
        self,
    ) -> tuple[FundingAction, ...]:
        """Revisit terminal Spot fills whose fee history was not visible yet."""

        planned: list[FundingAction] = []
        if self._fill_gateway is None:
            return ()
        for session in self._sessions.list_active_sessions():
            if session.status not in {
                FundingSessionStatus.ENTERING,
                FundingSessionStatus.HEDGING,
            }:
                continue
            if self._hedge_fill_history_is_complete(session):
                continue
            _trace(
                "FILL",
                "retrying incomplete Spot fill history",
                execution_id=session.execution_id,
                retry_interval_seconds=self._fill_retry_interval_seconds,
            )
            maker = self._maker_order(session)
            planned.extend(
                self.process_event(
                    OrderEvent(
                        kind=OrderEventKind.RECONCILED,
                        client_order_id=maker.intent.client_order_id,
                        event_id=(
                            "fill-history-retry:"
                            f"{session.execution_id}:"
                            f"{maker.state.value}:"
                            f"{maker.cumulative_quantity}"
                        ),
                        cumulative_quantity=maker.cumulative_quantity,
                        average_price=maker.average_price,
                        exchange_order_id=maker.exchange_order_id,
                        reconciled_state=maker.state,
                        reason="retry incomplete Spot fill history",
                    )
                )
            )
        return tuple(planned)

    def reconcile_fills(
        self,
        execution_id: str,
    ) -> tuple[OrderEvent, ...]:
        """Backfill missing trade fees after WebSocket-gap reconciliation."""

        if self._fill_gateway is None:
            return ()
        session = self._sessions.get_session(execution_id)
        if session is None:
            raise KeyError(f"unknown funding session: {execution_id}")

        appended: list[OrderEvent] = []
        for action in self._actions.list_actions(execution_id):
            if action.action_type != FundingCommandKind.SUBMIT_HEDGE.value:
                continue
            if action.client_order_id is None:
                continue
            order = self._orders.get(action.client_order_id)
            if order is None or order.exchange_order_id is None:
                continue
            existing_trade_ids = {
                event.trade_id
                for event in self._order_events.list_for_order(
                    action.client_order_id
                )
                if event.kind is OrderEventKind.TRADE
                and event.trade_id is not None
                and event.commission is not None
                and event.commission_asset is not None
            }
            fills = self._fill_gateway.list_order_fills(
                order.intent.instrument,
                order.exchange_order_id,
            )
            if fills or not self._fill_history_is_complete(order):
                _trace(
                    "FILL",
                    "REST Spot fills fetched",
                    client_order_id=action.client_order_id,
                    exchange_order_id=order.exchange_order_id,
                    fill_count=len(fills),
                    cumulative_quantity=order.cumulative_quantity,
                )
            for fill in fills:
                if fill.trade_id in existing_trade_ids:
                    continue
                event = OrderEvent(
                    kind=OrderEventKind.TRADE,
                    client_order_id=action.client_order_id,
                    event_id=(
                        "rest-fill:"
                        f"{fill.instrument.venue}:"
                        f"{fill.instrument.market}:"
                        f"{fill.instrument.symbol}:"
                        f"{fill.exchange_order_id}:"
                        f"{fill.trade_id}"
                    ),
                    last_executed_quantity=fill.quantity,
                    last_executed_price=fill.price,
                    trade_id=fill.trade_id,
                    commission=fill.commission,
                    commission_asset=fill.commission_asset,
                    exchange_order_id=fill.exchange_order_id,
                    occurred_at=fill.occurred_at,
                )
                if not self._order_events.contains(event.event_id or ""):
                    self._order_events.append(event)
                    appended.append(event)
                    _trace(
                        "FILL",
                        "REST fill backfilled",
                        client_order_id=action.client_order_id,
                        trade_id=fill.trade_id,
                        quantity=fill.quantity,
                        commission=fill.commission,
                        commission_asset=fill.commission_asset,
                    )
                existing_trade_ids.add(fill.trade_id)
        return tuple(appended)

    def _fill_history_is_complete(self, order: OrderRecord) -> bool:
        if order.cumulative_quantity <= ZERO:
            return True
        fills: dict[str, tuple[Decimal, bool]] = {}
        accounted_quantity = ZERO
        for event in self._order_events.list_for_order(
            order.intent.client_order_id
        ):
            if (
                event.kind is not OrderEventKind.TRADE
                or event.last_executed_quantity is None
            ):
                continue
            identity = event.trade_id or event.event_id
            if identity is None:
                continue
            previous_quantity, previous_has_fee = fills.get(
                identity,
                (ZERO, False),
            )
            fills[identity] = (
                max(previous_quantity, event.last_executed_quantity),
                previous_has_fee
                or (
                    event.commission is not None
                    and event.commission_asset is not None
                ),
            )
        for quantity, has_fee in fills.values():
            if not has_fee:
                return False
            accounted_quantity += quantity
        return accounted_quantity >= order.cumulative_quantity

    def _hedge_fill_history_is_complete(
        self,
        session: FundingSession,
    ) -> bool:
        for action in self._actions.list_actions(session.execution_id):
            if (
                action.action_type
                != FundingCommandKind.SUBMIT_HEDGE.value
                or action.client_order_id is None
            ):
                continue
            order = self._orders.get(action.client_order_id)
            if (
                order is not None
                and order.cumulative_quantity > ZERO
                and not self._fill_history_is_complete(order)
            ):
                return False
        return True

    def _spot_hedge_progress(
        self,
        session: FundingSession,
        base_asset: str,
    ) -> tuple[Decimal, Decimal, Decimal]:
        confirmed = ZERO
        base_commission = ZERO
        pending = ZERO
        for action in self._actions.list_actions(session.execution_id):
            if action.action_type != FundingCommandKind.SUBMIT_HEDGE.value:
                continue
            if action.client_order_id is None:
                continue
            order = self._orders.get(action.client_order_id)
            if order is None:
                if (
                    action.status
                    in {
                        FundingActionStatus.PENDING,
                        FundingActionStatus.IN_PROGRESS,
                    }
                    and action.requested_quantity is not None
                ):
                    pending += action.requested_quantity
                continue

            confirmed += order.cumulative_quantity
            if not order.is_terminal:
                pending += order.leaves_quantity
            seen_commission_fills: set[str] = set()
            for fill_event in self._order_events.list_for_order(
                action.client_order_id
            ):
                identity = fill_event.trade_id or fill_event.event_id
                if (
                    fill_event.kind is OrderEventKind.TRADE
                    and fill_event.commission is not None
                    and fill_event.commission_asset is not None
                    and fill_event.commission_asset.upper()
                    == base_asset.upper()
                    and identity is not None
                    and identity not in seen_commission_fills
                ):
                    base_commission += fill_event.commission
                    seen_commission_fills.add(identity)
        return confirmed, base_commission, pending

    def _maker_order(self, session: FundingSession) -> OrderRecord:
        if session.maker_client_order_id is None:
            raise RuntimeError("funding session has no maker order")
        maker = self._orders.get(session.maker_client_order_id)
        if maker is None:
            raise RuntimeError("funding session maker order is not persisted")
        return maker

    def _order_role(
        self,
        session: FundingSession,
        order: OrderRecord,
    ) -> FundingOrderRole | None:
        if order.intent.client_order_id == session.maker_client_order_id:
            return FundingOrderRole.MAKER
        if any(
            action.action_type == FundingCommandKind.SUBMIT_HEDGE.value
            and action.client_order_id == order.intent.client_order_id
            for action in self._actions.list_actions(session.execution_id)
        ):
            return FundingOrderRole.HEDGE
        return None

    def _persist_command(
        self,
        session: FundingSession,
        command: FundingPolicyCommand,
        source_event_id: str,
    ) -> FundingAction:
        quantity_key = (
            format(command.quantity, "f")
            if command.quantity is not None
            else ""
        )
        digest = hashlib.sha256(
            (
                f"{session.execution_id}:{source_event_id}:"
                f"{command.kind.value}:{quantity_key}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        action_id = f"fra-{digest}"
        client_order_id = (
            f"frh-{digest}"
            if command.kind is FundingCommandKind.SUBMIT_HEDGE
            else session.maker_client_order_id
        )
        action = FundingAction(
            action_id=action_id,
            execution_id=session.execution_id,
            source_event_id=source_event_id,
            action_type=command.kind.value,
            client_order_id=client_order_id,
            requested_quantity=command.quantity,
        )
        existing = self._actions.get_action(action_id)
        self._actions.save_action(action)
        persisted = self._actions.get_action(action_id) or action
        _trace(
            "ACTION",
            "durable action reused" if existing is not None else "durable action persisted",
            action_id=persisted.action_id,
            type=persisted.action_type,
            status=persisted.status,
            client_order_id=persisted.client_order_id,
            quantity=persisted.requested_quantity,
            source_event_id=source_event_id,
        )
        return persisted

    @staticmethod
    def _no_action_reason(context: FundingPolicyContext) -> str:
        if context.hedge.pending_quantity > ZERO:
            return "an existing Spot hedge is still pending"
        if context.hedge.uncovered_quantity == ZERO:
            return "no confirmed unhedged Perp quantity"
        if context.hedge.tradable_quantity == ZERO:
            return "residual quantity is below Spot trading minimums"
        return "event does not require an action under the current policy"

    @staticmethod
    def _fallback_event_id(event: OrderEvent) -> str:
        digest = hashlib.sha256(
            (
                f"{event.client_order_id}:{event.kind.value}:"
                f"{event.cumulative_quantity}:{event.reconciled_state}:"
                f"{event.occurred_at.isoformat()}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        return f"local-{digest}"

    @staticmethod
    def _event_from_dispatch(
        action: FundingAction,
        order: OrderRecord,
    ) -> OrderEvent:
        if order.state is OrderState.REJECTED:
            kind = OrderEventKind.REJECTED
        elif order.state is OrderState.CANCELED:
            kind = OrderEventKind.CANCELED
        elif order.state is OrderState.EXPIRED:
            kind = OrderEventKind.EXPIRED
        elif order.state is OrderState.UNKNOWN:
            kind = OrderEventKind.REQUEST_TIMED_OUT
        else:
            kind = OrderEventKind.RECONCILED
        return OrderEvent(
            kind=kind,
            client_order_id=order.intent.client_order_id,
            event_id=(
                f"dispatch:{action.action_id}:{order.state.value}:"
                f"{order.cumulative_quantity}"
            ),
            cumulative_quantity=order.cumulative_quantity,
            average_price=order.average_price,
            exchange_order_id=order.exchange_order_id,
            reconciled_state=order.state,
            reason=order.rejection_reason,
        )
