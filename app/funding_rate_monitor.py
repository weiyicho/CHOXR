"""Read-only Binance funding-rate scanner with optional Discord summaries."""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from adapters.binance.api import SpotApi, UsdMApi
from adapters.binance.config import BinanceConfig
from adapters.binance.gateways import BinanceMarketDataGateway
from adapters.binance.transport.rate_limit import RateLimitState
from adapters.binance.transport.rest_client import BinanceRestClient
from adapters.discord_notifier import DiscordNotifier
from engine.domain.instrument import InstrumentId
from strategies.funding_rate import FundingCandidate, scan_funding_candidates

from .settings import Settings


LOGGER = logging.getLogger(__name__)
TAIPEI = ZoneInfo("Asia/Taipei")
UNIVERSE_REFRESH_SECONDS = 3_600


@dataclass(frozen=True)
class FundingScanReport:
    scanned_at: datetime
    scanned_symbol_count: int
    candidates: tuple[FundingCandidate, ...]
    basis_error_count: int = 0

    def __post_init__(self) -> None:
        if self.scanned_at.tzinfo is None:
            raise ValueError("scanned_at must be timezone-aware")
        if self.scanned_symbol_count < 0:
            raise ValueError("scanned_symbol_count cannot be negative")
        if self.basis_error_count < 0:
            raise ValueError("basis_error_count cannot be negative")
        object.__setattr__(self, "candidates", tuple(self.candidates))

    @property
    def fingerprint(self) -> tuple[tuple[str, Decimal], ...]:
        precision = Decimal("0.001")
        return tuple(
            (
                candidate.symbol,
                candidate.annualized_rate.quantize(precision),
            )
            for candidate in self.candidates
        )


