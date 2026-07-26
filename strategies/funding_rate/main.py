"""Orchestrate the complete Funding Rate entry and hedge strategy.

The default mode performs a fresh public scan and previews the selected
perpetual maker.  Live execution additionally requires ``--submit``, an exact
``--confirm-symbol`` match, and ``CHOXR_LIVE_TRADING=true``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from dotenv import load_dotenv

from adapters.persistence import SqliteFundingRepository
from app.container import ApplicationContainer, build_binance_container
from app.runtime import ApplicationRuntime
from app.settings import Settings
from engine.domain.instrument import InstrumentId
from engine.domain.order import OrderRecord, OrderState
from engine.domain.order_event import OrderEvent, OrderEventKind

from .monitor import (
    DEFAULT_ORDER_PLAN_PATH,
    build_funding_rate_monitor,
    render_console_report,
)
from .order import (
    DEFAULT_ORDER_DATABASE_PATH,
    FundingOrderExecutor,
    FundingOrderPlanError,
    PreparedPerpetualMaker,
    ReadyFundingOrderPlan,
    build_funding_order_executor,
    load_funding_order_plan,
    prepared_order_payload,
    validate_plan_settings,
)
from .session import (
    FundingSession,
    FundingSessionStatus,
)
from .worker import (
    FundingActionDispatcher,
    FundingStrategyWorker,
)


def _operator_log(component: str, event: str, **fields: object) -> None:
    """Emit one stable, immediately visible operator-facing status line."""

    details = " ".join(
        f"{name}={value}"
        for name, value in fields.items()
        if value is not None
    )
    suffix = f" {details}" if details else ""
    print(f"[FUNDING][{component}] {event}{suffix}", flush=True)


@dataclass(frozen=True)
class FundingSessionBaseline:
    starting_spot_quantity: Decimal
    delta_tolerance: Decimal


@dataclass(frozen=True)
class FundingRateStrategyApplication:
    container: ApplicationContainer
    runtime: ApplicationRuntime
    worker: FundingStrategyWorker
    session: FundingSession | None
    plan: ReadyFundingOrderPlan | None = None
    prepared_maker: PreparedPerpetualMaker | None = None
    order_executor: FundingOrderExecutor | None = None
    session_baseline: FundingSessionBaseline | None = None

    async def run(self) -> None:
        execution_id = (
            self.session.execution_id
            if self.session is not None
            else self.plan.execution_id
            if self.plan is not None
            else None
        )
        symbol = (
            self.session.symbol
            if self.session is not None
            else self.plan.symbol
            if self.plan is not None
            else None
        )
        _operator_log(
            "APPLICATION",
            "START",
            execution_id=execution_id,
            symbol=symbol,
            session_status=(
                self.session.status.value
                if self.session is not None
                else "PENDING_MAKER_SUBMIT"
            ),
        )
        _operator_log("PREFLIGHT", "BEGIN")
        try:
            preflight = self.runtime.preflight()
        except Exception as exc:
            _operator_log(
                "PREFLIGHT",
                "FAILED",
                error_type=type(exc).__name__,
            )
            raise
        _operator_log(
            "PREFLIGHT",
            "PASSED",
            account_mode=preflight.account_mode.value,
            one_way_mode=preflight.one_way_mode,
        )
        _operator_log("RUNTIME", "TASK_STARTING")
        runtime_task = asyncio.create_task(
            self.runtime.consume_order_events(),
            name="funding-runtime",
        )
        _operator_log("RUNTIME", "WAITING_FOR_SYNCHRONIZATION")
        ready_task = asyncio.create_task(
            self.runtime.wait_until_synchronized(),
            name="funding-runtime-ready",
        )
        worker_task: asyncio.Task[None] | None = None
        try:
            done, _ = await asyncio.wait(
                {runtime_task, ready_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if runtime_task in done:
                exception = runtime_task.exception()
                if exception is not None:
                    raise exception
                raise RuntimeError(
                    "order runtime stopped before synchronization"
                )
            await ready_task
            _operator_log("RUNTIME", "SYNCHRONIZED")

            session = await self._ensure_session_after_synchronization()

            # Resume persisted outbox work only after websocket-gap
            # reconciliation has established current exchange truth.
            _operator_log(
                "FILL_RECONCILIATION",
                "BEGIN",
                execution_id=session.execution_id,
            )
            reconciled_fills = await asyncio.to_thread(
                self.worker.reconcile_fills,
                session.execution_id,
            )
            _operator_log(
                "FILL_RECONCILIATION",
                "COMPLETE",
                recovered_events=len(reconciled_fills),
            )
            _operator_log(
                "PENDING_RECOVERY",
                "BEGIN",
                execution_id=session.execution_id,
            )
            recovery_outcomes = await asyncio.to_thread(
                self.worker.recover_pending_actions,
                session.execution_id,
            )
            _operator_log(
                "PENDING_RECOVERY",
                "COMPLETE",
                dispatched_actions=len(recovery_outcomes),
            )
            maker = self.container.order_repository.get(
                session.maker_client_order_id or ""
            )
            if maker is None:
                _operator_log("MAKER_SNAPSHOT", "MISSING")
                raise RuntimeError("funding maker order disappeared after startup")
            _operator_log(
                "MAKER_SNAPSHOT",
                "LOADED",
                client_order_id=maker.intent.client_order_id,
                state=maker.state.value,
                cumulative_quantity=maker.cumulative_quantity,
                leaves_quantity=maker.leaves_quantity,
            )
            _operator_log("MAKER_SNAPSHOT", "PROCESSING")
            startup_actions = await asyncio.to_thread(
                self.worker.process_event,
                _startup_event(maker),
            )
            _operator_log(
                "MAKER_SNAPSHOT",
                "PROCESSED",
                planned_actions=len(startup_actions),
            )
            _operator_log("WORKER", "STARTING")
            worker_task = asyncio.create_task(
                self.worker.run(),
                name="funding-strategy-worker",
            )
            _operator_log("WORKER", "STARTED")

            done, _ = await asyncio.wait(
                {runtime_task, worker_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                exception = task.exception()
                if exception is not None:
                    raise exception
            if worker_task in done and not runtime_task.done():
                raise RuntimeError("funding strategy worker stopped unexpectedly")
        except asyncio.CancelledError:
            _operator_log("APPLICATION", "CANCELLED")
            raise
        except Exception as exc:
            _operator_log(
                "APPLICATION",
                "ERROR",
                error_type=type(exc).__name__,
            )
            raise
        finally:
            _operator_log("APPLICATION", "SHUTDOWN_BEGIN")
            self.container.order_event_stream.request_stop()
            for task in (ready_task, worker_task, runtime_task):
                if task is not None and not task.done():
                    task.cancel()
            await asyncio.gather(
                *(
                    task
                    for task in (ready_task, worker_task, runtime_task)
                    if task is not None
                ),
                return_exceptions=True,
            )
            if worker_task is not None:
                _operator_log("WORKER", "STOPPED")
            _operator_log("APPLICATION", "STOPPED")

    async def _ensure_session_after_synchronization(self) -> FundingSession:
        """Resume an existing session or submit one maker after WS sync."""

        if self.session is not None:
            _operator_log(
                "SESSION",
                "RESUMING",
                execution_id=self.session.execution_id,
                status=self.session.status.value,
            )
            return self.session
        if (
            self.plan is None
            or self.prepared_maker is None
            or self.order_executor is None
        ):
            raise RuntimeError("new funding entry is missing its prepared maker")

        # A previous process can have submitted the deterministic client order
        # ID and crashed before saving the Funding session.  Reuse it instead
        # of ever submitting a duplicate.
        maker = self.container.order_repository.get(
            self.plan.perpetual_client_order_id
        )
        if maker is None:
            _operator_log(
                "PERPETUAL_MAKER",
                "SUBMIT_BEGIN",
                client_order_id=self.plan.perpetual_client_order_id,
                symbol=self.plan.symbol,
                quantity=self.prepared_maker.intent.quantity,
                price=self.prepared_maker.intent.price,
            )
            maker = await asyncio.to_thread(
                self.order_executor.submit_perpetual_maker,
                self.prepared_maker,
            )
            _operator_log(
                "PERPETUAL_MAKER",
                "SUBMITTED",
                client_order_id=maker.intent.client_order_id,
                exchange_order_id=maker.exchange_order_id,
                state=maker.state.value,
            )
        else:
            _operator_log(
                "PERPETUAL_MAKER",
                "REUSING_PERSISTED",
                client_order_id=maker.intent.client_order_id,
                state=maker.state.value,
            )

        session = await asyncio.to_thread(
            _create_or_load_session,
            self.container,
            self.plan,
            maker,
            baseline=self.session_baseline,
        )
        _operator_log(
            "SESSION",
            "READY",
            execution_id=session.execution_id,
            status=session.status.value,
        )
        return session


def build_funding_rate_strategy_application(
    *,
    settings: Settings,
    plan: ReadyFundingOrderPlan | None,
    database_path: str | Path,
    confirmed_symbol: str,
    execution_id: str | None = None,
    submit_missing_maker: bool = False,
) -> FundingRateStrategyApplication:
    settings.require_live_trading()
    normalized_confirmation = confirmed_symbol.strip().upper()
    if not normalized_confirmation:
        raise RuntimeError("--confirm-symbol cannot be empty")
    container = build_binance_container(
        settings,
        database_path=database_path,
    )
    order_executor = build_funding_order_executor(container)

    if plan is None:
        session_baseline = None
        session = _select_active_session(
            container.funding_repository.list_active_sessions(),
            confirmed_symbol=normalized_confirmation,
            execution_id=execution_id,
        )
        expected_symbol = session.symbol.upper()
        maker = container.order_repository.get(
            session.maker_client_order_id or ""
        )
        if maker is None:
            raise FundingOrderPlanError(
                "persisted funding session has no matching perpetual maker"
            )
        if maker.intent.execution_id != session.execution_id:
            raise FundingOrderPlanError(
                "persisted maker execution does not match the funding session"
            )
    else:
        expected_symbol = plan.symbol.upper()
        if normalized_confirmation != expected_symbol:
            raise RuntimeError(
                f"live hedge worker requires --confirm-symbol {expected_symbol}"
            )
        if execution_id is not None and execution_id != plan.execution_id:
            raise FundingOrderPlanError(
                "--execution-id does not match the order plan"
            )
        validate_plan_settings(plan, settings)
        maker = container.order_repository.get(plan.perpetual_client_order_id)
        if maker is None:
            if not submit_missing_maker:
                raise FundingOrderPlanError(
                    "persisted perpetual maker was not found"
                )
            session = None
            # Validate Spot filters and capture the unhedged starting balance
            # before any Perp mutation.  No session-setup market-data failure
            # is therefore allowed to occur after maker submission.
            session_baseline = _load_session_baseline(container, plan)
        else:
            if maker.intent.execution_id != plan.execution_id:
                raise FundingOrderPlanError(
                    "persisted maker execution does not match the order plan"
                )
            session = _create_or_load_session(
                container,
                plan,
                maker,
            )
            session_baseline = None

    if normalized_confirmation != expected_symbol:
        raise RuntimeError(
            f"live hedge worker requires --confirm-symbol {expected_symbol}"
        )

    prepared_maker = None
    if plan is not None and session is None:
        # Prove the complete Spot leg is currently affordable before allowing
        # any Perp mutation.  The eventual worker still revalidates each exact
        # hedge immediately before submitting it.
        _operator_log(
            "SPOT_CAPACITY",
            "CHECK_BEGIN",
            symbol=plan.symbol,
            quantity=plan.spot_quantity,
        )
        order_executor.prepare_spot_taker(
            plan,
            quantity=plan.spot_quantity,
        )
        _operator_log("SPOT_CAPACITY", "CHECK_PASSED")
        prepared_maker = order_executor.prepare_perpetual_maker(plan)
    committed_events: asyncio.Queue[OrderEvent] = asyncio.Queue()
    runtime = ApplicationRuntime(
        container,
        committed_event_queue=committed_events,
    )
    dispatcher = FundingActionDispatcher(
        session_repository=container.funding_repository,
        action_repository=container.funding_repository,
        order_repository=container.order_repository,
        order_executor=order_executor,
        execution_service=container.execution_service,
    )
    worker = FundingStrategyWorker(
        committed_event_queue=committed_events,
        session_repository=container.funding_repository,
        action_repository=container.funding_repository,
        order_repository=container.order_repository,
        order_event_repository=container.order_event_repository,
        market_data_gateway=container.market_data_gateway,
        fill_gateway=getattr(container, "fill_gateway", None),
        dispatcher=dispatcher,
    )
    return FundingRateStrategyApplication(
        container=container,
        runtime=runtime,
        worker=worker,
        session=session,
        plan=plan,
        prepared_maker=prepared_maker,
        order_executor=order_executor,
        session_baseline=session_baseline,
    )


def _load_session_baseline(
    container: ApplicationContainer,
    plan: ReadyFundingOrderPlan,
) -> FundingSessionBaseline:
    spot_instrument = InstrumentId(
        "binance",
        "MARGIN",
        plan.symbol.upper(),
    )
    spot_rules = container.market_data_gateway.get_symbol_rules(
        spot_instrument
    )
    account = container.account_gateway.get_account_snapshot()
    starting_balance = account.find_balance(spot_rules.base_asset)
    return FundingSessionBaseline(
        starting_spot_quantity=(
            starting_balance.net if starting_balance is not None else 0
        ),
        delta_tolerance=spot_rules.effective_market_quantity_increment,
    )


def _create_or_load_session(
    container: ApplicationContainer,
    plan: ReadyFundingOrderPlan,
    maker: OrderRecord,
    *,
    baseline: FundingSessionBaseline | None = None,
) -> FundingSession:
    existing_session = container.funding_repository.get_session(
        plan.execution_id
    )
    if existing_session is not None:
        if (
            existing_session.symbol != plan.symbol.upper()
            or existing_session.maker_client_order_id
            != maker.intent.client_order_id
        ):
            raise FundingOrderPlanError(
                "persisted funding session does not match the order plan"
            )
        return existing_session

    resolved_baseline = baseline or _load_session_baseline(container, plan)
    session = FundingSession(
        execution_id=plan.execution_id,
        symbol=plan.symbol.upper(),
        policy_name="PERPETUAL_MAKER_SPOT_TAKER",
        status=_initial_session_status(maker),
        target_quantity=maker.intent.quantity,
        capital=plan.capital,
        maker_client_order_id=maker.intent.client_order_id,
        starting_spot_quantity=resolved_baseline.starting_spot_quantity,
        delta_tolerance=resolved_baseline.delta_tolerance,
    )
    container.funding_repository.save_session(session)
    return session


def _initial_session_status(maker: OrderRecord) -> FundingSessionStatus:
    if maker.state is OrderState.REJECTED and maker.cumulative_quantity == 0:
        return FundingSessionStatus.FAILED
    if maker.is_terminal and maker.cumulative_quantity == 0:
        return FundingSessionStatus.CLOSED
    if maker.cumulative_quantity > 0:
        return FundingSessionStatus.HEDGING
    return FundingSessionStatus.ENTERING


def _select_active_session(
    sessions: Sequence[FundingSession],
    *,
    confirmed_symbol: str,
    execution_id: str | None,
) -> FundingSession:
    candidates = tuple(
        session
        for session in sessions
        if session.symbol.upper() == confirmed_symbol
        and (
            execution_id is None
            or session.execution_id == execution_id
        )
    )
    if not candidates:
        suffix = (
            f" for execution {execution_id}"
            if execution_id is not None
            else ""
        )
        raise FundingOrderPlanError(
            f"no active {confirmed_symbol} funding session{suffix}"
        )
    if len(candidates) > 1:
        raise FundingOrderPlanError(
            "multiple active funding sessions match; pass --execution-id"
        )
    return candidates[0]


def _startup_event(maker: OrderRecord) -> OrderEvent:
    return OrderEvent(
        kind=OrderEventKind.RECONCILED,
        client_order_id=maker.intent.client_order_id,
        event_id=(
            f"funding-startup:{maker.intent.client_order_id}:"
            f"{maker.state.value}:{maker.cumulative_quantity}"
        ),
        cumulative_quantity=maker.cumulative_quantity,
        average_price=maker.average_price,
        exchange_order_id=maker.exchange_order_id,
        reconciled_state=maker.state,
        reason=maker.rejection_reason,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-path",
        type=Path,
        default=DEFAULT_ORDER_PLAN_PATH,
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=DEFAULT_ORDER_DATABASE_PATH,
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help=(
            "enable live maker submission and automatic Spot hedging; "
            "also requires CHOXR_LIVE_TRADING=true and --confirm-symbol"
        ),
    )
    parser.add_argument("--confirm-symbol")
    parser.add_argument("--execution-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    confirmed_symbol = (args.confirm_symbol or "").strip().upper()
    _operator_log(
        "PROCESS",
        "START",
        mode="LIVE" if args.submit else "PREVIEW",
        symbol=confirmed_symbol or None,
        execution_id=args.execution_id,
        database_path=args.database_path,
    )
    try:
        load_dotenv()
        _operator_log("PROCESS", "ENVIRONMENT_LOADED")
        settings = Settings.from_environment()
        _operator_log("PROCESS", "SETTINGS_VALIDATED")
        if args.submit and not confirmed_symbol:
            raise RuntimeError(
                "--confirm-symbol is required when --submit is enabled"
            )
        _operator_log("PROCESS", "ACTIVE_SESSION_LOOKUP_BEGIN")
        active_sessions = SqliteFundingRepository(
            args.database_path
        ).list_active_sessions()
        matching_sessions = tuple(
            session
            for session in active_sessions
            if (
                not confirmed_symbol
                or session.symbol.upper() == confirmed_symbol
            )
            and (
                args.execution_id is None
                or session.execution_id == args.execution_id
            )
        )
        _operator_log(
            "PROCESS",
            "ACTIVE_SESSION_LOOKUP_COMPLETE",
            matches=len(matching_sessions),
        )
        if len(matching_sessions) > 1:
            raise FundingOrderPlanError(
                "multiple active funding sessions match; pass "
                "--execution-id and --confirm-symbol"
            )
        if matching_sessions:
            active_session = matching_sessions[0]
            _operator_log(
                "PROCESS",
                "USING_PERSISTED_SESSION",
                execution_id=active_session.execution_id,
                symbol=active_session.symbol,
                status=active_session.status.value,
            )
            if not args.submit:
                print(
                    json.dumps(
                        {
                            "mode": "READ_ONLY",
                            "action": "ACTIVE_SESSION_FOUND",
                            "execution_id": active_session.execution_id,
                            "symbol": active_session.symbol,
                            "status": active_session.status.value,
                            "next_command": (
                                "python3 -m strategies.funding_rate.main "
                                "--submit --confirm-symbol "
                                f"{active_session.symbol}"
                            ),
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                _operator_log("PROCESS", "STOPPED", exit_code=0)
                return 0
            application = build_funding_rate_strategy_application(
                settings=settings,
                plan=None,
                database_path=args.database_path,
                confirmed_symbol=confirmed_symbol,
                execution_id=args.execution_id,
            )
        else:
            if args.execution_id is not None:
                raise FundingOrderPlanError(
                    f"no active funding session for execution "
                    f"{args.execution_id}"
                )
            _operator_log("SCANNER", "STARTING")
            monitor = build_funding_rate_monitor(
                settings,
                order_plan_path=args.plan_path,
            )
            report = monitor.scan_once()
            _operator_log(
                "SCANNER",
                "COMPLETE",
                scanned=report.scanned_symbol_count,
                candidates=len(report.candidates),
            )
            print(render_console_report(report), flush=True)
            plan_path = monitor.save_order_plan(report)
            _operator_log(
                "SCANNER",
                "ORDER_PLAN_SAVED",
                plan_path=plan_path,
            )
            if monitor.notifier_enabled:
                notified = monitor.notify(report)
                _operator_log(
                    "DISCORD",
                    "SENT" if notified else "FAILED",
                )
            plan = load_funding_order_plan(plan_path)
            validate_plan_settings(plan, settings)

            if not args.submit:
                container = build_binance_container(
                    settings,
                    database_path=args.database_path,
                )
                preflight = ApplicationRuntime(container).preflight()
                _operator_log(
                    "PREFLIGHT",
                    "PASSED",
                    account_mode=preflight.account_mode.value,
                    one_way_mode=preflight.one_way_mode,
                )
                order_executor = build_funding_order_executor(container)
                _operator_log(
                    "SPOT_CAPACITY",
                    "CHECK_BEGIN",
                    symbol=plan.symbol,
                    quantity=plan.spot_quantity,
                )
                order_executor.prepare_spot_taker(
                    plan,
                    quantity=plan.spot_quantity,
                )
                _operator_log("SPOT_CAPACITY", "CHECK_PASSED")
                prepared = order_executor.prepare_perpetual_maker(plan)
                print(
                    json.dumps(
                        prepared_order_payload(
                            prepared,
                            mode="PREVIEW",
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                _operator_log("PROCESS", "STOPPED", exit_code=0)
                return 0

            application = build_funding_rate_strategy_application(
                settings=settings,
                plan=plan,
                database_path=args.database_path,
                confirmed_symbol=confirmed_symbol,
                submit_missing_maker=True,
            )
            if application.prepared_maker is not None:
                print(
                    json.dumps(
                        prepared_order_payload(
                            application.prepared_maker,
                            mode="ARMED",
                        ),
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                _operator_log(
                    "PERPETUAL_MAKER",
                    "PERSISTED_ORDER_FOUND",
                    client_order_id=plan.perpetual_client_order_id,
                )

        _operator_log("PROCESS", "STRATEGY_STARTING")
        asyncio.run(application.run())
    except (FundingOrderPlanError, RuntimeError, ValueError) as exc:
        _operator_log(
            "PROCESS",
            "ERROR",
            error_type=type(exc).__name__,
            reason=str(exc),
        )
        _operator_log("PROCESS", "STOPPED", exit_code=1)
        return 1
    except KeyboardInterrupt:
        _operator_log("PROCESS", "INTERRUPTED")
        _operator_log("PROCESS", "STOPPED", exit_code=130)
        return 130
    _operator_log("PROCESS", "STOPPED", exit_code=0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
