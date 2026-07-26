from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import strategies.funding_rate.main as funding_local
from adapters.binance.config import BinanceAccountMode
from adapters.persistence import (
    SqliteFundingRepository,
    SqliteOrderEventRepository,
    SqliteOrderRepository,
)
from adapters.simulation import SimulatedTradingGateway
from app.settings import Settings
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
from engine.execution import OrderExecutionService
from strategies.funding_rate.order import (
    FundingOrderPlanError,
    ReadyFundingOrderPlan,
)
from strategies.funding_rate.session import (
    FundingSession,
    FundingSessionStatus,
)


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


class FakeMarketDataGateway:
    def get_symbol_rules(self, instrument: InstrumentId) -> SymbolRules:
        return SymbolRules(
            instrument=instrument,
            base_asset="BNB",
            quote_asset="USDT",
            price_increment="0.01",
            quantity_increment="0.001",
            min_quantity="0.001",
            min_notional="5",
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
            balances=(
                BalanceSnapshot("USDT", "100", "100"),
                BalanceSnapshot("BNB", "1.5", "1.5"),
            ),
            available_margin="100",
        )


class FakeOrderEventStream:
    def request_stop(self) -> None:
        pass

    async def events(self):
        if False:
            yield


def ready_plan() -> ReadyFundingOrderPlan:
    return ReadyFundingOrderPlan(
        generated_at=NOW,
        next_funding_at=NOW + timedelta(hours=8),
        symbol="BNBUSDT",
        capital=Decimal("50"),
        leverage=5,
        spot_reference_price=Decimal("100"),
        spot_quantity=Decimal("0.4"),
        spot_notional=Decimal("40"),
        perpetual_reference_price=Decimal("100"),
        perpetual_quantity=Decimal("0.4"),
        perpetual_notional=Decimal("40"),
        perpetual_margin=Decimal("8"),
    )