class FundingRateMonitor:
    """Fetch public market data, rank candidates and publish summaries."""

    def __init__(
        self,
        *,
        spot_api: SpotApi,
        usd_m_api: UsdMApi,
        market_data_gateway: BinanceMarketDataGateway,
        notifier: DiscordNotifier,
        settings: Settings,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._spot_api = spot_api
        self._usd_m_api = usd_m_api
        self._market_data = market_data_gateway
        self._notifier = notifier
        self._settings = settings
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep
        self._spot_symbols: frozenset[str] | None = None
        self._perpetual_symbols: frozenset[str] | None = None
        self._universe_refreshed_at: datetime | None = None
        self._last_fingerprint: tuple[tuple[str, Decimal], ...] | None = None
        self._last_summary_sent_at: datetime | None = None
        self._last_error_sent_at: datetime | None = None

    @property
    def notifier_enabled(self) -> bool:
        return self._notifier.enabled

    def scan_once(self) -> FundingScanReport:
        scanned_at = self._now()
        perpetual_symbols, spot_symbols = self._load_symbol_universe(scanned_at)
        premium_indexes = _require_rows(
            self._usd_m_api.get_premium_index(),
            "premium index",
        )
        funding_rate_info = _require_rows(
            self._usd_m_api.get_funding_rate_info(),
            "funding rate info",
        )
        tickers_24h = _require_rows(
            self._usd_m_api.get_24h_tickers(),
            "24-hour tickers",
        )
        candidates = scan_funding_candidates(
            premium_indexes=premium_indexes,
            tickers_24h=tickers_24h,
            funding_rate_info=funding_rate_info,
            perpetual_symbols=perpetual_symbols,
            spot_symbols=spot_symbols,
            min_annualized_rate=self._settings.funding_min_annualized_rate,
            min_quote_volume_24h=self._settings.funding_min_quote_volume_24h,
            top_n=self._settings.funding_top_n,
        )

        enriched: list[FundingCandidate] = []
        basis_errors = 0
        for candidate in candidates:
            try:
                spot_book = self._market_data.get_order_book(
                    InstrumentId("binance", "MARGIN", candidate.symbol),
                    depth=5,
                )
                perpetual_book = self._market_data.get_order_book(
                    InstrumentId(
                        "binance",
                        "USD_M_PERPETUAL",
                        candidate.symbol,
                    ),
                    depth=5,
                )
                if spot_book.best_ask is None or perpetual_book.best_bid is None:
                    raise ValueError("best executable prices are unavailable")
                candidate = candidate.with_executable_prices(
                    spot_ask=spot_book.best_ask.price,
                    perpetual_bid=perpetual_book.best_bid.price,
                )
            except Exception as exc:
                basis_errors += 1
                LOGGER.warning(
                    "Funding basis enrichment failed for %s: %s",
                    candidate.symbol,
                    exc,
                )
            enriched.append(candidate)

        return FundingScanReport(
            scanned_at=scanned_at,
            scanned_symbol_count=len(perpetual_symbols & spot_symbols),
            candidates=tuple(enriched),
            basis_error_count=basis_errors,
        )

    def notify_if_due(
        self,
        report: FundingScanReport,
        *,
        force: bool = False,
    ) -> bool:
        if not self._notifier.enabled:
            return False

        changed = report.fingerprint != self._last_fingerprint
        heartbeat_due = (
            self._last_summary_sent_at is None
            or (
                report.scanned_at - self._last_summary_sent_at
            ).total_seconds()
            >= self._settings.funding_summary_interval_seconds
        )
        if not force and not changed and not heartbeat_due:
            return False

        title, description, color, fields = discord_summary(report)
        sent = self._notifier.send_embed(
            title,
            description=description,
            color=color,
            fields=fields,
        )
        if sent:
            self._last_fingerprint = report.fingerprint
            self._last_summary_sent_at = report.scanned_at
        return sent

    def run_forever(self) -> None:
        consecutive_failures = 0
        while True:
            try:
                report = self.scan_once()
                print(render_console_report(report), flush=True)
                if consecutive_failures:
                    self._send_recovery(consecutive_failures)
                self.notify_if_due(report, force=consecutive_failures > 0)
                consecutive_failures = 0
                delay = self._settings.funding_scan_interval_seconds
            except KeyboardInterrupt:
                return
            except Exception as exc:
                consecutive_failures += 1
                LOGGER.exception("Funding monitor scan failed")
                self._notify_error_if_due(exc, consecutive_failures)
                delay = self.retry_delay_seconds(
                    consecutive_failures,
                    max_delay=self._settings.funding_scan_interval_seconds,
                )

            try:
                self._sleep(delay)
            except KeyboardInterrupt:
                return

    @staticmethod
    def retry_delay_seconds(
        consecutive_failures: int,
        *,
        max_delay: float,
    ) -> float:
        if consecutive_failures <= 0:
            raise ValueError("consecutive_failures must be positive")
        if max_delay <= 0:
            raise ValueError("max_delay must be positive")
        return min(max_delay, float(30 * (2 ** (consecutive_failures - 1))))

    def _load_symbol_universe(
        self,
        now: datetime,
    ) -> tuple[frozenset[str], frozenset[str]]:
        cache_fresh = (
            self._universe_refreshed_at is not None
            and self._perpetual_symbols is not None
            and self._spot_symbols is not None
            and (now - self._universe_refreshed_at).total_seconds()
            < UNIVERSE_REFRESH_SECONDS
        )
        if cache_fresh:
            return self._perpetual_symbols, self._spot_symbols

        perpetual_symbols = frozenset(
            _eligible_symbols(
                self._usd_m_api.get_exchange_info(),
                perpetual_only=True,
            )
        )
        spot_symbols = frozenset(
            _eligible_symbols(
                self._spot_api.get_exchange_info(),
                perpetual_only=False,
            )
        )
        self._perpetual_symbols = perpetual_symbols
        self._spot_symbols = spot_symbols
        self._universe_refreshed_at = now
        return perpetual_symbols, spot_symbols

    def _notify_error_if_due(
        self,
        exc: Exception,
        consecutive_failures: int,
    ) -> None:
        if not self._notifier.enabled:
            return
        now = self._now()
        due = (
            self._last_error_sent_at is None
            or (now - self._last_error_sent_at).total_seconds()
            >= self._settings.funding_summary_interval_seconds
        )
        if not due:
            return
        sent = self._notifier.send_embed(
            "CHOXR Funding Monitor Error",
            description=(
                f"連續失敗：{consecutive_failures}\n"
                f"錯誤：{exc.__class__.__name__}: {exc}"
            ),
            color=0xE74C3C,
        )
        if sent:
            self._last_error_sent_at = now

    def _send_recovery(self, previous_failures: int) -> None:
        if not self._notifier.enabled:
            return
        self._notifier.send_embed(
            "CHOXR Funding Monitor Recovered",
            description=f"掃描已恢復；先前連續失敗 {previous_failures} 次。",
            color=0x2ECC71,
        )
        self._last_error_sent_at = None


def build_funding_rate_monitor(settings: Settings) -> FundingRateMonitor:
    """Build only public Binance market-data clients and Discord output."""

    config = BinanceConfig(api_key="", api_secret="")
    shared_rate_limits = RateLimitState()
    spot_client = BinanceRestClient(
        config.spot_rest_url,
        config,
        rate_limits=shared_rate_limits,
    )
    usd_m_client = BinanceRestClient(
        config.usd_m_rest_url,
        config,
        rate_limits=shared_rate_limits,
    )
    spot_api = SpotApi(spot_client)
    usd_m_api = UsdMApi(usd_m_client)
    return FundingRateMonitor(
        spot_api=spot_api,
        usd_m_api=usd_m_api,
        market_data_gateway=BinanceMarketDataGateway(spot_api, usd_m_api),
        notifier=DiscordNotifier(
            settings.discord_webhook_url,
            enabled=settings.discord_notifications_enabled,
        ),
        settings=settings,
    )


def discord_summary(
    report: FundingScanReport,
) -> tuple[str, str, int, Sequence[Mapping[str, object]]]:
    observed = report.scanned_at.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")
    description = (
        f"掃描時間：{observed}（台北）\n"
        f"顯示候選：{len(report.candidates)} / 掃描 {report.scanned_symbol_count}"
    )
    if report.basis_error_count:
        description += f"\nBasis 無法取得：{report.basis_error_count}"

    fields: list[dict[str, object]] = []
    for rank, candidate in enumerate(report.candidates, start=1):
        funding_pct = candidate.funding_rate * Decimal("100")
        annualized_pct = candidate.annualized_rate * Decimal("100")
        basis = candidate.entry_basis_pct
        basis_text = (
            "unavailable"
            if basis is None
            else f"{basis * Decimal('100'):+.3f}%"
        )
        next_funding = candidate.next_funding_at.astimezone(TAIPEI).strftime(
            "%m-%d %H:%M"
        )
        fields.append(
            {
                "name": f"#{rank} {candidate.symbol}",
                "value": (
                    f"Funding：{funding_pct:.4f}% / "
                    f"{candidate.funding_interval_hours}h\n"
                    f"簡單年化：{annualized_pct:.2f}% ｜ "
                    f"24h 量：{_format_quote_volume(candidate.quote_volume_24h)}\n"
                    f"進場 basis：{basis_text} ｜ "
                    f"下次 funding：{next_funding}"
                ),
                "inline": False,
            }
        )

    if not fields:
        description += "\n目前沒有符合條件的正 funding 候選。"
    return (
        "CHOXR Funding Monitor — Binance",
        description,
        0x2ECC71 if fields else 0xF1C40F,
        fields,
    )


def render_console_report(report: FundingScanReport) -> str:
    title, description, _, fields = discord_summary(report)
    lines = [title, description]
    for field in fields:
        value = str(field["value"]).replace("\n", " | ")
        lines.append(f"{field['name']}: {value}")
    return "\n".join(lines)


def _eligible_symbols(
    payload: object,
    *,
    perpetual_only: bool,
) -> set[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise TypeError("Binance exchange info must contain a symbols list")

    result: set[str] = set()
    for item in payload["symbols"]:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol:
            continue
        if str(item.get("status", "")).upper() != "TRADING":
            continue
        if str(item.get("quoteAsset", "")).upper() != "USDT":
            continue
        if (
            perpetual_only
            and str(item.get("contractType", "")).upper() != "PERPETUAL"
        ):
            continue
        result.add(symbol)
    return result


def _require_rows(payload: object, name: str) -> list[Mapping[str, object]]:
    if not isinstance(payload, list):
        raise TypeError(f"Binance {name} response must be a list")
    return [row for row in payload if isinstance(row, Mapping)]


def _format_quote_volume(value: Decimal) -> str:
    billion = Decimal("1000000000")
    million = Decimal("1000000")
    if value >= billion:
        return f"${value / billion:.2f}B"
    if value >= million:
        return f"${value / million:.1f}M"
    return f"${value:,.0f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="scan once, print the report, and exit",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="with --once, also send the report when Discord is enabled",
    )
    args = parser.parse_args(argv)

    settings = Settings.from_environment()
    monitor = build_funding_rate_monitor(settings)
    if args.once:
        report = monitor.scan_once()
        print(render_console_report(report))
        if args.notify:
            monitor.notify_if_due(report, force=True)
        return 0

    monitor.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
