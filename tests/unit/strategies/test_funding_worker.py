from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from adapters.persistence import (
    SqliteFundingRepository,
    SqliteOrderEventRepository,
    SqliteOrderRepository,
)
from adapters.simulation import (
    SimulatedSubmitBehavior,
    SimulatedSubmitKind,
    SimulatedTradingGateway,
)
from engine.domain.account import AccountSnapshot, BalanceSnapshot
from engine.domain.instrument import (
    InstrumentId,
    OrderBookLevel,
    OrderBookSnapshot,
    SymbolRules,
)
from engine.domain.order import (
    OrderIntent,
    OrderRecord,
    OrderState,
    OrderType,
    Side,
)
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.domain.order_fill import OrderFill
from engine.execution import OrderExecutionService
from strategies.funding_rate.execution_policy import FundingCommandKind
from strategies.funding_rate.order import FundingOrderExecutor
from strategies.funding_rate.session import (
    FundingAction,
    FundingActionStatus,
    FundingSession,
    FundingSessionStatus,
)
from strategies.funding_rate.worker import (
    FundingActionDispatcher,
    FundingStrategyWorker,
)


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)
PERPETUAL = InstrumentId("binance", "USD_M_PERPETUAL", "BNBUSDT")
SPOT = InstrumentId("binance", "MARGIN", "BNBUSDT")


class FakeMarketDataGateway:
    def get_symbol_rules(self, instrument: InstrumentId) -> SymbolRules:
        return SymbolRules(
            instrument=instrument,
            base_asset="BNB",
            quote_asset="USDT",
            price_increment="0.01",
            quantity_increment="0.001",
            min_quantity="0.001",
            min_notional="0",
            market_quantity_increment="0.001",
            market_min_quantity="0.001",
        )

    def get_order_book(
        self,
        instrument: InstrumentId,
        depth: int | None = None,
    ) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            instrument,
            bids=(OrderBookLevel("99", "10"),),
            asks=(OrderBookLevel("100", "10"),),
        )


class FakeAccountGateway:
    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            venue="binance",
            balances=(BalanceSnapshot("USDT", "100", "100"),),
            available_margin="100",
        )


def maker_order(
    *,
    state: OrderState,
    cumulative_quantity: str,
    quantity: str = "0.2",
) -> OrderRecord:
    return OrderRecord(
        intent=OrderIntent(
            execution_id="funding-worker-1",
            client_order_id="frp-maker-1",
            instrument=PERPETUAL,
            side=Side.SELL,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price="100",
            post_only=True,
        ),
        state=state,
        cumulative_quantity=cumulative_quantity,
        average_price="100" if Decimal(cumulative_quantity) > 0 else None,
        created_at=NOW,
        updated_at=NOW,
    )


def maker_event(cumulative_quantity: str) -> OrderEvent:
    return OrderEvent(
        kind=OrderEventKind.TRADE,
        client_order_id="frp-maker-1",
        event_id=f"maker-fill-{cumulative_quantity}",
        cumulative_quantity=cumulative_quantity,
        last_executed_quantity=cumulative_quantity,
        last_executed_price="100",
        trade_id=f"trade-{cumulative_quantity}",
        occurred_at=NOW,
    )


def save_session(
    repository: SqliteFundingRepository,
    *,
    target_quantity: str = "0.2",
) -> FundingSession:
    session = FundingSession(
        execution_id="funding-worker-1",
        symbol="BNBUSDT",
        policy_name="PERPETUAL_MAKER_SPOT_TAKER",
        status=FundingSessionStatus.ENTERING,
        target_quantity=target_quantity,
        capital="50",
        maker_client_order_id="frp-maker-1",
        delta_tolerance="0",
        created_at=NOW,
        updated_at=NOW,
    )
    repository.save_session(session)
    return session


