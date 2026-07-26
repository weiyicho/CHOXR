"""Prepare and explicitly submit Funding Rate entry legs.

The default command is always a preview. Exchange mutation additionally
requires ``--submit``, a matching ``--confirm-symbol`` and
``CHOXR_LIVE_TRADING=true``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from app import ApplicationContainer, ApplicationRuntime, Settings
from app.container import build_binance_container
from dotenv import load_dotenv
from engine.domain.account import AccountSnapshot
from engine.domain.instrument import InstrumentId, OrderBookLevel
from engine.domain.order import (
    OrderIntent,
    OrderRecord,
    OrderType,
    Side,
    TimeInForce,
)
from engine.domain.position import PositionSnapshot
from engine.execution import OrderExecutionService
from engine.planning import (
    MakerPriceParameters,
    MakerPricePolicy,
    MarketOrderPlan,
    MarketOrderPlanner,
    MarketOrderRequest,
    PriceQuote,
    SymbolNormalizer,
)
from engine.ports.market_data_gateway import MarketDataGateway
from engine.ports.trading_gateway import TradingGateway
from engine.risk import (
    PreTradeRiskCheck,
    RiskContext,
    RiskDecision,
    RiskLimits,
    available_quote_capital,
)

from .monitor import DEFAULT_ORDER_PLAN_PATH


DEFAULT_PLAN_MAX_AGE_SECONDS = 5_400
DEFAULT_RUNTIME_DIRECTORY = Path(__file__).resolve().parent / "runtime"
DEFAULT_ORDER_DATABASE_PATH = DEFAULT_RUNTIME_DIRECTORY / "orders.sqlite3"
QUOTE_ASSET = "USDT"
SPOT_MARKET_CAPITAL_BUFFER = Decimal("1.01")


class FundingOrderPlanError(ValueError):
    """The saved monitor plan cannot safely be used for order preparation."""


class FundingAccountGateway(Protocol):
    def get_account_snapshot(self) -> AccountSnapshot: ...

    def get_position_snapshot(
        self,
        instrument: InstrumentId,
    ) -> PositionSnapshot: ...

    def get_um_symbol_leverage(self, instrument: InstrumentId) -> int: ...

    def set_um_symbol_leverage(
        self,
        instrument: InstrumentId,
        leverage: int,
    ) -> int: ...


@dataclass(frozen=True)
class ReadyFundingOrderPlan:
    """Validated fields needed to prepare the two entry legs."""

    generated_at: datetime
    next_funding_at: datetime
    symbol: str
    capital: Decimal
    leverage: int
    spot_reference_price: Decimal
    spot_quantity: Decimal
    spot_notional: Decimal
    perpetual_reference_price: Decimal
    perpetual_quantity: Decimal
    perpetual_notional: Decimal
    perpetual_margin: Decimal

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None or self.next_funding_at.tzinfo is None:
            raise FundingOrderPlanError("plan timestamps must be timezone-aware")
        if not self.symbol:
            raise FundingOrderPlanError("plan symbol is required")
        for name in (
            "capital",
            "spot_reference_price",
            "spot_quantity",
            "spot_notional",
            "perpetual_reference_price",
            "perpetual_quantity",
            "perpetual_notional",
            "perpetual_margin",
        ):
            if getattr(self, name) <= 0:
                raise FundingOrderPlanError(f"{name} must be positive")
        if self.leverage <= 0:
            raise FundingOrderPlanError("leverage must be positive")
        if self.spot_quantity != self.perpetual_quantity:
            raise FundingOrderPlanError(
                "Spot and perpetual plan quantities must match"
            )
        capital_overrun = (
            self.spot_notional + self.perpetual_margin - self.capital
        )
        tolerance = max(
            Decimal("0.000000000001"),
            self.capital * Decimal("0.000000000001"),
        )
        if capital_overrun > tolerance:
            raise FundingOrderPlanError(
                "planned legs require more than the deployed capital"
            )

    @property
    def execution_id(self) -> str:
        digest = _stable_digest(self.generated_at.isoformat(), self.symbol)
        return f"fr-{digest[:20]}"

    @property
    def perpetual_client_order_id(self) -> str:
        digest = _stable_digest(self.execution_id, "perpetual-maker")
        return f"frp-{digest[:24]}"

    def spot_client_order_id(self, quantity: Decimal) -> str:
        digest = _stable_digest(
            self.execution_id,
            "spot-taker",
            format(quantity, "f"),
        )
        return f"frs-{digest[:24]}"


@dataclass(frozen=True)
class PreparedPerpetualMaker:
    plan: ReadyFundingOrderPlan
    intent: OrderIntent
    price_quote: PriceQuote
    order_notional: Decimal
    required_margin: Decimal
    observed_leverage: int
    risk_decision: RiskDecision


@dataclass(frozen=True)
class PreparedSpotTaker:
    plan: ReadyFundingOrderPlan
    market_order: MarketOrderPlan
    reference_price: Decimal
    order_notional: Decimal
    risk_decision: RiskDecision


@dataclass(frozen=True)
class PreparedSpotHedge:
    """One exact Spot hedge independent of the scanner's mutable plan file."""

    execution_id: str
    symbol: str
    market_order: MarketOrderPlan
    reference_price: Decimal
    order_notional: Decimal
    risk_decision: RiskDecision


