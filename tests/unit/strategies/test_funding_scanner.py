from datetime import datetime, timezone
from decimal import Decimal

import pytest

from strategies.funding_rate import FundingCandidate, scan_funding_candidates


def premium(
    symbol: str,
    rate: str,
    *,
    mark_price: str = "101",
    index_price: str = "100",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "markPrice": mark_price,
        "indexPrice": index_price,
        "lastFundingRate": rate,
        "nextFundingTime": 1_800_000_000_000,
    }


def ticker(symbol: str, quote_volume: str) -> dict[str, object]:
    return {"symbol": symbol, "quoteVolume": quote_volume}


def scan(
    *,
    premiums: list[dict[str, object]],
    tickers: list[dict[str, object]],
    funding_info: list[dict[str, object]] | None = None,
    perpetual_symbols: set[str] | None = None,
    spot_symbols: set[str] | None = None,
    minimum_rate: str = "0.10",
    minimum_volume: str = "3000000",
    top_n: int = 10,
) -> tuple[FundingCandidate, ...]:
    symbols = {str(row["symbol"]) for row in premiums}
    return scan_funding_candidates(
        premium_indexes=premiums,
        tickers_24h=tickers,
        funding_rate_info=funding_info or [],
        perpetual_symbols=perpetual_symbols or symbols,
        spot_symbols=spot_symbols or symbols,
        min_annualized_rate=minimum_rate,
        min_quote_volume_24h=minimum_volume,
        top_n=top_n,
    )


def test_scanner_filters_and_ranks_positive_liquid_shared_symbols() -> None:
    result = scan(
        premiums=[
            premium("ETHUSDT", "0.00020"),
            premium("SOLUSDT", "0.00015"),
            premium("LOWUSDT", "0.00030"),
            premium("NEGUSDT", "-0.00040"),
            premium("NOSPOTUSDT", "0.00050"),
        ],
        tickers=[
            ticker("ETHUSDT", "50000000"),
            ticker("SOLUSDT", "60000000"),
            ticker("LOWUSDT", "2000000"),
            ticker("NEGUSDT", "90000000"),
            ticker("NOSPOTUSDT", "90000000"),
        ],
        spot_symbols={"ETHUSDT", "SOLUSDT", "LOWUSDT", "NEGUSDT"},
    )

    assert [candidate.symbol for candidate in result] == [
        "ETHUSDT",
        "SOLUSDT",
    ]
    assert result[0].annualized_rate == Decimal("0.21900")


def test_adjusted_funding_interval_changes_annualized_ranking() -> None:
    result = scan(
        premiums=[
            premium("FOURUSDT", "0.00010"),
            premium("EIGHTUSDT", "0.00015"),
        ],
        tickers=[
            ticker("FOURUSDT", "50000000"),
            ticker("EIGHTUSDT", "50000000"),
        ],
        funding_info=[
            {"symbol": "FOURUSDT", "fundingIntervalHours": 4},
        ],
    )

    assert [candidate.symbol for candidate in result] == [
        "FOURUSDT",
        "EIGHTUSDT",
    ]
    assert result[0].annualized_rate == Decimal("0.21900")
    assert result[1].annualized_rate == Decimal("0.164250")


def test_top_n_is_applied_after_ranking() -> None:
    result = scan(
        premiums=[
            premium("AUSDT", "0.00010"),
            premium("BUSDT", "0.00030"),
            premium("CUSDT", "0.00020"),
        ],
        tickers=[
            ticker("AUSDT", "50000000"),
            ticker("BUSDT", "50000000"),
            ticker("CUSDT", "50000000"),
        ],
        top_n=2,
    )

    assert [candidate.symbol for candidate in result] == ["BUSDT", "CUSDT"]


def test_malformed_market_rows_do_not_abort_the_scan() -> None:
    result = scan(
        premiums=[
            premium("ETHUSDT", "0.00020"),
            {"symbol": "BROKENUSDT", "lastFundingRate": "not-a-number"},
        ],
        tickers=[
            ticker("ETHUSDT", "50000000"),
            ticker("BROKENUSDT", "50000000"),
        ],
    )

    assert [candidate.symbol for candidate in result] == ["ETHUSDT"]


def test_candidate_calculates_executable_entry_basis() -> None:
    candidate = FundingCandidate(
        symbol="ethusdt",
        funding_rate="0.00020",
        funding_interval_hours=8,
        next_funding_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        mark_price="101",
        index_price="100",
        quote_volume_24h="50000000",
    ).with_executable_prices(
        spot_ask=Decimal("100"),
        perpetual_bid=Decimal("100.25"),
    )

    assert candidate.symbol == "ETHUSDT"
    assert candidate.entry_basis_pct == Decimal("0.0025")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"min_annualized_rate": "-0.1"}, "min_annualized_rate"),
        ({"min_quote_volume_24h": "-1"}, "min_quote_volume_24h"),
        ({"top_n": 0}, "top_n"),
    ],
)
def test_invalid_scan_parameters_fail_fast(
    kwargs: dict[str, object],
    message: str,
) -> None:
    parameters: dict[str, object] = {
        "premium_indexes": [],
        "tickers_24h": [],
        "funding_rate_info": [],
        "perpetual_symbols": [],
        "spot_symbols": [],
        "min_annualized_rate": "0.10",
        "min_quote_volume_24h": "3000000",
        "top_n": 10,
    }
    parameters.update(kwargs)

    with pytest.raises(ValueError, match=message):
        scan_funding_candidates(**parameters)
