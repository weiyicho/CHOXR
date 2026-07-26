"""Pure selection of Binance funding-rate monitoring candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable, Mapping


ZERO = Decimal("0")
DEFAULT_FUNDING_INTERVAL_HOURS = 8


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class FundingCandidate:
    """One monitor-only Spot/perpetual funding opportunity."""

    symbol: str
    funding_rate: Decimal
    funding_interval_hours: int
    next_funding_at: datetime
    mark_price: Decimal
    index_price: Decimal
    quote_volume_24h: Decimal
    spot_ask: Decimal | None = None
    perpetual_bid: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        for name in (
            "funding_rate",
            "mark_price",
            "index_price",
            "quote_volume_24h",
        ):
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        for name in ("spot_ask", "perpetual_bid"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _decimal(value))

        if not self.symbol:
            raise ValueError("symbol is required")
        if self.funding_interval_hours <= 0:
            raise ValueError("funding_interval_hours must be positive")
        if self.next_funding_at.tzinfo is None:
            raise ValueError("next_funding_at must be timezone-aware")
        if self.mark_price <= ZERO or self.index_price <= ZERO:
            raise ValueError("mark and index prices must be positive")
        if self.quote_volume_24h < ZERO:
            raise ValueError("quote_volume_24h cannot be negative")
        if self.spot_ask is not None and self.spot_ask <= ZERO:
            raise ValueError("spot_ask must be positive")
        if self.perpetual_bid is not None and self.perpetual_bid <= ZERO:
            raise ValueError("perpetual_bid must be positive")

    @property
    def annualized_rate(self) -> Decimal:
        periods_per_year = Decimal(24 * 365) / Decimal(self.funding_interval_hours)
        return self.funding_rate * periods_per_year

    @property
    def entry_basis_pct(self) -> Decimal | None:
        if self.spot_ask is None or self.perpetual_bid is None:
            return None
        return (self.perpetual_bid - self.spot_ask) / self.spot_ask

    def with_executable_prices(
        self,
        *,
        spot_ask: Decimal,
        perpetual_bid: Decimal,
    ) -> FundingCandidate:
        return replace(
            self,
            spot_ask=spot_ask,
            perpetual_bid=perpetual_bid,
        )


def scan_funding_candidates(
    *,
    premium_indexes: Iterable[Mapping[str, object]],
    tickers_24h: Iterable[Mapping[str, object]],
    funding_rate_info: Iterable[Mapping[str, object]],
    perpetual_symbols: Iterable[str],
    spot_symbols: Iterable[str],
    min_annualized_rate: Decimal | int | float | str,
    min_quote_volume_24h: Decimal | int | float | str,
    top_n: int,
) -> tuple[FundingCandidate, ...]:
    """Filter and rank current positive-funding Binance opportunities."""

    minimum_rate = _decimal(min_annualized_rate)
    minimum_volume = _decimal(min_quote_volume_24h)
    if minimum_rate < ZERO:
        raise ValueError("min_annualized_rate cannot be negative")
    if minimum_volume < ZERO:
        raise ValueError("min_quote_volume_24h cannot be negative")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    premium_by_symbol = _rows_by_symbol(premium_indexes)
    ticker_by_symbol = _rows_by_symbol(tickers_24h)
    interval_by_symbol = _funding_intervals(funding_rate_info)
    supported = {
        symbol.strip().upper() for symbol in perpetual_symbols
    } & {
        symbol.strip().upper() for symbol in spot_symbols
    }

    candidates: list[FundingCandidate] = []
    for symbol in sorted(supported):
        premium = premium_by_symbol.get(symbol)
        ticker = ticker_by_symbol.get(symbol)
        if premium is None or ticker is None:
            continue
        try:
            funding_rate = _decimal(premium["lastFundingRate"])
            interval_hours = interval_by_symbol.get(
                symbol,
                DEFAULT_FUNDING_INTERVAL_HOURS,
            )
            quote_volume = _decimal(ticker["quoteVolume"])
            candidate = FundingCandidate(
                symbol=symbol,
                funding_rate=funding_rate,
                funding_interval_hours=interval_hours,
                next_funding_at=datetime.fromtimestamp(
                    int(premium["nextFundingTime"]) / 1_000,
                    tz=timezone.utc,
                ),
                mark_price=_decimal(premium["markPrice"]),
                index_price=_decimal(premium["indexPrice"]),
                quote_volume_24h=quote_volume,
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            continue

        if funding_rate <= ZERO:
            continue
        if candidate.annualized_rate < minimum_rate:
            continue
        if quote_volume < minimum_volume:
            continue
        candidates.append(candidate)

    candidates.sort(
        key=lambda candidate: (
            candidate.annualized_rate,
            candidate.quote_volume_24h,
            candidate.symbol,
        ),
        reverse=True,
    )
    return tuple(candidates[:top_n])


def _rows_by_symbol(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    result: dict[str, Mapping[str, object]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        if symbol:
            result[symbol] = row
    return result


def _funding_intervals(
    rows: Iterable[Mapping[str, object]],
) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).strip().upper()
        try:
            interval = int(row["fundingIntervalHours"])
        except (KeyError, TypeError, ValueError):
            continue
        if symbol and interval > 0:
            result[symbol] = interval
    return result
