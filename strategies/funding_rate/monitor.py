"""Read-only Binance funding-rate scanner with optional Discord summaries."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from adapters.binance.api import SpotApi, UsdMApi
from adapters.binance.config import BinanceConfig
from adapters.binance.gateways import BinanceMarketDataGateway
from adapters.binance.transport.rate_limit import RateLimitState
from adapters.binance.transport.rest_client import BinanceRestClient
from adapters.discord_notifier import DiscordNotifier
from dotenv import load_dotenv
from engine.domain.instrument import InstrumentId
from PIL import Image, ImageDraw, ImageFont

from app.settings import Settings

from .allocation import FundingAllocation, FundingCapitalAllocator
from .scanner import FundingCandidate, scan_funding_candidates


LOGGER = logging.getLogger(__name__)
TAIPEI = ZoneInfo("Asia/Taipei")
UNIVERSE_REFRESH_SECONDS = 3_600
DEFAULT_PLAN_CAPITAL = Decimal("100")
DEFAULT_FUTURES_LEVERAGE = Decimal("5")
DEFAULT_ORDER_PLAN_PATH = (
    Path(__file__).resolve().parent
    / "runtime"
    / "order_plan.json"
)


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
        allocator: FundingCapitalAllocator | None = None,
        plan_capital: Decimal | None = None,
        futures_leverage: Decimal | None = None,
        order_plan_path: str | Path = DEFAULT_ORDER_PLAN_PATH,
    ) -> None:
        self._spot_api = spot_api
        self._usd_m_api = usd_m_api
        self._market_data = market_data_gateway
        self._notifier = notifier
        self._settings = settings
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep
        self._allocator = allocator or FundingCapitalAllocator()
        self._plan_capital = Decimal(
            str(
                settings.funding_capital
                if plan_capital is None
                else plan_capital
            )
        )
        self._futures_leverage = Decimal(
            str(
                settings.funding_leverage
                if futures_leverage is None
                else futures_leverage
            )
        )
        self._order_plan_path = Path(order_plan_path)
        if self._plan_capital <= 0:
            raise ValueError("plan_capital must be positive")
        if self._futures_leverage <= 0:
            raise ValueError("futures_leverage must be positive")
        self._spot_symbols: frozenset[str] | None = None
        self._perpetual_symbols: frozenset[str] | None = None
        self._universe_refreshed_at: datetime | None = None
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

    def notify(self, report: FundingScanReport) -> bool:
        if not self._notifier.enabled:
            return False

        with TemporaryDirectory(prefix="choxr-funding-") as output_dir:
            image_path = Path(output_dir) / "funding-opportunities.png"
            render_funding_table_image(
                report,
                image_path,
                settings=self._settings,
            )
            return self._notifier.send_picture(image_path)

    def save_order_plan(self, report: FundingScanReport) -> Path:
        """Build and atomically persist the latest monitor decision."""

        plan = build_funding_order_plan(
            report,
            available_capital=self._plan_capital,
            futures_leverage=self._futures_leverage,
            allocator=self._allocator,
        )
        return write_funding_order_plan(plan, self._order_plan_path)

    def run_forever(self) -> None:
        consecutive_failures = 0
        while True:
            try:
                report = self.scan_once()
                print(render_console_report(report), flush=True)
                plan_path = self.save_order_plan(report)
                print(f"Order plan: {plan_path}", flush=True)
                if consecutive_failures:
                    self._send_recovery(consecutive_failures)
                if self._notifier.enabled and not self.notify(report):
                    LOGGER.warning("Discord funding report was not accepted")
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
            >= self._settings.funding_scan_interval_seconds
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


def build_funding_order_plan(
    report: FundingScanReport,
    *,
    available_capital: Decimal | int | float | str = DEFAULT_PLAN_CAPITAL,
    futures_leverage: Decimal | int | float | str = DEFAULT_FUTURES_LEVERAGE,
    allocator: FundingCapitalAllocator | None = None,
) -> dict[str, object]:
    """Select the best executable candidate and calculate both position legs.

    This produces a decision snapshot only. It does not create an exchange
    client, round quantity to symbol filters, or submit an order.
    """

    capital = Decimal(str(available_capital))
    leverage = Decimal(str(futures_leverage))
    if capital <= 0:
        raise ValueError("available_capital must be positive")
    if leverage <= 0:
        raise ValueError("futures_leverage must be positive")

    base_plan: dict[str, object] = {
        "schema_version": 1,
        "strategy": "funding_rate",
        "status": "NO_CANDIDATE",
        "generated_at": report.scanned_at.isoformat(),
        "scan": {
            "scanned_symbol_count": report.scanned_symbol_count,
            "candidates_found": len(report.candidates),
            "basis_error_count": report.basis_error_count,
        },
        "selected_symbols": [],
        "candidate": None,
        "allocation": None,
    }
    selected = next(
        (
            (rank, candidate)
            for rank, candidate in enumerate(report.candidates, start=1)
            if candidate.spot_ask is not None
            and candidate.perpetual_bid is not None
        ),
        None,
    )
    if selected is None:
        return base_plan

    rank, candidate = selected
    allocation = (allocator or FundingCapitalAllocator()).allocate(
        available_capital=capital,
        capital_fraction=Decimal("1"),
        futures_leverage=leverage,
        reference_price=candidate.spot_ask,
        futures_reference_price=candidate.perpetual_bid,
    )
    base_plan.update(
        {
            "status": "READY",
            "selected_symbols": [candidate.symbol],
            "candidate": _candidate_plan_payload(candidate, rank=rank),
            "allocation": _allocation_plan_payload(allocation),
        }
    )
    return base_plan


def write_funding_order_plan(
    plan: Mapping[str, object],
    output_path: str | Path = DEFAULT_ORDER_PLAN_PATH,
) -> Path:
    """Atomically replace the latest JSON plan so readers never see half a file."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(
                dict(plan),
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return destination