class FundingOrderExecutor:
    """Compose existing market-data, planning, risk and execution components."""

    def __init__(
        self,
        *,
        market_data_gateway: MarketDataGateway,
        account_gateway: FundingAccountGateway,
        trading_gateway: TradingGateway,
        execution_service: OrderExecutionService,
        maker_price_policy: MakerPricePolicy | None = None,
        market_order_planner: MarketOrderPlanner | None = None,
        normalizer: SymbolNormalizer | None = None,
        risk_check: PreTradeRiskCheck | None = None,
    ) -> None:
        self._market_data = market_data_gateway
        self._account = account_gateway
        self._trading = trading_gateway
        self._execution = execution_service
        self._maker_price_policy = maker_price_policy or MakerPricePolicy()
        self._market_order_planner = (
            market_order_planner or MarketOrderPlanner()
        )
        self._normalizer = normalizer or SymbolNormalizer()
        self._risk = risk_check or PreTradeRiskCheck()

    def prepare_perpetual_maker(
        self,
        plan: ReadyFundingOrderPlan,
    ) -> PreparedPerpetualMaker:
        instrument = InstrumentId(
            "binance",
            "USD_M_PERPETUAL",
            plan.symbol,
        )
        observed_leverage = self._account.get_um_symbol_leverage(instrument)

        existing_position = self._account.get_position_snapshot(instrument)
        if not existing_position.is_flat:
            raise FundingOrderPlanError(
                f"{plan.symbol} already has a non-flat perpetual position"
            )
        open_orders = self._trading.list_open_orders(instrument)
        if open_orders:
            raise FundingOrderPlanError(
                f"{plan.symbol} already has {len(open_orders)} open "
                "perpetual order(s)"
            )

        rules = self._market_data.get_symbol_rules(instrument)
        if rules.quote_asset != QUOTE_ASSET:
            raise FundingOrderPlanError(
                f"{plan.symbol} quote asset must be {QUOTE_ASSET}"
            )
        order_book = self._market_data.get_order_book(instrument, depth=100)
        price_quote = self._maker_price_policy.quote(
            order_book,
            Side.SELL,
            rules,
            MakerPriceParameters(),
        )
        price = self._normalizer.normalize_maker_price(
            price_quote.desired_price,
            Side.SELL,
            order_book,
            rules,
        )
        quantity = self._normalizer.normalize_quantity(
            plan.perpetual_quantity,
            rules,
        )
        order_notional = self._normalizer.validate_notional(
            price,
            quantity,
            rules,
        )
        required_margin = order_notional / Decimal(plan.leverage)
        intent = OrderIntent(
            execution_id=plan.execution_id,
            client_order_id=plan.perpetual_client_order_id,
            instrument=instrument,
            side=Side.SELL,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=price,
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
            post_only=True,
            reason="funding_rate_perpetual_maker",
        )
        account = self._account.get_account_snapshot()
        risk_decision = self._risk.require_approved(
            intent,
            RiskContext(
                account=account,
                quote_asset=QUOTE_ASSET,
                current_gross_notional=_gross_notional(account),
                current_instrument_notional=Decimal("0"),
                required_capital=required_margin,
                available_capital=_available_margin(account),
            ),
            RiskLimits(
                max_order_notional=plan.capital,
                allowed_venues=("binance",),
                allowed_markets=("USD_M_PERPETUAL",),
            ),
        )
        return PreparedPerpetualMaker(
            plan=plan,
            intent=intent,
            price_quote=price_quote,
            order_notional=order_notional,
            required_margin=required_margin,
            observed_leverage=observed_leverage,
            risk_decision=risk_decision,
        )

    def prepare_spot_taker(
        self,
        plan: ReadyFundingOrderPlan,
        *,
        quantity: Decimal | int | str,
    ) -> PreparedSpotTaker:
        desired_quantity = Decimal(str(quantity))
        if desired_quantity <= 0:
            raise FundingOrderPlanError("Spot test quantity must be positive")
        if desired_quantity > plan.spot_quantity:
            raise FundingOrderPlanError(
                "Spot test quantity cannot exceed the planned Spot quantity"
            )

        instrument = InstrumentId("binance", "MARGIN", plan.symbol)
        rules = self._market_data.get_symbol_rules(instrument)
        if rules.quote_asset != QUOTE_ASSET:
            raise FundingOrderPlanError(
                f"{plan.symbol} quote asset must be {QUOTE_ASSET}"
            )
        normalized_test_quantity = self._normalizer.normalize_market_quantity(
            desired_quantity,
            rules,
        )
        market_order = self._market_order_planner.plan(
            MarketOrderRequest(
                execution_id=plan.execution_id,
                client_order_id=plan.spot_client_order_id(
                    normalized_test_quantity
                ),
                instrument=instrument,
                side=Side.BUY,
                desired_quantity=normalized_test_quantity,
                symbol_rules=rules,
                reason="funding_rate_spot_taker_test",
            )
        )
        order_book = self._market_data.get_order_book(instrument, depth=20)
        order_notional = _estimated_market_buy_notional(
            order_book.asks,
            market_order.normalized_quantity,
        )
        reference_price = (
            order_notional / market_order.normalized_quantity
        )
        order_notional = self._normalizer.validate_notional(
            reference_price,
            market_order.normalized_quantity,
            rules,
        )
        account = self._account.get_account_snapshot()
        available = available_quote_capital(account, QUOTE_ASSET)
        risk_decision = self._risk.require_approved(
            market_order.intent,
            RiskContext(
                account=account,
                quote_asset=QUOTE_ASSET,
                reference_price=reference_price,
                current_gross_notional=_gross_notional(account),
                current_instrument_notional=Decimal("0"),
                required_capital=(
                    order_notional * SPOT_MARKET_CAPITAL_BUFFER
                ),
                available_capital=available,
            ),
            RiskLimits(
                max_order_notional=plan.capital,
                allowed_venues=("binance",),
                allowed_markets=("MARGIN",),
            ),
        )
        return PreparedSpotTaker(
            plan=plan,
            market_order=market_order,
            reference_price=reference_price,
            order_notional=order_notional,
            risk_decision=risk_decision,
        )

    def prepare_spot_hedge(
        self,
        *,
        execution_id: str,
        client_order_id: str,
        symbol: str,
        quantity: Decimal | int | str,
        max_order_notional: Decimal | int | str,
    ) -> PreparedSpotHedge:
        """Prepare a durable event-driven Spot hedge.

        Unlike :meth:`prepare_spot_taker`, this method does not depend on the
        scanner's ``order_plan.json``. A running or restarted funding session
        provides the stable execution/action IDs and its persisted capital
        ceiling directly.
        """

        normalized_execution_id = execution_id.strip()
        normalized_client_order_id = client_order_id.strip()
        normalized_symbol = symbol.strip().upper()
        desired_quantity = Decimal(str(quantity))
        notional_limit = Decimal(str(max_order_notional))
        if not normalized_execution_id:
            raise FundingOrderPlanError("execution ID is required")
        if not normalized_client_order_id:
            raise FundingOrderPlanError("client order ID is required")
        if not normalized_symbol:
            raise FundingOrderPlanError("Spot hedge symbol is required")
        if desired_quantity <= 0:
            raise FundingOrderPlanError("Spot hedge quantity must be positive")
        if notional_limit <= 0:
            raise FundingOrderPlanError(
                "Spot hedge max order notional must be positive"
            )

        instrument = InstrumentId("binance", "MARGIN", normalized_symbol)
        rules = self._market_data.get_symbol_rules(instrument)
        if rules.quote_asset != QUOTE_ASSET:
            raise FundingOrderPlanError(
                f"{normalized_symbol} quote asset must be {QUOTE_ASSET}"
            )
        market_order = self._market_order_planner.plan(
            MarketOrderRequest(
                execution_id=normalized_execution_id,
                client_order_id=normalized_client_order_id,
                instrument=instrument,
                side=Side.BUY,
                desired_quantity=desired_quantity,
                symbol_rules=rules,
                reason="funding_rate_spot_hedge",
            )
        )
        order_book = self._market_data.get_order_book(instrument, depth=20)
        order_notional = _estimated_market_buy_notional(
            order_book.asks,
            market_order.normalized_quantity,
        )
        reference_price = order_notional / market_order.normalized_quantity
        order_notional = self._normalizer.validate_notional(
            reference_price,
            market_order.normalized_quantity,
            rules,
        )
        account = self._account.get_account_snapshot()
        available = available_quote_capital(account, QUOTE_ASSET)
        risk_decision = self._risk.require_approved(
            market_order.intent,
            RiskContext(
                account=account,
                quote_asset=QUOTE_ASSET,
                reference_price=reference_price,
                current_gross_notional=_gross_notional(account),
                current_instrument_notional=Decimal("0"),
                required_capital=(
                    order_notional * SPOT_MARKET_CAPITAL_BUFFER
                ),
                available_capital=available,
            ),
            RiskLimits(
                max_order_notional=notional_limit,
                allowed_venues=("binance",),
                allowed_markets=("MARGIN",),
            ),
        )
        return PreparedSpotHedge(
            execution_id=normalized_execution_id,
            symbol=normalized_symbol,
            market_order=market_order,
            reference_price=reference_price,
            order_notional=order_notional,
            risk_decision=risk_decision,
        )

    def submit_perpetual_maker(
        self,
        prepared: PreparedPerpetualMaker,
    ) -> OrderRecord:
        if not prepared.risk_decision.approved:
            raise RuntimeError("cannot submit a risk-rejected perpetual order")
        instrument = prepared.intent.instrument
        existing_position = self._account.get_position_snapshot(instrument)
        if not existing_position.is_flat:
            raise FundingOrderPlanError(
                f"{prepared.plan.symbol} acquired a perpetual position "
                "before submit"
            )
        open_orders = self._trading.list_open_orders(instrument)
        if open_orders:
            raise FundingOrderPlanError(
                f"{prepared.plan.symbol} acquired {len(open_orders)} open "
                "perpetual order(s) before submit"
            )

        current_leverage = self._account.get_um_symbol_leverage(instrument)
        if current_leverage != prepared.plan.leverage:
            self._account.set_um_symbol_leverage(
                instrument,
                prepared.plan.leverage,
            )
        confirmed_leverage = self._account.get_um_symbol_leverage(instrument)
        if confirmed_leverage != prepared.plan.leverage:
            raise FundingOrderPlanError(
                f"{prepared.plan.symbol} leverage verification returned "
                f"{confirmed_leverage}x after requesting "
                f"{prepared.plan.leverage}x; order was not submitted"
            )
        return self._execution.submit(prepared.intent)

    def submit_spot_taker(
        self,
        prepared: PreparedSpotTaker,
    ) -> OrderRecord:
        if not prepared.risk_decision.approved:
            raise RuntimeError("cannot submit a risk-rejected Spot order")
        return self._execution.submit(prepared.market_order.intent)

    def submit_spot_hedge(
        self,
        prepared: PreparedSpotHedge,
    ) -> OrderRecord:
        if not prepared.risk_decision.approved:
            raise RuntimeError("cannot submit a risk-rejected Spot hedge")
        return self._execution.submit(prepared.market_order.intent)


