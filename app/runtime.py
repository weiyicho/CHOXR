"""Process-level startup reconciliation and event consumption."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from adapters.binance.config import BinanceAccountMode
from adapters.binance.gateways.order_event_stream import StreamLifecycleKind
from engine.domain.order import OrderState
from engine.domain.order_event import OrderEvent, OrderEventKind
from engine.execution import OrderEventConsumer, OrderEventHandler, OrderReconciler

from .container import ApplicationContainer


@dataclass(frozen=True)
class PreflightReport:
    account_mode: BinanceAccountMode
    one_way_mode: bool


class LifecycleSignal(Protocol):
    """Minimum lifecycle signal shape required by the application runtime."""

    kind: StreamLifecycleKind


class LifecycleAwareOrderEventStream(Protocol):
    """Optional stream capability used to close websocket delivery gaps."""

    def lifecycle_events(self) -> AsyncIterator[LifecycleSignal]: ...


def _operator_log(component: str, event: str, **fields: object) -> None:
    """Emit one stable, immediately visible operator-facing status line."""

    details = " ".join(
        f"{name}={value}"
        for name, value in fields.items()
        if value is not None
    )
    suffix = f" {details}" if details else ""
    print(f"[FUNDING][{component}] {event}{suffix}", flush=True)


class ApplicationRuntime:
    def __init__(
        self,
        container: ApplicationContainer,
        *,
        committed_event_queue: asyncio.Queue[OrderEvent] | None = None,
    ) -> None:
        self._container = container
        self._committed_event_queue = committed_event_queue
        self._reconciler = OrderReconciler(container.execution_service)
        self._consumer = OrderEventConsumer(
            container.order_event_stream,
            OrderEventHandler(container.execution_service),
            committed_event_queue=committed_event_queue,
        )
        self._reconcile_lock = asyncio.Lock()
        self._synchronized = asyncio.Event()

    @property
    def is_synchronized(self) -> bool:
        return self._synchronized.is_set()

    async def wait_until_synchronized(self) -> None:
        """Wait until the connected stream has passed REST reconciliation."""

        await self._synchronized.wait()

    def reconcile_after_startup(self) -> None:
        self._reconciler.reconcile_after_startup()

    def preflight(self) -> PreflightReport:
        """Run explicit read-only checks before stream or strategy startup."""

        configured = BinanceAccountMode(
            self._container.settings.binance_account_mode
        )
        observed = self._container.account_gateway.verify_configured_mode(configured)
        one_way = self._container.account_gateway.is_one_way_mode()
        if not one_way:
            raise RuntimeError("CHOXR V1 requires Binance one-way position mode")
        return PreflightReport(account_mode=observed, one_way_mode=one_way)

    async def consume_order_events(self) -> None:
        """Run Binance network production and engine consumption together."""

        self._synchronized.clear()
        _operator_log(
            "RUNTIME",
            "START",
            producer="binance-order-event-producer",
            consumer="engine-order-event-consumer",
        )
        producer = asyncio.create_task(
            self._container.order_event_stream.run_network(),
            name="binance-order-event-producer",
        )
        _operator_log("WEBSOCKET", "PRODUCER_STARTED")
        consumer = asyncio.create_task(
            self._consumer.run(),
            name="engine-order-event-consumer",
        )
        _operator_log("EVENT_CONSUMER", "STARTED")
        tasks = {producer, consumer}
        lifecycle_events = getattr(
            self._container.order_event_stream,
            "lifecycle_events",
            None,
        )
        if callable(lifecycle_events):
            lifecycle = asyncio.create_task(
                self._monitor_stream_lifecycle(lifecycle_events()),
                name="order-stream-lifecycle-monitor",
            )
            tasks.add(lifecycle)
            _operator_log("WEBSOCKET", "LIFECYCLE_MONITOR_STARTED")
        try:
            done, _ = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                exception = task.exception()
                if exception is not None:
                    raise exception
            if any(not task.cancelled() for task in done) and not producer.done():
                self._container.order_event_stream.request_stop()
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            _operator_log("RUNTIME", "CANCELLED")
            raise
        except Exception as exc:
            _operator_log(
                "RUNTIME",
                "ERROR",
                error_type=type(exc).__name__,
            )
            raise
        finally:
            _operator_log("RUNTIME", "SHUTDOWN_BEGIN")
            self._synchronized.clear()
            self._container.order_event_stream.request_stop()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            _operator_log("WEBSOCKET", "PRODUCER_STOPPED")
            _operator_log("EVENT_CONSUMER", "STOPPED")
            if callable(lifecycle_events):
                _operator_log("WEBSOCKET", "LIFECYCLE_MONITOR_STOPPED")
            _operator_log("RUNTIME", "STOPPED")

    async def _monitor_stream_lifecycle(
        self,
        signals: AsyncIterator[LifecycleSignal],
    ) -> None:
        async for signal in signals:
            connection_sequence = getattr(signal, "connection_sequence", 0)
            reconnect_attempt = getattr(signal, "reconnect_attempt", 0)
            retry_delay_seconds = getattr(
                signal,
                "retry_delay_seconds",
                None,
            )
            if signal.kind is StreamLifecycleKind.RECONNECTING:
                _operator_log(
                    "WEBSOCKET",
                    "RECONNECTING",
                    sequence=connection_sequence,
                    attempt=reconnect_attempt,
                    retry_seconds=retry_delay_seconds,
                )
            elif signal.kind is StreamLifecycleKind.LISTEN_KEY_REBUILT:
                # Never print the listen key itself.
                _operator_log(
                    "WEBSOCKET",
                    "LISTEN_KEY_REBUILT",
                    sequence=connection_sequence,
                )
            elif signal.kind is StreamLifecycleKind.STOPPED:
                _operator_log(
                    "WEBSOCKET",
                    "STOPPED",
                    sequence=connection_sequence,
                )
            elif signal.kind is StreamLifecycleKind.CONNECTED:
                _operator_log(
                    "WEBSOCKET",
                    "CONNECTED",
                    sequence=connection_sequence,
                )
            elif signal.kind is StreamLifecycleKind.RECONNECTED:
                _operator_log(
                    "WEBSOCKET",
                    "RECONNECTED",
                    sequence=connection_sequence,
                )
            if signal.kind in {
                StreamLifecycleKind.RECONNECTING,
                StreamLifecycleKind.LISTEN_KEY_REBUILT,
                StreamLifecycleKind.STOPPED,
            }:
                self._synchronized.clear()
                _operator_log(
                    "RUNTIME",
                    "SYNCHRONIZATION_CLEARED",
                    cause=signal.kind.value,
                )
                continue
            if signal.kind in {
                StreamLifecycleKind.CONNECTED,
                StreamLifecycleKind.RECONNECTED,
            }:
                self._synchronized.clear()
                _operator_log(
                    "RECONCILIATION",
                    "BEGIN",
                    cause=signal.kind.value,
                    sequence=connection_sequence,
                )
                async with self._reconcile_lock:
                    try:
                        reconciled = tuple(
                            await asyncio.to_thread(
                                self._reconciler.reconcile_after_startup
                            )
                            or ()
                        )
                    except Exception as exc:
                        _operator_log(
                            "RECONCILIATION",
                            "ERROR",
                            error_type=type(exc).__name__,
                            sequence=connection_sequence,
                        )
                        raise
                    unresolved = tuple(
                        order.intent.client_order_id
                        for order in reconciled
                        if order.state
                        in {
                            OrderState.CREATED,
                            OrderState.SUBMITTING,
                            OrderState.UNKNOWN,
                            OrderState.PENDING_CANCEL,
                        }
                    )
                    if unresolved:
                        _operator_log(
                            "RECONCILIATION",
                            "UNRESOLVED",
                            count=len(unresolved),
                            client_order_ids=",".join(unresolved),
                        )
                        raise RuntimeError(
                            "stream reconciliation left unresolved orders: "
                            + ", ".join(unresolved)
                        )
                    _operator_log(
                        "RECONCILIATION",
                        "COMPLETE",
                        reconciled_orders=len(reconciled),
                        unresolved_orders=0,
                        sequence=connection_sequence,
                    )
                    committed_event_queue = getattr(
                        self,
                        "_committed_event_queue",
                        None,
                    )
                    if committed_event_queue is not None:
                        for order in reconciled:
                            committed_event_queue.put_nowait(
                                OrderEvent(
                                    kind=OrderEventKind.RECONCILED,
                                    client_order_id=(
                                        order.intent.client_order_id
                                    ),
                                    event_id=(
                                        "runtime-reconcile:"
                                        f"{connection_sequence}:"
                                        f"{order.intent.client_order_id}:"
                                        f"{order.state.value}:"
                                        f"{order.cumulative_quantity}"
                                    ),
                                    cumulative_quantity=(
                                        order.cumulative_quantity
                                    ),
                                    average_price=order.average_price,
                                    exchange_order_id=(
                                        order.exchange_order_id
                                    ),
                                    reconciled_state=order.state,
                                    reason=order.rejection_reason,
                                )
                            )
                        _operator_log(
                            "RECONCILIATION",
                            "COMMITTED_EVENTS_PUBLISHED",
                            count=len(reconciled),
                        )
                self._synchronized.set()
                _operator_log(
                    "RUNTIME",
                    "SYNCHRONIZED",
                    sequence=connection_sequence,
                )