def _candidate_plan_payload(
    candidate: FundingCandidate,
    *,
    rank: int,
) -> dict[str, object]:
    return {
        "rank": rank,
        "symbol": candidate.symbol,
        "funding_rate": str(candidate.funding_rate),
        "funding_interval_hours": candidate.funding_interval_hours,
        "annualized_rate": str(candidate.annualized_rate),
        "quote_volume_24h": str(candidate.quote_volume_24h),
        "spot_ask": str(candidate.spot_ask),
        "perpetual_bid": str(candidate.perpetual_bid),
        "entry_basis_pct": (
            None
            if candidate.entry_basis_pct is None
            else str(candidate.entry_basis_pct)
        ),
        "next_funding_at": candidate.next_funding_at.isoformat(),
    }


def _allocation_plan_payload(
    allocation: FundingAllocation,
) -> dict[str, object]:
    return {
        "capital": {
            "available": str(allocation.available_capital),
            "deployed": str(allocation.deployed_capital),
        },
        "spot_leg": {
            "market": "MARGIN",
            "side": "BUY",
            "reference_price": str(allocation.reference_price),
            "quantity": str(allocation.spot_quantity),
            "notional": str(allocation.spot_notional),
        },
        "perpetual_leg": {
            "market": "USD_M_PERPETUAL",
            "side": "SELL",
            "reference_price": str(allocation.futures_reference_price),
            "quantity": str(allocation.futures_quantity),
            "notional": str(allocation.futures_notional),
            "initial_margin": str(allocation.futures_margin),
            "leverage": str(allocation.futures_leverage),
        },
    }


def build_funding_rate_monitor(
    settings: Settings,
    *,
    order_plan_path: str | Path = DEFAULT_ORDER_PLAN_PATH,
) -> FundingRateMonitor:
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
        order_plan_path=order_plan_path,
    )


def render_console_report(report: FundingScanReport) -> str:
    observed = report.scanned_at.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "CHOXR Funding Monitor — Binance",
        f"掃描時間：{observed}（台北）\n"
        f"顯示候選：{len(report.candidates)} / 掃描 {report.scanned_symbol_count}",
    ]
    if report.basis_error_count:
        lines.append(f"Basis 無法取得：{report.basis_error_count}")

    if report.candidates:
        lines.append(_funding_table(report.candidates))
    else:
        lines.append("目前沒有符合條件的正 funding 候選。")
    return "\n".join(lines)