def load_funding_order_plan(
    path: str | Path = DEFAULT_ORDER_PLAN_PATH,
    *,
    now: datetime | None = None,
    max_age_seconds: int = DEFAULT_PLAN_MAX_AGE_SECONDS,
) -> ReadyFundingOrderPlan:
    """Load the latest monitor snapshot and reject stale or malformed plans."""

    if max_age_seconds <= 0:
        raise ValueError("max_age_seconds must be positive")
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FundingOrderPlanError(f"order plan does not exist: {source}") from exc
    except json.JSONDecodeError as exc:
        raise FundingOrderPlanError(f"order plan is invalid JSON: {source}") from exc

    root = _mapping(payload, "order plan")
    if root.get("schema_version") != 1:
        raise FundingOrderPlanError("unsupported order-plan schema")
    if root.get("status") != "READY":
        raise FundingOrderPlanError(
            f"order plan is not READY: {root.get('status', 'UNKNOWN')}"
        )
    selected_symbols = root.get("selected_symbols")
    if (
        not isinstance(selected_symbols, list)
        or len(selected_symbols) != 1
        or not isinstance(selected_symbols[0], str)
    ):
        raise FundingOrderPlanError(
            "READY order plan must contain exactly one selected symbol"
        )

    candidate = _mapping(root.get("candidate"), "candidate")
    allocation = _mapping(root.get("allocation"), "allocation")
    capital = _mapping(allocation.get("capital"), "allocation.capital")
    spot_leg = _mapping(allocation.get("spot_leg"), "allocation.spot_leg")
    perpetual_leg = _mapping(
        allocation.get("perpetual_leg"),
        "allocation.perpetual_leg",
    )
    symbol = str(candidate.get("symbol", "")).strip().upper()
    if selected_symbols[0].strip().upper() != symbol:
        raise FundingOrderPlanError(
            "selected symbol does not match candidate symbol"
        )
    if (
        spot_leg.get("market") != "MARGIN"
        or spot_leg.get("side") != "BUY"
        or perpetual_leg.get("market") != "USD_M_PERPETUAL"
        or perpetual_leg.get("side") != "SELL"
    ):
        raise FundingOrderPlanError("order-plan leg direction is invalid")

    generated_at = _timestamp(root.get("generated_at"), "generated_at")
    next_funding_at = _timestamp(
        candidate.get("next_funding_at"),
        "candidate.next_funding_at",
    )
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    age_seconds = (current - generated_at).total_seconds()
    if age_seconds < -60:
        raise FundingOrderPlanError("order plan timestamp is in the future")
    if age_seconds > max_age_seconds:
        raise FundingOrderPlanError(
            f"order plan is stale ({age_seconds:.0f}s old)"
        )
    if current >= next_funding_at:
        raise FundingOrderPlanError(
            "order plan has passed its next funding timestamp"
        )

    leverage_decimal = _decimal(
        perpetual_leg.get("leverage"),
        "allocation.perpetual_leg.leverage",
    )
    leverage = int(leverage_decimal)
    if leverage_decimal != Decimal(leverage):
        raise FundingOrderPlanError("planned leverage must be a whole number")

    return ReadyFundingOrderPlan(
        generated_at=generated_at,
        next_funding_at=next_funding_at,
        symbol=symbol,
        capital=_decimal(capital.get("deployed"), "allocation.capital.deployed"),
        leverage=leverage,
        spot_reference_price=_decimal(
            spot_leg.get("reference_price"),
            "allocation.spot_leg.reference_price",
        ),
        spot_quantity=_decimal(
            spot_leg.get("quantity"),
            "allocation.spot_leg.quantity",
        ),
        spot_notional=_decimal(
            spot_leg.get("notional"),
            "allocation.spot_leg.notional",
        ),
        perpetual_reference_price=_decimal(
            perpetual_leg.get("reference_price"),
            "allocation.perpetual_leg.reference_price",
        ),
        perpetual_quantity=_decimal(
            perpetual_leg.get("quantity"),
            "allocation.perpetual_leg.quantity",
        ),
        perpetual_notional=_decimal(
            perpetual_leg.get("notional"),
            "allocation.perpetual_leg.notional",
        ),
        perpetual_margin=_decimal(
            perpetual_leg.get("initial_margin"),
            "allocation.perpetual_leg.initial_margin",
        ),
    )


