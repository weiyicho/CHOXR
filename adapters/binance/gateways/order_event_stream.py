from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from websockets.asyncio.client import connect as websocket_connect

from engine.domain.order import OrderState
from engine.domain.order_event import OrderEvent, OrderEventKind

from ..api.user_stream import PortfolioMarginUserStreamApi
from ..parsers.models import OrderEventSnapshot
from ..parsers.order_events import parse_order_event
from ..transport.errors import BinanceRequestError


_STOP = object()
_ORDER_EVENT_TYPES = frozenset({"executionReport", "ORDER_TRADE_UPDATE"})

Connector = Callable[..., Any]
Sleep = Callable[[float], Awaitable[None]]
RunSync = Callable[..., Awaitable[Any]]


def _operator_print(message: str) -> None:
    print(f"[FUNDING][WS] {message}", flush=True)


class ListenKeyExpired(RuntimeError):
    pass


class StreamLifecycleKind(str, Enum):
    """Binance-specific connection lifecycle signals.

    These signals deliberately live in the adapter rather than the engine's
    :class:`OrderEvent` stream.  They describe transport health, not exchange
    order state.
    """

    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    RECONNECTED = "reconnected"
    LISTEN_KEY_REBUILT = "listen_key_rebuilt"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class StreamLifecycleSignal:
    kind: StreamLifecycleKind
    reason: str | None = None
    connection_sequence: int = 0
    reconnect_attempt: int = 0
    retry_delay_seconds: float | None = None
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class PortfolioMarginOrderEventStream:
    """Own the PAPI websocket and normalize only order lifecycle messages.

    Binance listen keys are kept alive before their documented 60-minute
    expiry.  Connections are proactively rotated every 12 hours and transient
    disconnects use bounded reconnect backoff.
    """

    def __init__(
        self,
        user_stream_api: PortfolioMarginUserStreamApi,
        stream_base_url: str,
        *,
        connector: Connector = websocket_connect,
        sleep: Sleep = asyncio.sleep,
        run_sync: RunSync = asyncio.to_thread,
        keepalive_interval_seconds: float = 45 * 60,
        max_connection_age_seconds: float = 12 * 60 * 60,
        reconnect_backoff_seconds: tuple[float, ...] = (1, 2, 5, 10, 20, 30),
    ) -> None:
        if keepalive_interval_seconds <= 0:
            raise ValueError("keepalive_interval_seconds must be positive")
        if max_connection_age_seconds <= 0:
            raise ValueError("max_connection_age_seconds must be positive")
        if not reconnect_backoff_seconds or any(
            delay < 0 for delay in reconnect_backoff_seconds
        ):
            raise ValueError("reconnect_backoff_seconds must be non-empty and non-negative")
        self._api = user_stream_api
        self._stream_base_url = stream_base_url.rstrip("/")
        self._connector = connector
        self._sleep = sleep
        self._run_sync = run_sync
        self._keepalive_interval_seconds = keepalive_interval_seconds
        self._max_connection_age_seconds = max_connection_age_seconds
        self._reconnect_backoff_seconds = reconnect_backoff_seconds
        self._queue: asyncio.Queue[OrderEvent | object] = asyncio.Queue()
        self._lifecycle_queue: asyncio.Queue[StreamLifecycleSignal] = asyncio.Queue()
        self._lifecycle_state: StreamLifecycleSignal | None = None
        self._successful_connection_count = 0
        self._listen_key: str | None = None
        self._stop_requested = asyncio.Event()

    @property
    def listen_key(self) -> str | None:
        return self._listen_key

    @property
    def stream_base_url(self) -> str:
        return self._stream_base_url

    @property
    def websocket_url(self) -> str | None:
        if self._listen_key is None:
            return None
        return f"{self._stream_base_url}/ws/{self._listen_key}"

    @property
    def lifecycle_state(self) -> StreamLifecycleSignal | None:
        """Return the latest transport signal without consuming the stream."""

        return self._lifecycle_state

    def start(self) -> str:
        self._listen_key = self._api.start()
        return self._listen_key

    def keepalive(self) -> None:
        if self._listen_key is None:
            raise RuntimeError("user stream has not been started")
        self._api.keepalive()

    def close(self) -> None:
        self.request_stop()
        self._close_listen_key()
        self._queue.put_nowait(_STOP)

    def request_stop(self) -> None:
        self._stop_requested.set()

    def feed_native_event(self, payload: dict[str, object]) -> OrderEvent | None:
        if payload.get("e") not in _ORDER_EVENT_TYPES:
            return None
        event = self._to_domain(parse_order_event(payload))
        self._queue.put_nowait(event)
        return event

    async def run_network(self) -> None:
        """Run until :meth:`request_stop`, reconnecting without leaking events."""

        self._stop_requested.clear()
        self._successful_connection_count = 0
        reconnect_attempt = 0
        try:
            if self._listen_key is None:
                _operator_print("requesting Binance listen key")
                await self._start_listen_key()
            while not self._stop_requested.is_set():
                reconnect_reason = "connection_error"
                try:
                    _operator_print("opening WebSocket connection")
                    reason = await self._run_connection()
                    if self._stop_requested.is_set():
                        break
                    if reason == "rotate":
                        # The listen key is still valid.  Reopen only the
                        # websocket so Binance can continue buffering the same
                        # account stream while the new connection is created.
                        self._emit_lifecycle(
                            StreamLifecycleKind.RECONNECTING,
                            reason="connection_rotation",
                        )
                        reconnect_attempt = 0
                        continue
                    if reason == "listen_key_expired":
                        self._emit_lifecycle(
                            StreamLifecycleKind.RECONNECTING,
                            reason="listen_key_expired",
                        )
                        await self._rebuild_listen_key()
                        reconnect_attempt = 0
                        continue
                    if reason == "disconnected":
                        reconnect_reason = "stream_disconnected"
                except ListenKeyExpired:
                    self._emit_lifecycle(
                        StreamLifecycleKind.RECONNECTING,
                        reason="listen_key_expired",
                    )
                    await self._rebuild_listen_key()
                    reconnect_attempt = 0
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # A failed connect, receive, or keepalive is retried with the
                    # same idempotent listen key until Binance reports expiry.
                    _operator_print(
                        "connection cycle failed "
                        f"({type(exc).__name__}); scheduling reconnect"
                    )

                delay = self._reconnect_backoff_seconds[
                    min(reconnect_attempt, len(self._reconnect_backoff_seconds) - 1)
                ]
                reconnect_attempt += 1
                self._emit_lifecycle(
                    StreamLifecycleKind.RECONNECTING,
                    reason=reconnect_reason,
                    reconnect_attempt=reconnect_attempt,
                    retry_delay_seconds=delay,
                )
                await self._sleep(delay)
        finally:
            await self._close_listen_key_async()
            self._queue.put_nowait(_STOP)
            self._emit_lifecycle(StreamLifecycleKind.STOPPED)
            _operator_print("network loop stopped; listen key closed")

    async def _run_connection(self) -> str:
        url = self.websocket_url
        if url is None:
            raise RuntimeError("listen key is not available")
        async with self._connector(
            url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
            max_queue=1_024,
        ) as websocket:
            self._successful_connection_count += 1
            self._emit_lifecycle(
                (
                    StreamLifecycleKind.CONNECTED
                    if self._successful_connection_count == 1
                    else StreamLifecycleKind.RECONNECTED
                )
            )
            receive_task = asyncio.create_task(self._receive_messages(websocket))
            keepalive_task = asyncio.create_task(self._keepalive_loop())
            rotation_task = asyncio.create_task(
                self._sleep(self._max_connection_age_seconds)
            )
            stop_task = asyncio.create_task(self._stop_requested.wait())
            tasks = {receive_task, keepalive_task, rotation_task, stop_task}
            try:
                done, _ = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if stop_task in done:
                    return "stopped"
                if keepalive_task in done:
                    exception = keepalive_task.exception()
                    if exception is not None:
                        raise exception
                    return "disconnected"
                if receive_task in done:
                    return receive_task.result()
                return "rotate"
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _receive_messages(self, websocket: Any) -> str:
        async for raw_message in websocket:
            payload = self._decode_message(raw_message)
            if payload is None:
                continue
            event_type = payload.get("e")
            if event_type == "listenKeyExpired":
                return "listen_key_expired"
            if event_type in _ORDER_EVENT_TYPES:
                self.feed_native_event(payload)
        return "disconnected"

    async def _keepalive_loop(self) -> None:
        while not self._stop_requested.is_set():
            await self._sleep(self._keepalive_interval_seconds)
            if self._stop_requested.is_set():
                return
            try:
                await self._run_sync(self.keepalive)
                _operator_print(
                    "listen key keepalive succeeded; "
                    f"next refresh in {self._keepalive_interval_seconds:g}s"
                )
            except BinanceRequestError as exc:
                if exc.context.code == -1125:
                    raise ListenKeyExpired("Binance listen key expired") from exc
                raise

    @staticmethod
    def _decode_message(raw_message: object) -> dict[str, object] | None:
        if isinstance(raw_message, bytes):
            try:
                raw_message = raw_message.decode("utf-8")
            except UnicodeDecodeError:
                return None
        if not isinstance(raw_message, str):
            return None
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    async def _start_listen_key(self) -> None:
        self._listen_key = await self._run_sync(self._api.start)
        _operator_print("listen key created (value hidden)")

    async def _rebuild_listen_key(self) -> None:
        await self._close_listen_key_async()
        await self._start_listen_key()
        _operator_print("expired listen key replaced (value hidden)")
        self._emit_lifecycle(
            StreamLifecycleKind.LISTEN_KEY_REBUILT,
            reason="listen_key_expired",
        )

    async def _close_listen_key_async(self) -> None:
        if self._listen_key is None:
            return
        try:
            await self._run_sync(self._api.close)
        except Exception:
            # Shutdown and expiry recovery must still clear the stale local key.
            pass
        finally:
            self._listen_key = None

    def _close_listen_key(self) -> None:
        if self._listen_key is None:
            return
        try:
            self._api.close()
        finally:
            self._listen_key = None

    async def events(self) -> AsyncIterator[OrderEvent]:
        while True:
            item = await self._queue.get()
            if item is _STOP:
                return
            assert isinstance(item, OrderEvent)
            yield item

    async def lifecycle_events(self) -> AsyncIterator[StreamLifecycleSignal]:
        """Yield adapter connection signals independently of order events.

        Publishing only uses ``put_nowait`` on an adapter-local queue, so an
        absent or slow observer cannot stall network I/O.
        """

        while True:
            signal = await self._lifecycle_queue.get()
            yield signal
            if signal.kind is StreamLifecycleKind.STOPPED:
                return

    def _emit_lifecycle(
        self,
        kind: StreamLifecycleKind,
        *,
        reason: str | None = None,
        reconnect_attempt: int = 0,
        retry_delay_seconds: float | None = None,
    ) -> None:
        signal = StreamLifecycleSignal(
            kind=kind,
            reason=reason,
            connection_sequence=self._successful_connection_count,
            reconnect_attempt=reconnect_attempt,
            retry_delay_seconds=retry_delay_seconds,
        )
        self._lifecycle_state = signal
        self._lifecycle_queue.put_nowait(signal)

    @staticmethod
    def _to_domain(native: OrderEventSnapshot) -> OrderEvent:
        kind = _event_kind(native)
        event_id = (
            f"{native.market}:{native.symbol}:{native.exchange_order_id}:"
            f"{native.client_order_id}:{native.trade_id}:{native.execution_type}:"
            f"{native.transaction_time_ms}:{native.event_time_ms}"
        )
        return OrderEvent(
            kind=kind,
            client_order_id=native.client_order_id,
            event_id=event_id,
            cumulative_quantity=native.cumulative_quantity,
            average_price=native.average_price,
            last_executed_quantity=native.last_executed_quantity,
            last_executed_price=native.last_executed_price,
            trade_id=(
                str(native.trade_id) if native.trade_id is not None else None
            ),
            commission=native.commission,
            commission_asset=native.commission_asset,
            exchange_order_id=str(native.exchange_order_id),
            reconciled_state=_reconciled_state(native.status),
            reason=native.reject_reason,
            occurred_at=datetime.fromtimestamp(
                native.event_time_ms / 1_000, tz=timezone.utc
            ),
        )


def _event_kind(native: OrderEventSnapshot) -> OrderEventKind:
    if native.execution_type == "TRADE":
        return OrderEventKind.TRADE
    if native.status in {"CANCELED", "CANCELLED"}:
        return OrderEventKind.CANCELED
    if native.status == "REJECTED":
        return OrderEventKind.REJECTED
    if native.status in {"EXPIRED", "EXPIRED_IN_MATCH"}:
        return OrderEventKind.EXPIRED
    return OrderEventKind.ACKNOWLEDGED


def _reconciled_state(status: str) -> OrderState | None:
    return {
        "NEW": OrderState.NEW,
        "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
        "FILLED": OrderState.FILLED,
        "CANCELED": OrderState.CANCELED,
        "CANCELLED": OrderState.CANCELED,
        "REJECTED": OrderState.REJECTED,
        "EXPIRED": OrderState.EXPIRED,
        "EXPIRED_IN_MATCH": OrderState.EXPIRED,
    }.get(status)