def planner_worker(tmp_path, maker: OrderRecord):
    database = tmp_path / "orders.sqlite3"
    funding = SqliteFundingRepository(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    orders.save(maker)
    save_session(funding, target_quantity=str(maker.intent.quantity))
    worker = FundingStrategyWorker(
        committed_event_queue=asyncio.Queue(),
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_event_repository=events,
        market_data_gateway=FakeMarketDataGateway(),
    )
    return worker, funding, orders, events


def test_committed_partial_fill_creates_one_durable_incremental_hedge(
    tmp_path,
    capsys,
) -> None:
    worker, funding, _, events = planner_worker(
        tmp_path,
        maker_order(
            state=OrderState.PARTIALLY_FILLED,
            cumulative_quantity="0.12",
            quantity="0.2",
        ),
    )
    event = maker_event("0.12")
    events.append(event)

    planned = worker.process_event(event)

    assert len(planned) == 1
    assert planned[0].action_type == FundingCommandKind.SUBMIT_HEDGE.value
    assert planned[0].requested_quantity == Decimal("0.12")
    assert planned[0].client_order_id is not None
    assert planned[0].client_order_id.startswith("frh-")
    assert (
        funding.get_session("funding-worker-1").status
        is FundingSessionStatus.HEDGING
    )

    # Replaying the same committed fill observes the durable pending action and
    # cannot reserve or submit the same Spot quantity twice.
    assert worker.process_event(event) == ()
    assert len(funding.list_actions("funding-worker-1")) == 1

    output = capsys.readouterr().out
    expected_markers = (
        "[FUNDING][EVENT] committed order event received",
        "[FUNDING][EVENT] funding order identified",
        "[FUNDING][CALC] hedge inputs",
        "[FUNDING][CALC] hedge result",
        "[FUNDING][DECISION] policy command",
        "[FUNDING][ACTION] durable action persisted",
        "[FUNDING][WAIT] no policy action",
    )
    positions = tuple(output.index(marker) for marker in expected_markers)
    assert positions == tuple(sorted(positions))
    assert "role=MAKER" in output
    assert "command=SUBMIT_HEDGE quantity=0.12" in output
    assert "reason=cover confirmed perpetual fills" in output


def test_base_asset_commission_is_rehedged_from_persisted_fill_events(
    tmp_path,
) -> None:
    worker, funding, orders, events = planner_worker(
        tmp_path,
        maker_order(state=OrderState.FILLED, cumulative_quantity="0.2"),
    )
    first_action = FundingAction(
        action_id="first-spot-action",
        execution_id="funding-worker-1",
        source_event_id="maker-fill-0.2",
        action_type=FundingCommandKind.SUBMIT_HEDGE.value,
        client_order_id="frh-first",
        requested_quantity="0.2",
        status=FundingActionStatus.COMPLETED,
        created_at=NOW,
        updated_at=NOW,
    )
    funding.save_action(first_action)
    spot_order = OrderRecord(
        intent=OrderIntent(
            execution_id="funding-worker-1",
            client_order_id="frh-first",
            instrument=SPOT,
            side=Side.BUY,
            quantity="0.2",
        ),
        state=OrderState.FILLED,
        cumulative_quantity="0.2",
        average_price="100",
        created_at=NOW,
        updated_at=NOW,
    )
    orders.save(spot_order)
    spot_fill = OrderEvent(
        kind=OrderEventKind.TRADE,
        client_order_id="frh-first",
        event_id="spot-fill-with-base-fee",
        cumulative_quantity="0.2",
        last_executed_quantity="0.2",
        last_executed_price="100",
        trade_id="spot-trade-1",
        commission="0.001",
        commission_asset="BNB",
        occurred_at=NOW,
    )
    events.append(spot_fill)

    planned = worker.process_event(spot_fill)

    assert len(planned) == 1
    assert planned[0].action_type == FundingCommandKind.SUBMIT_HEDGE.value
    assert planned[0].requested_quantity == Decimal("0.001")


def test_rest_fill_reconciliation_backfills_missing_commission_once(
    tmp_path,
    capsys,
) -> None:
    worker, funding, orders, events = planner_worker(
        tmp_path,
        maker_order(state=OrderState.FILLED, cumulative_quantity="0.2"),
    )
    action = FundingAction(
        action_id="first-spot-action",
        execution_id="funding-worker-1",
        source_event_id="maker-fill-0.2",
        action_type=FundingCommandKind.SUBMIT_HEDGE.value,
        client_order_id="frh-first",
        requested_quantity="0.2",
        status=FundingActionStatus.COMPLETED,
        created_at=NOW,
        updated_at=NOW,
    )
    funding.save_action(action)
    orders.save(
        OrderRecord(
            intent=OrderIntent(
                execution_id="funding-worker-1",
                client_order_id="frh-first",
                instrument=SPOT,
                side=Side.BUY,
                quantity="0.2",
            ),
            state=OrderState.FILLED,
            exchange_order_id="77",
            cumulative_quantity="0.2",
            average_price="100",
            created_at=NOW,
            updated_at=NOW,
        )
    )

    class FakeFillGateway:
        def list_order_fills(self, instrument, exchange_order_id):
            assert instrument == SPOT
            assert exchange_order_id == "77"
            return (
                OrderFill(
                    instrument=SPOT,
                    trade_id="55",
                    exchange_order_id="77",
                    price="100",
                    quantity="0.2",
                    quote_quantity="20",
                    commission="0.001",
                    commission_asset="BNB",
                    occurred_at=NOW,
                ),
            )

    reconciler = FundingStrategyWorker(
        committed_event_queue=asyncio.Queue(),
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_event_repository=events,
        market_data_gateway=FakeMarketDataGateway(),
        fill_gateway=FakeFillGateway(),
    )
    # A WebSocket trade can establish quantity before usable commission
    # metadata is present. REST must still enrich the same trade ID.
    events.append(
        OrderEvent(
            kind=OrderEventKind.TRADE,
            client_order_id="frh-first",
            event_id="ws-fill-without-fee",
            last_executed_quantity="0.2",
            last_executed_price="100",
            trade_id="55",
            occurred_at=NOW,
        )
    )

    appended = reconciler.reconcile_fills("funding-worker-1")
    replayed = reconciler.reconcile_fills("funding-worker-1")
    planned = reconciler.process_event(maker_event("0.2"))

    assert len(appended) == 1
    assert replayed == ()
    assert appended[0].trade_id == "55"
    assert len(planned) == 1
    assert planned[0].requested_quantity == Decimal("0.001")

    output = capsys.readouterr().out
    assert "[FUNDING][FILL] REST Spot fills fetched" in output
    assert (
        "[FUNDING][FILL] REST fill backfilled "
        "client_order_id=frh-first trade_id=55 quantity=0.2 "
        "commission=0.001 commission_asset=BNB"
    ) in output


def test_terminal_spot_response_waits_for_complete_fill_history(
    tmp_path,
    capsys,
) -> None:
    _, funding, orders, events = planner_worker(
        tmp_path,
        maker_order(state=OrderState.FILLED, cumulative_quantity="0.2"),
    )
    funding.save_action(
        FundingAction(
            action_id="spot-action-awaiting-fills",
            execution_id="funding-worker-1",
            source_event_id="maker-fill-0.2",
            action_type=FundingCommandKind.SUBMIT_HEDGE.value,
            client_order_id="frh-awaiting-fills",
            requested_quantity="0.2",
            status=FundingActionStatus.COMPLETED,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    orders.save(
        OrderRecord(
            intent=OrderIntent(
                execution_id="funding-worker-1",
                client_order_id="frh-awaiting-fills",
                instrument=SPOT,
                side=Side.BUY,
                quantity="0.2",
            ),
            state=OrderState.FILLED,
            exchange_order_id="88",
            cumulative_quantity="0.2",
            average_price="100",
            created_at=NOW,
            updated_at=NOW,
        )
    )

    class EventuallyConsistentFillGateway:
        def __init__(self):
            self.calls = 0

        def list_order_fills(self, instrument, exchange_order_id):
            self.calls += 1
            if self.calls == 1:
                return ()
            return (
                OrderFill(
                    instrument=SPOT,
                    trade_id="eventual-trade",
                    exchange_order_id="88",
                    price="100",
                    quantity="0.2",
                    quote_quantity="20",
                    commission="0.001",
                    commission_asset="BNB",
                    occurred_at=NOW,
                ),
            )

    fill_gateway = EventuallyConsistentFillGateway()
    worker = FundingStrategyWorker(
        committed_event_queue=asyncio.Queue(),
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_event_repository=events,
        market_data_gateway=FakeMarketDataGateway(),
        fill_gateway=fill_gateway,
    )
    rest_terminal_event = OrderEvent(
        kind=OrderEventKind.RECONCILED,
        client_order_id="frh-awaiting-fills",
        event_id="spot-rest-filled-before-trades",
        cumulative_quantity="0.2",
        reconciled_state=OrderState.FILLED,
        occurred_at=NOW,
    )

    assert worker.process_event(rest_terminal_event) == ()
    assert (
        funding.get_session("funding-worker-1").status
        is FundingSessionStatus.ENTERING
    )
    retried = worker.retry_incomplete_fill_history()
    assert len(retried) == 1
    assert retried[0].action_type == FundingCommandKind.SUBMIT_HEDGE.value
    assert retried[0].requested_quantity == Decimal("0.001")
    assert fill_gateway.calls == 2

    output = capsys.readouterr().out
    assert (
        "[FUNDING][WAIT] decision deferred "
        "execution_id=funding-worker-1 "
        "reason=Spot fill quantity or commission history is incomplete"
    ) in output
    assert (
        "[FUNDING][FILL] retrying incomplete Spot fill history "
        "execution_id=funding-worker-1"
    ) in output


def test_dispatcher_cascades_full_spot_fill_to_open_session(
    tmp_path,
    capsys,
) -> None:
    database = tmp_path / "orders.sqlite3"
    funding = SqliteFundingRepository(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    maker = maker_order(state=OrderState.FILLED, cumulative_quantity="0.2")
    orders.save(maker)
    save_session(funding)

    gateway = SimulatedTradingGateway()
    gateway.queue_submit(
        SimulatedSubmitBehavior(SimulatedSubmitKind.FULL_FILL, "100")
    )
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    order_executor = FundingOrderExecutor(
        market_data_gateway=FakeMarketDataGateway(),
        account_gateway=FakeAccountGateway(),
        trading_gateway=gateway,
        execution_service=execution,
    )
    dispatcher = FundingActionDispatcher(
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_executor=order_executor,
        execution_service=execution,
    )
    worker = FundingStrategyWorker(
        committed_event_queue=asyncio.Queue(),
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_event_repository=events,
        market_data_gateway=FakeMarketDataGateway(),
        dispatcher=dispatcher,
    )
    event = maker_event("0.2")
    events.append(event)

    initial = worker.process_event(event)

    assert len(initial) == 1
    actions = funding.list_actions("funding-worker-1")
    assert tuple(action.action_type for action in actions) == (
        FundingCommandKind.SUBMIT_HEDGE.value,
        FundingCommandKind.MARK_OPEN.value,
    )
    hedge_action = actions[0]
    assert hedge_action.status is FundingActionStatus.COMPLETED
    assert hedge_action.client_order_id is not None
    assert orders.get(hedge_action.client_order_id).state is OrderState.FILLED
    assert funding.get_session("funding-worker-1").status is FundingSessionStatus.OPEN
    assert gateway.submit_calls == 1

    output = capsys.readouterr().out
    expected_markers = (
        "[FUNDING][ACTION] dispatch requested",
        "[FUNDING][ORDER] preparing Spot MARKET hedge",
        "[FUNDING][ORDER] Spot hedge approved; submitting",
        "[FUNDING][ORDER] Spot hedge submit returned",
        "[FUNDING][ACTION] dispatch completed",
        "[FUNDING][ORDER] authoritative order state",
    )
    positions = tuple(output.index(marker) for marker in expected_markers)
    assert positions == tuple(sorted(positions))
    assert "state=FILLED cumulative_quantity=0.2" in output


def test_local_spot_hedge_failure_durably_cancels_maker_and_pauses(
    tmp_path,
    capsys,
) -> None:
    database = tmp_path / "orders.sqlite3"
    funding = SqliteFundingRepository(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    gateway = SimulatedTradingGateway()
    maker_intent = maker_order(
        state=OrderState.NEW,
        cumulative_quantity="0",
    ).intent
    maker = gateway.submit_order(maker_intent)
    orders.save(maker)
    save_session(funding)
    execution = OrderExecutionService(gateway, orders, event_repository=events)

    class FailingSpotOrderExecutor:
        def prepare_spot_hedge(self, **kwargs):
            raise RuntimeError("Spot ask depth unavailable")

    action = FundingAction(
        action_id="failed-spot-action",
        execution_id="funding-worker-1",
        source_event_id="maker-fill-before-failure",
        action_type=FundingCommandKind.SUBMIT_HEDGE.value,
        client_order_id="frh-failed-spot",
        requested_quantity="0.1",
        created_at=NOW,
        updated_at=NOW,
    )
    funding.save_action(action)
    dispatcher = FundingActionDispatcher(
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_executor=FailingSpotOrderExecutor(),
        execution_service=execution,
    )

    outcome = dispatcher.dispatch(action)

    assert outcome.action.status is FundingActionStatus.FAILED
    assert orders.get(maker_intent.client_order_id).state is OrderState.CANCELED
    assert funding.get_session("funding-worker-1").status is FundingSessionStatus.PAUSED
    actions = funding.list_actions("funding-worker-1")
    assert tuple(candidate.action_type for candidate in actions) == (
        FundingCommandKind.SUBMIT_HEDGE.value,
        FundingCommandKind.CANCEL_MAKER.value,
        FundingCommandKind.RECONCILE.value,
    )
    assert all(
        candidate.status is FundingActionStatus.COMPLETED
        for candidate in actions[1:]
    )

    output = capsys.readouterr().out
    assert (
        "[FUNDING][RECOVERY] action execution failed "
        "action_id=failed-spot-action type=SUBMIT_HEDGE "
        "reason=Spot ask depth unavailable"
    ) in output
    assert (
        "[FUNDING][RECOVERY] hedge failed and session paused atomically"
    ) in output
    assert "[FUNDING][RECOVERY] canceling remaining Perp maker" in output
    assert "[FUNDING][RECOVERY] reconciling order through REST" in output


def test_rejected_spot_hedge_cancels_maker_without_second_submit(
    tmp_path,
) -> None:
    database = tmp_path / "orders.sqlite3"
    funding = SqliteFundingRepository(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    gateway = SimulatedTradingGateway()
    submitted_maker = gateway.submit_order(
        maker_order(state=OrderState.NEW, cumulative_quantity="0").intent
    )
    gateway.fill(submitted_maker.intent.client_order_id, "0.1", "100")
    orders.save(
        gateway.get_order(
            submitted_maker.intent.instrument,
            submitted_maker.intent.client_order_id,
        )
    )
    save_session(funding)
    gateway.queue_submit(
        SimulatedSubmitBehavior(SimulatedSubmitKind.REJECT)
    )
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    order_executor = FundingOrderExecutor(
        market_data_gateway=FakeMarketDataGateway(),
        account_gateway=FakeAccountGateway(),
        trading_gateway=gateway,
        execution_service=execution,
    )
    dispatcher = FundingActionDispatcher(
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_executor=order_executor,
        execution_service=execution,
    )
    worker = FundingStrategyWorker(
        committed_event_queue=asyncio.Queue(),
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_event_repository=events,
        market_data_gateway=FakeMarketDataGateway(),
        dispatcher=dispatcher,
    )
    event = maker_event("0.1")
    events.append(event)

    worker.process_event(event)

    actions = funding.list_actions("funding-worker-1")
    hedge_actions = tuple(
        action
        for action in actions
        if action.action_type == FundingCommandKind.SUBMIT_HEDGE.value
    )
    recovery_actions = tuple(
        action
        for action in actions
        if action.action_type
        in {
            FundingCommandKind.CANCEL_MAKER.value,
            FundingCommandKind.RECONCILE.value,
        }
    )
    assert len(hedge_actions) == 1
    assert hedge_actions[0].status is FundingActionStatus.FAILED
    assert all(
        action.status is FundingActionStatus.COMPLETED
        for action in recovery_actions
    )
    assert gateway.submit_calls == 2  # one maker and exactly one Spot attempt
    assert (
        orders.get(submitted_maker.intent.client_order_id).state
        is OrderState.CANCELED
    )
    assert (
        funding.get_session("funding-worker-1").status
        is FundingSessionStatus.PAUSED
    )


def test_market_data_failure_pauses_and_cancels_partial_maker(
    tmp_path,
) -> None:
    database = tmp_path / "orders.sqlite3"
    funding = SqliteFundingRepository(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    gateway = SimulatedTradingGateway()
    submitted_maker = gateway.submit_order(
        maker_order(state=OrderState.NEW, cumulative_quantity="0").intent
    )
    gateway.fill(submitted_maker.intent.client_order_id, "0.1", "100")
    orders.save(
        gateway.get_order(
            submitted_maker.intent.instrument,
            submitted_maker.intent.client_order_id,
        )
    )
    save_session(funding)
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    dispatcher = FundingActionDispatcher(
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_executor=FundingOrderExecutor(
            market_data_gateway=FakeMarketDataGateway(),
            account_gateway=FakeAccountGateway(),
            trading_gateway=gateway,
            execution_service=execution,
        ),
        execution_service=execution,
    )

    class FailingMarketDataGateway(FakeMarketDataGateway):
        def get_symbol_rules(self, instrument):
            raise RuntimeError("simulated exchangeInfo outage")

    worker = FundingStrategyWorker(
        committed_event_queue=asyncio.Queue(),
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_event_repository=events,
        market_data_gateway=FailingMarketDataGateway(),
        dispatcher=dispatcher,
    )
    event = maker_event("0.1")
    events.append(event)

    planned = worker.process_event(event)

    assert tuple(action.action_type for action in planned) == (
        FundingCommandKind.PAUSE.value,
        FundingCommandKind.CANCEL_MAKER.value,
        FundingCommandKind.RECONCILE.value,
    )
    assert all(
        action.status is FundingActionStatus.COMPLETED
        for action in funding.list_actions("funding-worker-1")
    )
    assert gateway.submit_calls == 1
    assert (
        orders.get(submitted_maker.intent.client_order_id).state
        is OrderState.CANCELED
    )
    assert (
        funding.get_session("funding-worker-1").status
        is FundingSessionStatus.PAUSED
    )


def test_unknown_spot_submission_reconciles_same_id_before_resuming(
    tmp_path,
) -> None:
    database = tmp_path / "orders.sqlite3"
    funding = SqliteFundingRepository(database)
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    orders.save(
        maker_order(
            state=OrderState.PARTIALLY_FILLED,
            cumulative_quantity="0.1",
        )
    )
    save_session(funding)
    gateway = SimulatedTradingGateway()
    gateway.queue_submit(
        SimulatedSubmitBehavior(
            SimulatedSubmitKind.TIMEOUT_BEFORE_ACCEPT,
        )
    )
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    order_executor = FundingOrderExecutor(
        market_data_gateway=FakeMarketDataGateway(),
        account_gateway=FakeAccountGateway(),
        trading_gateway=gateway,
        execution_service=execution,
    )
    dispatcher = FundingActionDispatcher(
        session_repository=funding,
        action_repository=funding,
        order_repository=orders,
        order_executor=order_executor,
        execution_service=execution,
    )
    action = FundingAction(
        action_id="unknown-spot-action",
        execution_id="funding-worker-1",
        source_event_id="maker-fill-unknown",
        action_type=FundingCommandKind.SUBMIT_HEDGE.value,
        client_order_id="frh-unknown-spot",
        requested_quantity="0.1",
        created_at=NOW,
        updated_at=NOW,
    )
    funding.save_action(action)

    first = dispatcher.dispatch(action)

    assert first.orders[0].state is OrderState.UNKNOWN
    assert (
        funding.get_action(action.action_id).status
        is FundingActionStatus.IN_PROGRESS
    )
    assert funding.get_session("funding-worker-1").status is FundingSessionStatus.PAUSED

    # Simulate discovering that Binance did accept the exact same client ID.
    gateway.submit_order(orders.get("frh-unknown-spot").intent)
    recovered = dispatcher.dispatch(funding.get_action(action.action_id))

    assert recovered.orders[0].state is OrderState.NEW
    assert (
        funding.get_action(action.action_id).status
        is FundingActionStatus.COMPLETED
    )
    assert (
        funding.get_session("funding-worker-1").status
        is FundingSessionStatus.HEDGING
    )
    assert gateway.submit_calls == 2