def build_funding_order_executor(
    container: ApplicationContainer,
) -> FundingOrderExecutor:
    return FundingOrderExecutor(
        market_data_gateway=container.market_data_gateway,
        account_gateway=container.account_gateway,
        trading_gateway=container.trading_gateway,
        execution_service=container.execution_service,
    )


def validate_plan_settings(
    plan: ReadyFundingOrderPlan,
    settings: Settings,
) -> None:
    """Require a fresh monitor run after capital or leverage is reconfigured."""

    if plan.capital != settings.funding_capital:
        raise FundingOrderPlanError(
            f"order plan capital is {plan.capital}, but current setting is "
            f"{settings.funding_capital}; rerun the funding monitor"
        )
    if plan.leverage != settings.funding_leverage:
        raise FundingOrderPlanError(
            f"order plan leverage is {plan.leverage}x, but current setting is "
            f"{settings.funding_leverage}x; rerun the funding monitor"
        )


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FundingOrderPlanError(f"{name} must be an object")
    return value


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FundingOrderPlanError(f"{name} must be a decimal") from exc
    if not result.is_finite():
        raise FundingOrderPlanError(f"{name} must be finite")
    return result


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise FundingOrderPlanError(f"{name} must be an ISO timestamp")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise FundingOrderPlanError(f"{name} must be an ISO timestamp") from exc
    if result.tzinfo is None:
        raise FundingOrderPlanError(f"{name} must be timezone-aware")
    return result


