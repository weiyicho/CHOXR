from __future__ import annotations

from engine.domain.account import AccountSnapshot, BalanceSnapshot
from engine.domain.instrument import InstrumentId
from engine.domain.position import PositionSnapshot

from ..account_mode import verify_account_mode
from ..api.account_profile import PortfolioAccountProfileApi
from ..api.portfolio_margin import PortfolioMarginApi
from ..config import BinanceAccountMode
from ..parsers.accounts import parse_account, parse_balances, parse_funding_income
from ..parsers.positions import parse_um_positions
from ..transport.errors import UnknownExecutionOutcome
from .market_data_gateway import BinanceMarketDataGateway, _market_family


class ClassicPortfolioMarginAccountGateway:
    def __init__(
        self,
        api: PortfolioMarginApi,
        market_data: BinanceMarketDataGateway,
        account_profile_api: PortfolioAccountProfileApi | None = None,
    ) -> None:
        self._api = api
        self._market_data = market_data
        self._account_profile_api = account_profile_api

    def verify_configured_mode(
        self,
        configured: BinanceAccountMode,
    ) -> BinanceAccountMode:
        """Read-only startup preflight with no endpoint fallback.

        PAPI's account response does not expose ``accountType``.  The SAPI
        portfolio profile is therefore the discriminator, while a separate
        PAPI account read verifies that the Classic PM account plane is
        available before runtime starts.
        """

        if self._account_profile_api is None:
            raise RuntimeError(
                "account_profile_api is required for account-mode preflight"
            )
        profile = self._account_profile_api.get_account_profile()
        observed = verify_account_mode(configured, profile)
        if observed is not BinanceAccountMode.CLASSIC_PORTFOLIO_MARGIN:
            raise RuntimeError("Classic Portfolio Margin gateway requires PM_2")
        self._api.get_account()
        return observed

    def get_account_snapshot(self) -> AccountSnapshot:
        native_account = parse_account(self._api.get_account())
        native_balances = parse_balances(self._api.get_balances())
        native_positions = parse_um_positions(self._api.get_um_positions())
        balances = tuple(
            BalanceSnapshot(
                asset=item.asset,
                total=item.total_wallet_balance,
                available=item.cross_margin_free,
                locked=item.cross_margin_locked,
                borrowed=item.cross_margin_borrowed + item.cross_margin_interest,
            )
            for item in native_balances
        )
        positions = tuple(
            PositionSnapshot(
                instrument=InstrumentId(
                    venue="binance",
                    market="USD_M_FUTURES",
                    symbol=item.symbol,
                ),
                quantity=item.quantity,
                average_entry_price=item.entry_price,
                mark_price=item.mark_price,
                unrealized_pnl=item.unrealized_pnl,
            )
            for item in native_positions
        )
        return AccountSnapshot(
            venue="binance",
            balances=balances,
            positions=positions,
            equity=native_account.account_equity,
            available_margin=native_account.available_balance,
        )

    def get_position_snapshot(self, instrument: InstrumentId) -> PositionSnapshot:
        family = _market_family(instrument)
        if family == "UM":
            positions = parse_um_positions(
                self._api.get_um_positions(instrument.symbol)
            )
            matching = next(
                (
                    item
                    for item in positions
                    if item.symbol == instrument.symbol and item.position_side == "BOTH"
                ),
                None,
            )
            if matching is None:
                return PositionSnapshot(instrument=instrument)
            return PositionSnapshot(
                instrument=instrument,
                quantity=matching.quantity,
                average_entry_price=matching.entry_price,
                mark_price=matching.mark_price,
                unrealized_pnl=matching.unrealized_pnl,
            )

        rules = self._market_data.get_symbol_rules(instrument)
        balances = parse_balances(self._api.get_balances(rules.base_asset))
        matching_balance = next(
            (item for item in balances if item.asset == rules.base_asset), None
        )
        if matching_balance is None:
            return PositionSnapshot(instrument=instrument)
        net_quantity = (
            matching_balance.cross_margin_free
            + matching_balance.cross_margin_locked
            - matching_balance.cross_margin_borrowed
            - matching_balance.cross_margin_interest
        )
        return PositionSnapshot(instrument=instrument, quantity=net_quantity)

    def is_one_way_mode(self) -> bool:
        return not bool(self._api.get_um_position_mode().get("dualSidePosition"))

    def get_um_symbol_leverage(self, instrument: InstrumentId) -> int:
        """Return the configured leverage without mutating account settings."""

        if _market_family(instrument) != "UM":
            raise ValueError("leverage is only available for USD-M instruments")
        configurations = self._api.get_um_symbol_config(instrument.symbol)
        matching = next(
            (
                item
                for item in configurations
                if str(item.get("symbol", "")).upper()
                == instrument.symbol.upper()
            ),
            None,
        )
        if matching is None:
            raise LookupError(
                f"USD-M symbol configuration is unavailable for {instrument.symbol}"
            )
        try:
            leverage = int(matching["leverage"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid leverage configuration for {instrument.symbol}"
            ) from exc
        if leverage <= 0:
            raise ValueError(
                f"invalid leverage configuration for {instrument.symbol}"
            )
        return leverage

    def set_um_symbol_leverage(
        self,
        instrument: InstrumentId,
        leverage: int,
    ) -> int:
        """Set one USD-M symbol's initial leverage and return Binance's value.

        A transport timeout has an uncertain write outcome. Because setting a
        fixed leverage is idempotent, reconcile it through the read-only symbol
        configuration before deciding whether the operation failed.
        """

        if _market_family(instrument) != "UM":
            raise ValueError("leverage is only available for USD-M instruments")
        if isinstance(leverage, bool) or not isinstance(leverage, int):
            raise ValueError("leverage must be a whole number")
        if not 1 <= leverage <= 125:
            raise ValueError("leverage must be between 1 and 125")
        try:
            response = self._api.change_um_initial_leverage(
                symbol=instrument.symbol,
                leverage=leverage,
            )
        except UnknownExecutionOutcome:
            if self.get_um_symbol_leverage(instrument) == leverage:
                return leverage
            raise

        try:
            observed_symbol = str(response["symbol"]).upper()
            observed_leverage = int(response["leverage"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid leverage response for {instrument.symbol}"
            ) from exc
        if (
            observed_symbol != instrument.symbol.upper()
            or observed_leverage != leverage
        ):
            raise ValueError(
                f"Binance did not confirm {instrument.symbol} leverage "
                f"at {leverage}x"
            )
        return observed_leverage

    def list_funding_income(self, **filters: object):
        return parse_funding_income(self._api.list_funding_income(**filters))

    def collect_futures_funds(self) -> dict[str, object]:
        return self._api.collect_futures_funds()