def test_strategy_application_creates_durable_session_for_existing_maker(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "orders.sqlite3"
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    funding = SqliteFundingRepository(database)
    gateway = SimulatedTradingGateway()
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    plan = ready_plan()
    maker = OrderRecord(
        intent=OrderIntent(
            execution_id=plan.execution_id,
            client_order_id=plan.perpetual_client_order_id,
            instrument=InstrumentId(
                "binance",
                "USD_M_PERPETUAL",
                "BNBUSDT",
            ),
            side=Side.SELL,
            quantity="0.4",
            order_type=OrderType.LIMIT,
            price="100",
            post_only=True,
        ),
        state=OrderState.PARTIALLY_FILLED,
        cumulative_quantity="0.1",
        average_price="100",
    )
    orders.save(maker)
    container = SimpleNamespace(
        trading_gateway=gateway,
        market_data_gateway=FakeMarketDataGateway(),
        account_gateway=FakeAccountGateway(),
        order_event_stream=FakeOrderEventStream(),
        order_repository=orders,
        order_event_repository=events,
        funding_repository=funding,
        execution_service=execution,
    )
    monkeypatch.setattr(
        funding_local,
        "build_binance_container",
        lambda settings, database_path: container,
    )

    application = funding_local.build_funding_rate_strategy_application(
        settings=Settings(
            "key",
            "secret",
            live_trading_enabled=True,
            funding_capital="50",
            funding_leverage=5,
        ),
        plan=plan,
        database_path=database,
        confirmed_symbol="bnbusdt",
    )

    session = funding.get_session(plan.execution_id)
    assert application.session == session
    assert session is not None
    assert session.status is FundingSessionStatus.HEDGING
    assert session.target_quantity == Decimal("0.4")
    assert session.starting_spot_quantity == Decimal("1.5")
    assert session.delta_tolerance == Decimal("0.001")


def test_strategy_application_requires_live_mode_and_exact_symbol(tmp_path) -> None:
    plan = ready_plan()
    with pytest.raises(RuntimeError, match="live trading is disabled"):
        funding_local.build_funding_rate_strategy_application(
            settings=Settings("key", "secret"),
            plan=plan,
            database_path=tmp_path / "orders.sqlite3",
            confirmed_symbol="BNBUSDT",
        )
    with pytest.raises(RuntimeError, match="confirm-symbol BNBUSDT"):
        funding_local.build_funding_rate_strategy_application(
            settings=Settings(
                "key",
                "secret",
                live_trading_enabled=True,
                funding_capital="50",
                funding_leverage=5,
            ),
            plan=plan,
            database_path=tmp_path / "orders.sqlite3",
            confirmed_symbol="ETHUSDT",
        )


def test_new_entry_checks_full_spot_capacity_before_preparing_maker(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "orders.sqlite3"
    orders = SqliteOrderRepository(database)
    funding = SqliteFundingRepository(database)
    timeline: list[str] = []
    container = SimpleNamespace(
        market_data_gateway=FakeMarketDataGateway(),
        account_gateway=FakeAccountGateway(),
        order_repository=orders,
        funding_repository=funding,
    )

    class RejectingExecutor:
        def prepare_spot_taker(self, plan, *, quantity):
            timeline.append("spot_capacity_checked")
            raise RuntimeError("Spot capital unavailable")

        def prepare_perpetual_maker(self, plan):
            timeline.append("perpetual_prepared")
            raise AssertionError("Perp preparation must not run")

    monkeypatch.setattr(
        funding_local,
        "build_binance_container",
        lambda settings, database_path: container,
    )
    monkeypatch.setattr(
        funding_local,
        "build_funding_order_executor",
        lambda container: RejectingExecutor(),
    )

    with pytest.raises(RuntimeError, match="Spot capital unavailable"):
        funding_local.build_funding_rate_strategy_application(
            settings=Settings(
                "key",
                "secret",
                live_trading_enabled=True,
                funding_capital="50",
                funding_leverage=5,
            ),
            plan=ready_plan(),
            database_path=database,
            confirmed_symbol="BNBUSDT",
            submit_missing_maker=True,
        )

    assert timeline == ["spot_capacity_checked"]
    assert orders.list_open() == ()


def test_strategy_application_restarts_from_active_session_without_plan(
    tmp_path,
    monkeypatch,
) -> None:
    database = tmp_path / "orders.sqlite3"
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    funding = SqliteFundingRepository(database)
    gateway = SimulatedTradingGateway()
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    plan = ready_plan()
    maker = OrderRecord(
        intent=OrderIntent(
            execution_id=plan.execution_id,
            client_order_id=plan.perpetual_client_order_id,
            instrument=InstrumentId(
                "binance",
                "USD_M_PERPETUAL",
                "BNBUSDT",
            ),
            side=Side.SELL,
            quantity="0.4",
            order_type=OrderType.LIMIT,
            price="100",
            post_only=True,
        ),
        state=OrderState.PARTIALLY_FILLED,
        cumulative_quantity="0.1",
        average_price="100",
    )
    orders.save(maker)
    persisted_session = FundingSession(
        execution_id=plan.execution_id,
        symbol="BNBUSDT",
        policy_name="PERPETUAL_MAKER_SPOT_TAKER",
        status=FundingSessionStatus.HEDGING,
        target_quantity="0.4",
        capital="50",
        maker_client_order_id=maker.intent.client_order_id,
        starting_spot_quantity="1.5",
        delta_tolerance="0.001",
    )
    funding.save_session(persisted_session)
    container = SimpleNamespace(
        trading_gateway=gateway,
        market_data_gateway=FakeMarketDataGateway(),
        account_gateway=FakeAccountGateway(),
        order_event_stream=FakeOrderEventStream(),
        order_repository=orders,
        order_event_repository=events,
        funding_repository=funding,
        execution_service=execution,
    )
    monkeypatch.setattr(
        funding_local,
        "build_binance_container",
        lambda settings, database_path: container,
    )

    application = funding_local.build_funding_rate_strategy_application(
        settings=Settings(
            "key",
            "secret",
            live_trading_enabled=True,
        ),
        plan=None,
        database_path=database,
        confirmed_symbol="BNBUSDT",
        execution_id=plan.execution_id,
    )

    assert application.session == persisted_session


def test_select_active_session_requires_execution_id_for_ambiguity() -> None:
    sessions = tuple(
        FundingSession(
            execution_id=execution_id,
            symbol="BNBUSDT",
            policy_name="PERPETUAL_MAKER_SPOT_TAKER",
            status=FundingSessionStatus.HEDGING,
            target_quantity="0.4",
            capital="50",
        )
        for execution_id in ("fr-a", "fr-b")
    )

    with pytest.raises(FundingOrderPlanError, match="pass --execution-id"):
        funding_local._select_active_session(
            sessions,
            confirmed_symbol="BNBUSDT",
            execution_id=None,
        )

    selected = funding_local._select_active_session(
        sessions,
        confirmed_symbol="BNBUSDT",
        execution_id="fr-b",
    )
    assert selected.execution_id == "fr-b"


def test_strategy_application_prints_live_startup_and_shutdown_decisions(
    capsys,
) -> None:
    plan = ready_plan()
    maker = OrderRecord(
        intent=OrderIntent(
            execution_id=plan.execution_id,
            client_order_id=plan.perpetual_client_order_id,
            instrument=InstrumentId(
                "binance",
                "USD_M_PERPETUAL",
                "BNBUSDT",
            ),
            side=Side.SELL,
            quantity="0.4",
            order_type=OrderType.LIMIT,
            price="100",
            post_only=True,
        ),
        state=OrderState.NEW,
    )
    session = FundingSession(
        execution_id=plan.execution_id,
        symbol="BNBUSDT",
        policy_name="PERPETUAL_MAKER_SPOT_TAKER",
        status=FundingSessionStatus.ENTERING,
        target_quantity="0.4",
        capital="50",
        maker_client_order_id=maker.intent.client_order_id,
    )

    class FakeRuntime:
        def preflight(self):
            return SimpleNamespace(
                account_mode=(
                    BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN
                ),
                one_way_mode=True,
            )

        async def consume_order_events(self):
            await asyncio.Event().wait()

        async def wait_until_synchronized(self):
            return None

    class FakeWorker:
        def reconcile_fills(self, execution_id):
            assert execution_id == session.execution_id
            return ()

        def recover_pending_actions(self, execution_id):
            assert execution_id == session.execution_id
            return ()

        def process_event(self, event):
            assert event.client_order_id == maker.intent.client_order_id
            return ()

        async def run(self):
            raise RuntimeError("intentional test stop")

    application = funding_local.FundingRateStrategyApplication(
        container=SimpleNamespace(
            order_repository=SimpleNamespace(
                get=lambda client_order_id: maker
            ),
            order_event_stream=FakeOrderEventStream(),
        ),
        runtime=FakeRuntime(),
        worker=FakeWorker(),
        session=session,
    )

    with pytest.raises(RuntimeError, match="intentional test stop"):
        asyncio.run(application.run())

    output = capsys.readouterr().out
    assert (
        f"[FUNDING][APPLICATION] START "
        f"execution_id={session.execution_id} symbol=BNBUSDT"
    ) in output
    assert "[FUNDING][PREFLIGHT] BEGIN" in output
    assert (
        "[FUNDING][PREFLIGHT] PASSED "
        "account_mode=CLASSIC_PORTFOLIO_MARGIN one_way_mode=True"
    ) in output
    assert "[FUNDING][RUNTIME] WAITING_FOR_SYNCHRONIZATION" in output
    assert "[FUNDING][RUNTIME] SYNCHRONIZED" in output
    assert "[FUNDING][FILL_RECONCILIATION] COMPLETE recovered_events=0" in output
    assert "[FUNDING][PENDING_RECOVERY] COMPLETE dispatched_actions=0" in output
    assert (
        "[FUNDING][MAKER_SNAPSHOT] LOADED "
        f"client_order_id={maker.intent.client_order_id} state=NEW"
    ) in output
    assert "[FUNDING][MAKER_SNAPSHOT] PROCESSED planned_actions=0" in output
    assert "[FUNDING][WORKER] STARTED" in output
    assert "[FUNDING][APPLICATION] ERROR error_type=RuntimeError" in output
    assert "[FUNDING][APPLICATION] STOPPED" in output


def test_new_entry_synchronizes_websocket_before_submitting_maker(
    tmp_path,
) -> None:
    database = tmp_path / "orders.sqlite3"
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    funding = SqliteFundingRepository(database)
    plan = ready_plan()
    timeline: list[str] = []
    maker = OrderRecord(
        intent=OrderIntent(
            execution_id=plan.execution_id,
            client_order_id=plan.perpetual_client_order_id,
            instrument=InstrumentId(
                "binance",
                "USD_M_PERPETUAL",
                plan.symbol,
            ),
            side=Side.SELL,
            quantity="0.4",
            order_type=OrderType.LIMIT,
            price="100",
            post_only=True,
        ),
        state=OrderState.NEW,
        exchange_order_id="exchange-maker-1",
    )

    class FakeRuntime:
        def preflight(self):
            return SimpleNamespace(
                account_mode=(
                    BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN
                ),
                one_way_mode=True,
            )

        async def consume_order_events(self):
            timeline.append("websocket_started")
            await asyncio.Event().wait()

        async def wait_until_synchronized(self):
            timeline.append("websocket_synchronized")

    class FakeExecutor:
        def submit_perpetual_maker(self, prepared):
            timeline.append("maker_submitted")
            orders.save(maker)
            return maker

    class FakeWorker:
        def reconcile_fills(self, execution_id):
            timeline.append("fills_reconciled")
            return ()

        def recover_pending_actions(self, execution_id):
            return ()

        def process_event(self, event):
            return ()

        async def run(self):
            raise RuntimeError("intentional strategy stop")

    application = funding_local.FundingRateStrategyApplication(
        container=SimpleNamespace(
            market_data_gateway=FakeMarketDataGateway(),
            account_gateway=FakeAccountGateway(),
            order_repository=orders,
            funding_repository=funding,
            order_event_stream=FakeOrderEventStream(),
        ),
        runtime=FakeRuntime(),
        worker=FakeWorker(),
        session=None,
        plan=plan,
        prepared_maker=SimpleNamespace(intent=maker.intent),
        order_executor=FakeExecutor(),
    )

    with pytest.raises(RuntimeError, match="intentional strategy stop"):
        asyncio.run(application.run())

    assert timeline.index("websocket_synchronized") < timeline.index(
        "maker_submitted"
    )
    assert timeline.index("maker_submitted") < timeline.index(
        "fills_reconciled"
    )
    persisted = funding.get_session(plan.execution_id)
    assert persisted is not None
    assert persisted.maker_client_order_id == plan.perpetual_client_order_id


def test_main_prints_safe_order_plan_error_reason(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(funding_local, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        funding_local.Settings,
        "from_environment",
        staticmethod(lambda: SimpleNamespace()),
    )
    monkeypatch.setattr(
        funding_local,
        "load_funding_order_plan",
        lambda path: (_ for _ in ()).throw(
            FundingOrderPlanError("order plan is stale (5985s old)")
        ),
    )
    fake_report = SimpleNamespace(
        scanned_symbol_count=362,
        candidates=(object(),),
    )
    monkeypatch.setattr(
        funding_local,
        "build_funding_rate_monitor",
        lambda settings, order_plan_path: SimpleNamespace(
            notifier_enabled=False,
            scan_once=lambda: fake_report,
            save_order_plan=lambda report: order_plan_path,
        ),
    )
    monkeypatch.setattr(
        funding_local,
        "render_console_report",
        lambda report: "fake scan",
    )

    exit_code = funding_local.main(
        (
            "--database-path",
            str(tmp_path / "orders.sqlite3"),
            "--plan-path",
            str(tmp_path / "order_plan.json"),
            "--confirm-symbol",
            "BNBUSDT",
        )
    )

    assert exit_code == 1
    output = capsys.readouterr().out
    assert (
        "[FUNDING][PROCESS] ERROR "
        "error_type=FundingOrderPlanError "
        "reason=order plan is stale (5985s old)"
    ) in output