def _stable_digest(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def _available_margin(account: AccountSnapshot) -> Decimal:
    if account.available_margin is not None:
        return account.available_margin
    return available_quote_capital(account, QUOTE_ASSET)


def _gross_notional(account: AccountSnapshot) -> Decimal:
    return sum(
        (
            abs(position.quantity) * position.mark_price
            for position in account.positions
            if position.mark_price is not None
        ),
        Decimal("0"),
    )


def _estimated_market_buy_notional(
    asks: Sequence[OrderBookLevel],
    quantity: Decimal,
) -> Decimal:
    remaining = quantity
    notional = Decimal("0")
    for level in asks:
        filled = min(remaining, level.quantity)
        notional += filled * level.price
        remaining -= filled
        if remaining == 0:
            return notional
    raise FundingOrderPlanError(
        "visible Spot ask depth cannot cover the requested test quantity"
    )


def prepared_order_payload(
    prepared: PreparedPerpetualMaker | PreparedSpotTaker,
    *,
    mode: str,
    order: OrderRecord | None = None,
) -> dict[str, object]:
    if isinstance(prepared, PreparedPerpetualMaker):
        intent = prepared.intent
        payload: dict[str, object] = {
            "mode": mode,
            "leg": "PERPETUAL_MAKER",
            "symbol": prepared.plan.symbol,
            "client_order_id": intent.client_order_id,
            "side": intent.side.value,
            "order_type": intent.order_type.value,
            "post_only": intent.post_only,
            "price": str(intent.price),
            "quantity": str(intent.quantity),
            "notional": str(prepared.order_notional),
            "required_margin": str(prepared.required_margin),
            "account_leverage_before_submit": prepared.observed_leverage,
            "target_leverage": prepared.plan.leverage,
            "leverage_change_required": (
                prepared.observed_leverage != prepared.plan.leverage
            ),
            "risk": "APPROVED",
        }
        if order is not None:
            payload["account_leverage_after_submit"] = prepared.plan.leverage
    else:
        intent = prepared.market_order.intent
        payload = {
            "mode": mode,
            "leg": "SPOT_TAKER_TEST",
            "symbol": prepared.plan.symbol,
            "client_order_id": intent.client_order_id,
            "side": intent.side.value,
            "order_type": intent.order_type.value,
            "quantity": str(intent.quantity),
            "reference_price": str(prepared.reference_price),
            "notional": str(prepared.order_notional),
            "risk": "APPROVED",
        }
    if order is not None:
        payload.update(
            {
                "state": order.state.value,
                "exchange_order_id": order.exchange_order_id,
                "cumulative_quantity": str(order.cumulative_quantity),
                "average_price": (
                    None
                    if order.average_price is None
                    else str(order.average_price)
                ),
            }
        )
    return payload


def _order_record_payload(
    order: OrderRecord,
    *,
    mode: str,
    action: str,
) -> dict[str, object]:
    return {
        "mode": mode,
        "action": action,
        "symbol": order.intent.instrument.symbol,
        "market": order.intent.instrument.market,
        "client_order_id": order.intent.client_order_id,
        "exchange_order_id": order.exchange_order_id,
        "side": order.intent.side.value,
        "order_type": order.intent.order_type.value,
        "price": (
            None if order.intent.price is None else str(order.intent.price)
        ),
        "quantity": str(order.intent.quantity),
        "state": order.state.value,
        "cumulative_quantity": str(order.cumulative_quantity),
        "average_price": (
            None if order.average_price is None else str(order.average_price)
        ),
    }


def _require_live_confirmation(
    settings: Settings,
    *,
    expected_symbol: str,
    confirmed_symbol: str | None,
) -> None:
    settings.require_live_trading()
    if (confirmed_symbol or "").strip().upper() != expected_symbol:
        raise RuntimeError(
            f"live submit requires --confirm-symbol {expected_symbol}"
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
    subparsers = parser.add_subparsers(dest="command", required=True)

    perpetual = subparsers.add_parser(
        "perp-maker",
        help=(
            "preview or submit the saved plan's perpetual maker SELL; "
            "submit aligns Binance leverage first"
        ),
    )
    perpetual.add_argument("--submit", action="store_true")
    perpetual.add_argument("--confirm-symbol")

    spot = subparsers.add_parser(
        "spot-taker",
        help="preview or submit a manual Spot MARKET BUY test",
    )
    spot.add_argument("--quantity", required=True)
    spot.add_argument("--submit", action="store_true")
    spot.add_argument("--confirm-symbol")

    status = subparsers.add_parser(
        "order-status",
        help="reconcile one persisted order by client order ID",
    )
    status.add_argument("--client-order-id", required=True)

    cancel = subparsers.add_parser(
        "cancel-order",
        help="preview or submit cancellation of one persisted open order",
    )
    cancel.add_argument("--client-order-id", required=True)
    cancel.add_argument("--submit", action="store_true")
    cancel.add_argument("--confirm-symbol")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    load_dotenv()
    settings = Settings.from_environment()
    try:
        plan: ReadyFundingOrderPlan | None = None
        if args.command in {"perp-maker", "spot-taker"}:
            plan = load_funding_order_plan(args.plan_path)
            validate_plan_settings(plan, settings)
        if (
            plan is not None
            and args.submit
        ):
            _require_live_confirmation(
                settings,
                expected_symbol=plan.symbol,
                confirmed_symbol=args.confirm_symbol,
            )

        args.database_path.parent.mkdir(parents=True, exist_ok=True)
        container = build_binance_container(
            settings,
            database_path=args.database_path,
        )
        if args.command in {"order-status", "cancel-order"}:
            local_order = container.order_repository.get(args.client_order_id)
            if local_order is None:
                raise LookupError(
                    f"local order does not exist: {args.client_order_id}"
                )
            if args.command == "cancel-order" and args.submit:
                _require_live_confirmation(
                    settings,
                    expected_symbol=local_order.intent.instrument.symbol,
                    confirmed_symbol=args.confirm_symbol,
                )

        ApplicationRuntime(container).preflight()
        if args.command == "order-status":
            order = container.execution_service.reconcile(
                args.client_order_id
            )
            print(
                json.dumps(
                    _order_record_payload(
                        order,
                        mode="READ_ONLY",
                        action="RECONCILED",
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "cancel-order":
            order = (
                container.execution_service.cancel(args.client_order_id)
                if args.submit
                else local_order
            )
            print(
                json.dumps(
                    _order_record_payload(
                        order,
                        mode="SUBMITTED" if args.submit else "PREVIEW",
                        action="CANCEL",
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        assert plan is not None
        executor = build_funding_order_executor(container)

        if args.command == "perp-maker":
            prepared = executor.prepare_perpetual_maker(plan)
            order = (
                executor.submit_perpetual_maker(prepared)
                if args.submit
                else None
            )
        else:
            prepared = executor.prepare_spot_taker(
                plan,
                quantity=args.quantity,
            )
            order = (
                executor.submit_spot_taker(prepared)
                if args.submit
                else None
            )
        print(
            json.dumps(
                prepared_order_payload(
                    prepared,
                    mode="SUBMITTED" if args.submit else "PREVIEW",
                    order=order,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (FundingOrderPlanError, LookupError, RuntimeError, ValueError) as exc:
        print(f"Funding order stopped: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
