from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

import strategies.funding_rate.order as order_module
from adapters.persistence import InMemoryOrderRepository
from adapters.simulation import (
    SimulatedSubmitBehavior,
    SimulatedSubmitKind,
    SimulatedTradingGateway,
)
from app.settings import Settings
from engine.domain.account import AccountSnapshot, BalanceSnapshot
from engine.domain.instrument import (
    InstrumentId,
    OrderBookLevel,
    OrderBookSnapshot,
    SymbolRules,
)
from engine.domain.order import OrderIntent, OrderState, OrderType, Side
from engine.domain.position import PositionSnapshot
from engine.execution import OrderExecutionService
from strategies.funding_rate import FundingCandidate
from strategies.funding_rate.monitor import (
    FundingScanReport,
    build_funding_order_plan,
    write_funding_order_plan,
)
from strategies.funding_rate.order import (
    FundingOrderExecutor,
    FundingOrderPlanError,
    ReadyFundingOrderPlan,
    load_funding_order_plan,
    validate_plan_settings,
)


NOW = datetime(2027, 1, 1, tzinfo=timezone.utc)


def candidate() -> FundingCandidate:
    return FundingCandidate(
        symbol="ETHUSDT",
        funding_rate="0.00020",
        funding_interval_hours=8,
        next_funding_at=NOW + timedelta(hours=8),
        mark_price="100.1",
        index_price="100",
        quote_volume_24h="50000000",
        spot_ask="100",
        perpetual_bid="100.25",
    )


def saved_ready_plan(tmp_path: Path) -> tuple[Path, ReadyFundingOrderPlan]:
    path = tmp_path / "order_plan.json"
    payload = build_funding_order_plan(
        FundingScanReport(NOW, 1, (candidate(),)),
        available_capital="50",
        futures_leverage="5",
    )
    write_funding_order_plan(payload, path)
    return path, load_funding_order_plan(
        path,
        now=NOW + timedelta(minutes=1),
    )


