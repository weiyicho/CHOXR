from decimal import Decimal

from adapters.persistence import SqliteOrderEventRepository, SqliteOrderRepository
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
from strategies.funding_rate import FundingCapitalAllocator, FundingEntryCoordinator


def test_perpetual_partial_fill_triggers_exact_incremental_spot_hedge(tmp_path) -> None:
    perpetual = InstrumentId("binance", "USD_M_PERPETUAL", "ETHUSDT")
    spot = InstrumentId("binance", "MARGIN", "ETHUSDT")
    account = AccountSnapshot(
        venue="binance",
        balances=(BalanceSnapshot("USDT", "100", "100"),),
        available_margin="100",
    )
    perpetual_rules = SymbolRules(
        perpetual, "ETH", "USDT", "0.1", "0.001", "0.001", min_notional="5"
    )
    spot_rules = SymbolRules(
        spot, "ETH", "USDT", "0.1", "0.001", "0.001", min_notional="5"
    )
    book = OrderBookSnapshot(
        perpetual,
        bids=(OrderBookLevel("100", "5"),),
        asks=(OrderBookLevel("101", "5"),),
    )
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
            instrument=perpetual,
            side=Side.SELL,
            budget=CapitalBudget(allocation.futures_notional, "USDT"),
            account=account,
            order_book=book,
            symbol_rules=perpetual_rules,
            reason="funding_rate_perpetual_maker",
        )
    )
    PreTradeRiskCheck().require_approved(
        maker_plan.intent,
        RiskContext(
            account,
            "USDT",
            required_capital=allocation.futures_margin,
        ),
        RiskLimits(max_order_notional="60", max_gross_notional="100"),
    )

    gateway = SimulatedTradingGateway()
    database = tmp_path / "vertical.sqlite3"
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    execution = OrderExecutionService(gateway, orders, event_repository=events)
    perpetual_order = execution.submit(maker_plan.intent)
    assert perpetual_order.state is OrderState.NEW

    fill_event = gateway.fill(
        perpetual_order.intent.client_order_id,
        cumulative_quantity="0.2",
        average_price="101",
    )
    perpetual_order = execution.handle_event(fill_event)
    hedge = FundingEntryCoordinator().plan_spot_hedge(
        perpetual_order=perpetual_order,
        spot_instrument=spot,
        spot_rules=spot_rules,
        previously_hedged_quantity="0",
    )
    assert hedge is not None
    assert hedge.market_order.intent.quantity == Decimal("0.2")

    PreTradeRiskCheck().require_approved(
        hedge.market_order.intent,
        RiskContext(account, "USDT", reference_price="101"),
        RiskLimits(max_order_notional="60"),
    )
    gateway.queue_submit(
        SimulatedSubmitBehavior(SimulatedSubmitKind.FULL_FILL, "101")
    )
    spot_order = execution.submit(hedge.market_order.intent)

    assert spot_order.state is OrderState.FILLED
    assert spot_order.cumulative_quantity == Decimal("0.2")
    assert len(events.list_for_order(perpetual_order.intent.client_order_id)) == 3
