import asyncio
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
from engine.domain.order import OrderState, Side
from engine.execution import OrderExecutionService
from engine.planning import CapitalBudget, OrderPlanner, PlanningRequest
from engine.risk import PreTradeRiskCheck, RiskContext, RiskLimits
from strategies.funding_rate import FundingCapitalAllocator
from strategies.funding_rate.execution_policy import FundingCommandKind
from strategies.funding_rate.order import FundingOrderExecutor
from strategies.funding_rate.session import (
    FundingActionStatus,
    FundingSession,
    FundingSessionStatus,
)
from strategies.funding_rate.worker import (
    FundingActionDispatcher,
    FundingStrategyWorker,
)


PERPETUAL = InstrumentId("binance", "USD_M_PERPETUAL", "ETHUSDT")
SPOT = InstrumentId("binance", "MARGIN", "ETHUSDT")
ACCOUNT = AccountSnapshot(
    venue="binance",
    balances=(BalanceSnapshot("USDT", "100", "100"),),
    available_margin="100",
)


class MarketData:
    def get_symbol_rules(self, instrument: InstrumentId) -> SymbolRules:
        return SymbolRules(
            instrument,
            "ETH",
            "USDT",
            "0.1",
            "0.001",
            "0.001",
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
            bids=(OrderBookLevel("100", "5"),),
            asks=(OrderBookLevel("101", "5"),),
        )


class AccountGateway:
    def get_account_snapshot(self) -> AccountSnapshot:
        return ACCOUNT


def test_perpetual_partial_fill_triggers_one_durable_spot_hedge(
    tmp_path,
) -> None:
    market_data = MarketData()
    allocation = FundingCapitalAllocator().allocate(
        available_capital="100",
        capital_fraction="0.6",
        futures_leverage="5",
        reference_price="100",
    )
    maker_plan = OrderPlanner().plan(
        PlanningRequest(
            execution_id="funding-vertical-1",
            client_order_id="perp-maker-vertical-1",
            instrument=PERPETUAL,
            side=Side.SELL,
            budget=CapitalBudget(allocation.futures_notional, "USDT"),
            account=ACCOUNT,
            order_book=market_data.get_order_book(PERPETUAL),
            symbol_rules=market_data.get_symbol_rules(PERPETUAL),
            reason="funding_rate_perpetual_maker",
        )
    )
    PreTradeRiskCheck().require_approved(
        maker_plan.intent,
        RiskContext(
            ACCOUNT,
            "USDT",
            required_capital=allocation.futures_margin,
        ),
        RiskLimits(max_order_notional="60", max_gross_notional="100"),
    )

    gateway = SimulatedTradingGateway()
    database = tmp_path / "vertical.sqlite3"
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    funding = SqliteFundingRepository(database)
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    perpetual_order = execution.submit(maker_plan.intent)
    fill_event = gateway.fill(
        perpetual_order.intent.client_order_id,
        cumulative_quantity="0.2",
        average_price="101",
    )
    perpetual_order = execution.handle_event(fill_event)
    funding.save_session(
        FundingSession(
            execution_id=perpetual_order.intent.execution_id,
            symbol="ETHUSDT",
            policy_name="PERPETUAL_MAKER_SPOT_TAKER",
            status=FundingSessionStatus.ENTERING,
            target_quantity=perpetual_order.intent.quantity,
            capital="60",
            maker_client_order_id=perpetual_order.intent.client_order_id,
            delta_tolerance="0.001",
        )
    )
    order_executor = FundingOrderExecutor(
        market_data_gateway=market_data,
        account_gateway=AccountGateway(),
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
        market_data_gateway=market_data,
        dispatcher=dispatcher,
    )
    gateway.queue_submit(
        SimulatedSubmitBehavior(SimulatedSubmitKind.FULL_FILL, "101")
    )

    worker.process_event(fill_event)

    actions = funding.list_actions("funding-vertical-1")
    assert len(actions) == 1
    assert actions[0].action_type == FundingCommandKind.SUBMIT_HEDGE.value
    assert actions[0].status is FundingActionStatus.COMPLETED
    assert actions[0].requested_quantity == Decimal("0.2")
    assert actions[0].client_order_id is not None
    spot_order = orders.get(actions[0].client_order_id)
    assert spot_order is not None
    assert spot_order.intent.instrument == SPOT
    assert spot_order.state is OrderState.FILLED
    assert spot_order.cumulative_quantity == Decimal("0.2")
    assert (
        funding.get_session("funding-vertical-1").status
        is FundingSessionStatus.HEDGING
    )

    # The same committed WebSocket event cannot create another Spot order.
    assert worker.process_event(fill_event) == ()
    assert len(funding.list_actions("funding-vertical-1")) == 1
    assert gateway.submit_calls == 2