class FakeMarketDataGateway:
    def get_symbol_rules(self, instrument: InstrumentId) -> SymbolRules:
        return SymbolRules(
            instrument=instrument,
            base_asset="ETH",
            quote_asset="USDT",
            price_increment="0.1",
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
        if instrument.market == "MARGIN":
            bids = (OrderBookLevel("99.9", "10"),)
            asks = (OrderBookLevel("100", "10"),)
        else:
            bids = (OrderBookLevel("100", "10"),)
            asks = (OrderBookLevel("101", "10"),)
        return OrderBookSnapshot(instrument, bids=bids, asks=asks)


class ShallowSpotMarketDataGateway(FakeMarketDataGateway):
    def get_order_book(
        self,
        instrument: InstrumentId,
        depth: int | None = None,
    ) -> OrderBookSnapshot:
        if instrument.market != "MARGIN":
            return super().get_order_book(instrument, depth)
        return OrderBookSnapshot(
            instrument,
            bids=(OrderBookLevel("99.9", "1"),),
            asks=(OrderBookLevel("100", "0.01"),),
        )


class FakeAccountGateway:
    def __init__(
        self,
        *,
        leverage: int = 5,
        perpetual_quantity: str = "0",
        apply_leverage_changes: bool = True,
    ) -> None:
        self.leverage = leverage
        self.perpetual_quantity = Decimal(perpetual_quantity)
        self.apply_leverage_changes = apply_leverage_changes
        self.leverage_changes: list[tuple[InstrumentId, int]] = []
        self.account = AccountSnapshot(
            venue="binance",
            balances=(BalanceSnapshot("USDT", "100", "100"),),
            available_margin="100",
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        return self.account

    def get_position_snapshot(
        self,
        instrument: InstrumentId,
    ) -> PositionSnapshot:
        return PositionSnapshot(
            instrument=instrument,
            quantity=self.perpetual_quantity,
        )

    def get_um_symbol_leverage(self, instrument: InstrumentId) -> int:
        return self.leverage

    def set_um_symbol_leverage(
        self,
        instrument: InstrumentId,
        leverage: int,
    ) -> int:
        self.leverage_changes.append((instrument, leverage))
        if self.apply_leverage_changes:
            self.leverage = leverage
        return self.leverage


def executor(
    *,
    account: FakeAccountGateway | None = None,
    trading: SimulatedTradingGateway | None = None,
) -> tuple[FundingOrderExecutor, SimulatedTradingGateway]:
    gateway = trading or SimulatedTradingGateway()
    service = OrderExecutionService(gateway, InMemoryOrderRepository())
    return (
        FundingOrderExecutor(
            market_data_gateway=FakeMarketDataGateway(),
            account_gateway=account or FakeAccountGateway(),
            trading_gateway=gateway,
            execution_service=service,
        ),
        gateway,
    )


def test_ready_plan_loader_validates_and_builds_stable_ids(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)

    assert plan.symbol == "ETHUSDT"
    assert plan.capital == Decimal("50")
    assert plan.leverage == 5
    assert plan.spot_quantity == plan.perpetual_quantity
    assert plan.execution_id == plan.execution_id
    assert len(plan.perpetual_client_order_id) <= 32


def test_loader_rejects_no_candidate_and_stale_plans(tmp_path: Path) -> None:
    path = tmp_path / "order_plan.json"
    no_candidate = build_funding_order_plan(FundingScanReport(NOW, 1, ()))
    write_funding_order_plan(no_candidate, path)

    with pytest.raises(FundingOrderPlanError, match="not READY"):
        load_funding_order_plan(path, now=NOW)

    ready = build_funding_order_plan(
        FundingScanReport(NOW, 1, (candidate(),))
    )
    write_funding_order_plan(ready, path)
    with pytest.raises(FundingOrderPlanError, match="stale"):
        load_funding_order_plan(
            path,
            now=NOW + timedelta(hours=2),
            max_age_seconds=3_600,
        )


def test_order_plan_must_match_current_capital_and_leverage_settings(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)

    validate_plan_settings(
        plan,
        Settings("", "", funding_capital="50", funding_leverage=5),
    )
    with pytest.raises(FundingOrderPlanError, match="rerun"):
        validate_plan_settings(
            plan,
            Settings("", "", funding_capital="75", funding_leverage=5),
        )


def test_perpetual_preview_is_post_only_sell_and_does_not_submit(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    funding_executor, gateway = executor()

    prepared = funding_executor.prepare_perpetual_maker(plan)

    assert prepared.intent.side is Side.SELL
    assert prepared.intent.order_type is OrderType.LIMIT
    assert prepared.intent.post_only is True
    assert prepared.intent.price == Decimal("101")
    assert prepared.intent.quantity == Decimal("0.416")
    assert prepared.observed_leverage == 5
    assert prepared.risk_decision.approved is True
    assert gateway.submit_calls == 0


def test_perpetual_preview_reports_leverage_change_without_mutation(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    account = FakeAccountGateway(leverage=3)
    funding_executor, _ = executor(
        account=account
    )

    prepared = funding_executor.prepare_perpetual_maker(plan)

    assert prepared.observed_leverage == 3
    assert prepared.required_margin == Decimal("8.4032")
    assert account.leverage_changes == []


def test_perpetual_submit_changes_and_verifies_leverage_before_order(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    account = FakeAccountGateway(leverage=13)
    funding_executor, gateway = executor(account=account)

    prepared = funding_executor.prepare_perpetual_maker(plan)
    order = funding_executor.submit_perpetual_maker(prepared)

    assert account.leverage == 5
    assert account.leverage_changes == [
        (prepared.intent.instrument, 5),
    ]
    assert gateway.submit_calls == 1
    assert order.state is OrderState.NEW


def test_perpetual_submit_stops_if_changed_leverage_cannot_be_verified(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    account = FakeAccountGateway(
        leverage=13,
        apply_leverage_changes=False,
    )
    funding_executor, gateway = executor(account=account)
    prepared = funding_executor.prepare_perpetual_maker(plan)

    with pytest.raises(
        FundingOrderPlanError,
        match="verification returned 13x.*5x",
    ):
        funding_executor.submit_perpetual_maker(prepared)

    assert account.leverage_changes == [
        (prepared.intent.instrument, 5),
    ]
    assert gateway.submit_calls == 0


def test_perpetual_preview_rejects_existing_position_or_order(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    with_position, _ = executor(
        account=FakeAccountGateway(perpetual_quantity="-0.1")
    )
    with pytest.raises(FundingOrderPlanError, match="non-flat"):
        with_position.prepare_perpetual_maker(plan)

    gateway = SimulatedTradingGateway()
    gateway.submit_order(
        OrderIntent(
            execution_id="other",
            client_order_id="other-perpetual-order",
            instrument=InstrumentId(
                "binance",
                "USD_M_PERPETUAL",
                "ETHUSDT",
            ),
            side=Side.SELL,
            quantity="0.01",
            order_type=OrderType.LIMIT,
            price="101",
            post_only=True,
        )
    )
    with_order, _ = executor(trading=gateway)
    with pytest.raises(FundingOrderPlanError, match="open perpetual"):
        with_order.prepare_perpetual_maker(plan)


def test_spot_taker_preview_uses_exact_normalized_test_quantity(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    funding_executor, gateway = executor()

    prepared = funding_executor.prepare_spot_taker(
        plan,
        quantity="0.0559",
    )
    same_normalized_order = funding_executor.prepare_spot_taker(
        plan,
        quantity="0.0558",
    )

    assert prepared.market_order.intent.side is Side.BUY
    assert prepared.market_order.intent.order_type is OrderType.MARKET
    assert prepared.market_order.intent.quantity == Decimal("0.055")
    assert prepared.order_notional == Decimal("5.500")
    assert prepared.risk_decision.required_capital == Decimal("5.55500")
    assert prepared.risk_decision.approved is True
    assert (
        prepared.market_order.intent.client_order_id
        == same_normalized_order.market_order.intent.client_order_id
    )
    assert gateway.submit_calls == 0


def test_spot_taker_rejects_quantity_beyond_visible_ask_depth(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    gateway = SimulatedTradingGateway()
    funding_executor = FundingOrderExecutor(
        market_data_gateway=ShallowSpotMarketDataGateway(),
        account_gateway=FakeAccountGateway(),
        trading_gateway=gateway,
        execution_service=OrderExecutionService(
            gateway,
            InMemoryOrderRepository(),
        ),
    )

    with pytest.raises(FundingOrderPlanError, match="ask depth"):
        funding_executor.prepare_spot_taker(plan, quantity="0.055")


def test_spot_taker_cannot_exceed_planned_quantity(tmp_path: Path) -> None:
    _, plan = saved_ready_plan(tmp_path)
    funding_executor, _ = executor()

    with pytest.raises(FundingOrderPlanError, match="cannot exceed"):
        funding_executor.prepare_spot_taker(plan, quantity="1")


def test_event_driven_spot_hedge_uses_durable_ids_without_plan_file() -> None:
    funding_executor, gateway = executor()

    prepared = funding_executor.prepare_spot_hedge(
        execution_id="funding-session-1",
        client_order_id="frh-action-1",
        symbol="ethusdt",
        quantity="0.0559",
        max_order_notional="50",
    )

    assert prepared.execution_id == "funding-session-1"
    assert prepared.symbol == "ETHUSDT"
    assert prepared.market_order.intent.client_order_id == "frh-action-1"
    assert prepared.market_order.intent.quantity == Decimal("0.055")
    assert prepared.market_order.intent.side is Side.BUY
    assert prepared.market_order.intent.reason == "funding_rate_spot_hedge"
    assert prepared.order_notional == Decimal("5.500")
    assert prepared.risk_decision.approved is True
    assert gateway.submit_calls == 0

    gateway.queue_submit(
        SimulatedSubmitBehavior(SimulatedSubmitKind.FULL_FILL, "100")
    )
    submitted = funding_executor.submit_spot_hedge(prepared)
    assert submitted.state is OrderState.FILLED
    assert submitted.cumulative_quantity == Decimal("0.055")
    assert gateway.submit_calls == 1


def test_manual_perpetual_and_spot_submissions_use_execution_service(
    tmp_path: Path,
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    funding_executor, gateway = executor()

    perpetual = funding_executor.submit_perpetual_maker(
        funding_executor.prepare_perpetual_maker(plan)
    )
    gateway.queue_submit(
        SimulatedSubmitBehavior(SimulatedSubmitKind.FULL_FILL, "100")
    )
    spot = funding_executor.submit_spot_taker(
        funding_executor.prepare_spot_taker(plan, quantity="0.055")
    )

    assert perpetual.state is OrderState.NEW
    assert spot.state is OrderState.FILLED
    assert spot.cumulative_quantity == Decimal("0.055")
    assert gateway.submit_calls == 2


def test_cli_submit_stops_before_network_when_live_trading_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, plan = saved_ready_plan(tmp_path)
    events: list[str] = []
    monkeypatch.setattr(order_module, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        order_module.Settings,
        "from_environment",
        classmethod(
            lambda cls: Settings(
                "key",
                "secret",
                live_trading_enabled=False,
            )
        ),
    )
    monkeypatch.setattr(
        order_module,
        "load_funding_order_plan",
        lambda path: plan,
    )
    monkeypatch.setattr(
        order_module,
        "build_binance_container",
        lambda *args, **kwargs: events.append("network") or None,
    )

    result = order_module.main(
        [
            "--plan-path",
            str(tmp_path / "unused.json"),
            "perp-maker",
            "--submit",
            "--confirm-symbol",
            "ETHUSDT",
        ]
    )

    assert result == 2
    assert events == []
    assert "live trading is disabled" in capsys.readouterr().out
