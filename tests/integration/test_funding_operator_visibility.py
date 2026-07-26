"""Operator-facing visibility for the offline Funding Rate hedge flow."""

from __future__ import annotations

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
from engine.domain.order import (
    OrderIntent,
    OrderRecord,
    OrderState,
    OrderType,
    Side,
)
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.execution import OrderExecutionService
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


PERPETUAL = InstrumentId("binance", "USD_M_PERPETUAL", "BNBUSDT")
SPOT = InstrumentId("binance", "MARGIN", "BNBUSDT")


class OfflineMarketData:
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


class OfflineAccount:
    def get_account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            venue="binance",
            balances=(BalanceSnapshot("USDT", "100", "100"),),
            available_margin="100",
        )


def test_partial_fill_prints_the_complete_operator_decision_chain(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    """One offline fill visibly reaches calculation, policy, and Spot result."""

    secret_canaries = {
        "BINANCE_API_KEY": "visibility-api-key-canary",
        "BINANCE_API_SECRET": "visibility-secret-canary",
        "DISCORD_WEBHOOK_URL": "https://webhook.invalid/visibility-canary",
    }
    for name, value in secret_canaries.items():
        monkeypatch.setenv(name, value)

    database = tmp_path / "operator-visibility.sqlite3"
    orders = SqliteOrderRepository(database)
    events = SqliteOrderEventRepository(database)
    funding = SqliteFundingRepository(database)
    market_data = OfflineMarketData()
    gateway = SimulatedTradingGateway()
    execution = OrderExecutionService(
        gateway,
        orders,
        event_repository=events,
    )

    maker = OrderRecord(
        intent=OrderIntent(
            execution_id="funding-visibility-1",
            client_order_id="perp-maker-visibility-1",
            instrument=PERPETUAL,
            side=Side.SELL,
            quantity="0.3",
            order_type=OrderType.LIMIT,
            price="100",
            post_only=True,
        ),
        state=OrderState.PARTIALLY_FILLED,
        exchange_order_id="sim-perp-visibility-1",
        cumulative_quantity="0.2",
        average_price="100",
    )
    orders.save(maker)
    funding.save_session(
        FundingSession(
            execution_id=maker.intent.execution_id,
            symbol=maker.intent.instrument.symbol,
            policy_name="PERPETUAL_MAKER_SPOT_TAKER",
            status=FundingSessionStatus.ENTERING,
            target_quantity=maker.intent.quantity,
            capital="50",
            maker_client_order_id=maker.intent.client_order_id,
            delta_tolerance="0.001",
        )
    )
    fill_event = OrderEvent(
        kind=OrderEventKind.TRADE,
        client_order_id=maker.intent.client_order_id,
        event_id="maker-fill-visibility-0.2",
        cumulative_quantity="0.2",
        last_executed_quantity="0.2",
        last_executed_price="100",
        trade_id="perp-trade-visibility-1",
        exchange_order_id=maker.exchange_order_id,
    )
    events.append(fill_event)

    gateway.queue_submit(
        SimulatedSubmitBehavior(
            SimulatedSubmitKind.FULL_FILL,
            fill_price="100",
        )
    )
    order_executor = FundingOrderExecutor(
        market_data_gateway=market_data,
        account_gateway=OfflineAccount(),
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

    planned = worker.process_event(fill_event)

    assert len(planned) == 1
    assert planned[0].action_type == FundingCommandKind.SUBMIT_HEDGE.value
    assert planned[0].status is FundingActionStatus.PENDING
    persisted = funding.get_action(planned[0].action_id)
    assert persisted is not None
    assert persisted.status is FundingActionStatus.COMPLETED
    assert persisted.client_order_id is not None
    spot_order = orders.get(persisted.client_order_id)
    assert spot_order is not None
    assert spot_order.intent.instrument == SPOT
    assert spot_order.state is OrderState.FILLED
    assert spot_order.cumulative_quantity == Decimal("0.2")

    output = capsys.readouterr().out
    expected_chain = (
        "[FUNDING][EVENT] committed order event received",
        "[FUNDING][EVENT] funding order identified",
        "[FUNDING][CALC] hedge inputs",
        "[FUNDING][CALC] hedge result",
        "[FUNDING][DECISION] policy command",
        "[FUNDING][ACTION] durable action persisted",
        "[FUNDING][ACTION] dispatch requested",
        "[FUNDING][ACTION] action marked in progress",
        "[FUNDING][ORDER] preparing Spot MARKET hedge",
        "[FUNDING][ORDER] Spot hedge approved; submitting",
        "[FUNDING][ORDER] Spot hedge submit returned",
        "[FUNDING][ACTION] dispatch completed",
        "[FUNDING][ORDER] authoritative order state",
    )
    positions = [output.index(marker) for marker in expected_chain]
    assert positions == sorted(positions)
    assert "role=MAKER" in output
    assert "perp_filled=0.2" in output
    assert "tradable=0.2" in output
    assert "command=SUBMIT_HEDGE" in output
    assert "quantity=0.2" in output
    assert "state=FILLED" in output

    lowered_output = output.lower()
    for secret in secret_canaries.values():
        assert secret.lower() not in lowered_output
    assert "api_key" not in lowered_output
    assert "api_secret" not in lowered_output
    assert "webhook_url" not in lowered_output
