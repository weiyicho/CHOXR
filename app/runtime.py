"""Process-level startup reconciliation and event consumption."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Protocol

from adapters.binance.config import BinanceAccountMode
from adapters.binance.gateways.order_event_stream import StreamLifecycleKind
from engine.domain.order import OrderState
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


class ApplicationRuntime:
    def __init__(self, container: ApplicationContainer) -> None:
        self._container = container
        self._reconciler = OrderReconciler(container.execution_service)
        self._consumer = OrderEventConsumer(
            container.order_event_stream,
            OrderEventHandler(container.execution_service),
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
        producer = asyncio.create_task(
            self._container.order_event_stream.run_network(),
            name="binance-order-event-producer",
        )
        consumer = asyncio.create_task(
            self._consumer.run(),
            name="engine-order-event-consumer",
        )
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
        finally:
            self._synchronized.clear()
            self._container.order_event_stream.request_stop()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _monitor_stream_lifecycle(
        self,
        signals: AsyncIterator[LifecycleSignal],
    ) -> None:
        async for signal in signals:
            if signal.kind in {
                StreamLifecycleKind.RECONNECTING,
                StreamLifecycleKind.LISTEN_KEY_REBUILT,
                StreamLifecycleKind.STOPPED,
            }:
                self._synchronized.clear()
                continue
            if signal.kind in {
                StreamLifecycleKind.CONNECTED,
                StreamLifecycleKind.RECONNECTED,
            }:
                self._synchronized.clear()
                async with self._reconcile_lock:
                    reconciled = await asyncio.to_thread(
                        self._reconciler.reconcile_after_startup
                    )
                    unresolved = tuple(
                        order.intent.client_order_id
                        for order in reconciled or ()
                        if order.state
                        in {
                            OrderState.CREATED,
                            OrderState.SUBMITTING,
                            OrderState.UNKNOWN,
                            OrderState.PENDING_CANCEL,
                        }
                    )
                    if unresolved:
                        raise RuntimeError(
                            "stream reconciliation left unresolved orders: "
                            + ", ".join(unresolved)
                        )
                self._synchronized.set()
