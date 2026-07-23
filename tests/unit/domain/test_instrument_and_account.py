from decimal import Decimal

import pytest

from engine.domain import (
    AccountSnapshot,
    BalanceSnapshot,
    InstrumentId,
    OrderBookLevel,
    OrderBookSnapshot,
    PositionSnapshot,
    SymbolRules,
)


def instrument(venue: str = "any-venue") -> InstrumentId:
    return InstrumentId(venue=venue, market="PERPETUAL", symbol="ETH-USD")


def test_instrument_identity_does_not_require_a_known_exchange_or_market() -> None:
    result = InstrumentId("future-exchange", "NEW_MARKET_KIND", "ABC-XYZ")

    assert result.venue == "future-exchange"
    assert result.market == "NEW_MARKET_KIND"
    assert result.symbol == "ABC-XYZ"


def test_order_book_requires_canonical_price_ordering() -> None:
    book = OrderBookSnapshot(
        instrument(),
        bids=(OrderBookLevel("99", "2"), OrderBookLevel("98", "3")),
        asks=(OrderBookLevel("101", "4"), OrderBookLevel("102", "1")),
    )

    assert book.best_bid.price == Decimal("99")
    assert book.best_ask.price == Decimal("101")

    with pytest.raises(ValueError, match="bids must be ordered"):
        OrderBookSnapshot(
            instrument(),
            bids=(OrderBookLevel("98", "2"), OrderBookLevel("99", "3")),
            asks=(),
        )


def test_symbol_rules_expose_generic_and_exchange_familiar_names() -> None:
    rules = SymbolRules(
        instrument=instrument(),
        base_asset="ETH",
        quote_asset="USD",
        price_increment="0.01",
        quantity_increment="0.001",
        min_quantity="0.001",
        min_notional="5",
    )

    assert rules.price_increment == Decimal("0.01")
    assert rules.quantity_increment == Decimal("0.001")
    assert rules.tick_size == rules.price_increment
    assert rules.step_size == rules.quantity_increment


def test_symbol_rules_expose_distinct_market_quantity_constraints() -> None:
    rules = SymbolRules(
        instrument=instrument(),
        base_asset="ETH",
        quote_asset="USD",
        price_increment="0.01",
        quantity_increment="0.001",
        min_quantity="0.001",
        max_quantity="100",
        market_quantity_increment="0.01",
        market_min_quantity="0.02",
        market_max_quantity="10",
        trading_enabled=False,
    )

    assert rules.effective_market_quantity_increment == Decimal("0.01")
    assert rules.effective_market_min_quantity == Decimal("0.02")
    assert rules.effective_market_max_quantity == Decimal("10")
    assert rules.trading_enabled is False


def test_market_quantity_constraints_fall_back_to_general_constraints() -> None:
    rules = SymbolRules(
        instrument=instrument(),
        base_asset="ETH",
        quote_asset="USD",
        price_increment="0.01",
        quantity_increment="0.001",
        min_quantity="0.005",
        max_quantity="100",
    )

    assert rules.effective_market_quantity_increment == Decimal("0.001")
    assert rules.effective_market_min_quantity == Decimal("0.005")
    assert rules.effective_market_max_quantity == Decimal("100")


def test_market_max_quantity_cannot_be_less_than_effective_minimum() -> None:
    with pytest.raises(ValueError, match="market max quantity"):
        SymbolRules(
            instrument=instrument(),
            base_asset="ETH",
            quote_asset="USD",
            price_increment="0.01",
            quantity_increment="0.001",
            min_quantity="0.01",
            market_max_quantity="0.005",
        )


def test_account_snapshot_can_hold_arbitrary_instrument_positions() -> None:
    position = PositionSnapshot(instrument("venue-b"), quantity="-2.5")
    balance = BalanceSnapshot("USD", total="1000", available="800", locked="200")
    account = AccountSnapshot(
        venue="venue-b",
        balances=(balance,),
        positions=(position,),
        equity="1250.50",
        available_margin="700",
    )

    assert account.find_balance("USD") is balance
    assert account.find_position(position.instrument) is position
    assert account.equity == Decimal("1250.50")