def render_funding_table_image(
    report: FundingScanReport,
    output_path: str | Path,
    *,
    settings: Settings,
) -> Path:
    """Render a Discord-safe PNG table that cannot wrap like text columns."""

    width = 1_400
    outer_margin = 44
    table_left = 68
    table_right = width - 68
    table_top = 244
    header_height = 58
    row_height = 68
    visible_rows = max(1, len(report.candidates))
    footer_height = 104
    height = table_top + header_height + visible_rows * row_height + footer_height

    image = Image.new("RGB", (width, height), "#090E1A")
    draw = ImageDraw.Draw(image)
    title_font = _load_table_font(42, bold=True)
    label_font = _load_table_font(18, bold=True)
    meta_font = _load_table_font(19)
    header_font = _load_table_font(17, bold=True)
    body_font = _load_table_font(20)
    body_bold_font = _load_table_font(20, bold=True)
    small_font = _load_table_font(17)

    draw.rounded_rectangle(
        (outer_margin, 34, width - outer_margin, height - 34),
        radius=28,
        fill="#101827",
        outline="#263349",
        width=2,
    )
    draw.rounded_rectangle(
        (68, 58, 210, 64),
        radius=3,
        fill="#34D399",
    )
    draw.text(
        (68, 82),
        "CHOXR  /  FUNDING RATE",
        font=label_font,
        fill="#6EE7B7",
    )
    draw.text(
        (68, 112),
        "Top Funding Opportunities",
        font=title_font,
        fill="#F8FAFC",
    )

    observed = report.scanned_at.astimezone(TAIPEI)
    chip_y = 184
    chip_x = 68
    chip_x = _draw_metric_chip(
        draw,
        chip_x,
        chip_y,
        f"{len(report.candidates)} candidates",
        meta_font,
        accent="#34D399",
    )
    chip_x = _draw_metric_chip(
        draw,
        chip_x,
        chip_y,
        f"{report.scanned_symbol_count} markets",
        meta_font,
        accent="#60A5FA",
    )
    _draw_metric_chip(
        draw,
        chip_x,
        chip_y,
        observed.strftime("Taipei  %Y-%m-%d  %H:%M:%S"),
        meta_font,
        accent="#A78BFA",
    )

    draw.rounded_rectangle(
        (table_left, table_top, table_right, table_top + header_height),
        radius=14,
        fill="#1A2538",
    )
    columns = {
        "rank": 98,
        "symbol": 144,
        "funding": 510,
        "interval": 620,
        "annual": 795,
        "volume": 990,
        "basis": 1_165,
        "next": 1_320,
    }
    header_y = table_top + header_height // 2
    draw.text(
        (columns["rank"], header_y),
        "#",
        font=header_font,
        fill="#94A3B8",
        anchor="mm",
    )
    draw.text(
        (columns["symbol"], header_y),
        "MARKET",
        font=header_font,
        fill="#94A3B8",
        anchor="lm",
    )
    for key, label in (
        ("funding", "FUNDING"),
        ("interval", "INTERVAL"),
        ("annual", "ANNUALIZED"),
        ("volume", "24H VOLUME"),
        ("basis", "ENTRY BASIS"),
        ("next", "NEXT"),
    ):
        draw.text(
            (columns[key], header_y),
            label,
            font=header_font,
            fill="#94A3B8",
            anchor="rm",
        )

    if report.candidates:
        for row_index, candidate in enumerate(report.candidates):
            row_top = table_top + header_height + row_index * row_height
            row_bottom = row_top + row_height
            if row_index % 2 == 0:
                draw.rounded_rectangle(
                    (table_left, row_top + 2, table_right, row_bottom - 2),
                    radius=10,
                    fill="#121D2E",
                )
            if row_index:
                draw.line(
                    (table_left + 20, row_top, table_right - 20, row_top),
                    fill="#223047",
                    width=1,
                )
            _draw_funding_row(
                draw,
                candidate,
                rank=row_index + 1,
                center_y=row_top + row_height // 2,
                columns=columns,
                body_font=body_font,
                body_bold_font=body_bold_font,
            )
    else:
        empty_y = table_top + header_height + row_height // 2
        draw.text(
            ((table_left + table_right) // 2, empty_y),
            "No candidates meet the current funding and liquidity thresholds.",
            font=body_font,
            fill="#94A3B8",
            anchor="mm",
        )

    footer_y = table_top + header_height + visible_rows * row_height + 34
    draw.ellipse((68, footer_y + 4, 80, footer_y + 16), fill="#34D399")
    draw.text(
        (90, footer_y + 10),
        "READ-ONLY PUBLIC MARKET SCAN",
        font=small_font,
        fill="#CBD5E1",
        anchor="lm",
    )
    thresholds = (
        f"Annualized >= {settings.funding_min_annualized_rate * Decimal('100'):.2f}%"
        f"   •   24h Volume >= "
        f"{_format_quote_volume(settings.funding_min_quote_volume_24h)}"
    )
    draw.text(
        (table_right, footer_y + 10),
        thresholds,
        font=small_font,
        fill="#64748B",
        anchor="rm",
    )
    if report.basis_error_count:
        draw.text(
            (68, footer_y + 42),
            f"Basis unavailable for {report.basis_error_count} candidates",
            font=small_font,
            fill="#F59E0B",
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return destination


def _draw_funding_row(
    draw: ImageDraw.ImageDraw,
    candidate: FundingCandidate,
    *,
    rank: int,
    center_y: int,
    columns: Mapping[str, int],
    body_font: ImageFont.ImageFont,
    body_bold_font: ImageFont.ImageFont,
) -> None:
    funding_pct = candidate.funding_rate * Decimal("100")
    annualized_pct = candidate.annualized_rate * Decimal("100")
    basis = candidate.entry_basis_pct
    basis_text = (
        "n/a"
        if basis is None
        else f"{basis * Decimal('100'):+.3f}%"
    )
    basis_color = (
        "#94A3B8"
        if basis is None
        else "#34D399"
        if basis >= 0
        else "#FB7185"
    )
    next_funding = candidate.next_funding_at.astimezone(TAIPEI).strftime(
        "%m/%d  %H:%M"
    )

    draw.rounded_rectangle(
        (
            columns["rank"] - 18,
            center_y - 18,
            columns["rank"] + 18,
            center_y + 18,
        ),
        radius=9,
        fill="#24334A",
    )
    draw.text(
        (columns["rank"], center_y),
        str(rank),
        font=body_bold_font,
        fill="#CBD5E1",
        anchor="mm",
    )
    draw.text(
        (columns["symbol"], center_y),
        candidate.symbol,
        font=body_bold_font,
        fill="#F8FAFC",
        anchor="lm",
    )
    draw.text(
        (columns["funding"], center_y),
        f"{funding_pct:.4f}%",
        font=body_bold_font,
        fill="#34D399",
        anchor="rm",
    )
    draw.text(
        (columns["interval"], center_y),
        f"{candidate.funding_interval_hours}h",
        font=body_font,
        fill="#CBD5E1",
        anchor="rm",
    )
    draw.text(
        (columns["annual"], center_y),
        f"{annualized_pct:.2f}%",
        font=body_bold_font,
        fill="#6EE7B7",
        anchor="rm",
    )
    draw.text(
        (columns["volume"], center_y),
        _format_quote_volume(candidate.quote_volume_24h),
        font=body_font,
        fill="#E2E8F0",
        anchor="rm",
    )
    draw.text(
        (columns["basis"], center_y),
        basis_text,
        font=body_bold_font,
        fill=basis_color,
        anchor="rm",
    )
    draw.text(
        (columns["next"], center_y),
        next_funding,
        font=body_font,
        fill="#CBD5E1",
        anchor="rm",
    )


def _draw_metric_chip(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    *,
    accent: str,
) -> int:
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0] + 44
    draw.rounded_rectangle(
        (x, y, x + width, y + 42),
        radius=21,
        fill="#182438",
        outline="#293850",
        width=1,
    )
    draw.ellipse((x + 14, y + 15, x + 24, y + 25), fill=accent)
    draw.text(
        (x + 31, y + 21),
        text,
        font=font,
        fill="#CBD5E1",
        anchor="lm",
    )
    return x + width + 12


def _load_table_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    if bold:
        candidates = (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
    else:
        candidates = (
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _funding_table(candidates: Sequence[FundingCandidate]) -> str:
    header = (
        f"{'#':>2} {'Symbol':<14} {'Funding/Int':>13} "
        f"{'Annual':>8} {'24h Vol':>9} {'Basis':>8} {'Next':>11}"
    )
    rows = [header, "-" * len(header)]
    for rank, candidate in enumerate(candidates, start=1):
        funding_pct = candidate.funding_rate * Decimal("100")
        annualized_pct = candidate.annualized_rate * Decimal("100")
        funding_text = (
            f"{funding_pct:.4f}%/{candidate.funding_interval_hours}h"
        )
        basis = candidate.entry_basis_pct
        basis_text = (
            "n/a"
            if basis is None
            else f"{basis * Decimal('100'):+.3f}%"
        )
        next_funding = candidate.next_funding_at.astimezone(TAIPEI).strftime(
            "%m/%d %H:%M"
        )
        rows.append(
            f"{rank:>2} {candidate.symbol:<14} {funding_text:>13} "
            f"{annualized_pct:>7.2f}% "
            f"{_format_quote_volume(candidate.quote_volume_24h):>9} "
            f"{basis_text:>8} {next_funding:>11}"
        )
    return "\n".join(rows)


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
    args = parser.parse_args(argv)

    load_dotenv()
    settings = Settings.from_environment()
    monitor = build_funding_rate_monitor(settings)
    if args.once:
        report = monitor.scan_once()
        print(render_console_report(report))
        plan_path = monitor.save_order_plan(report)
        print(f"Order plan: {plan_path}")
        sent = monitor.notify(report)
        if monitor.notifier_enabled:
            if not sent:
                print("Discord report: failed")
                return 1
            print("Discord report: sent")
        else:
            print("Discord report: disabled")
        return 0

    monitor.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
