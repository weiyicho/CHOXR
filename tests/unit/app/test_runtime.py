from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from types import SimpleNamespace

from adapters.binance.gateways.order_event_stream import StreamLifecycleKind
from app.runtime import ApplicationRuntime
from engine.domain.order import OrderState


def test_runtime_runs_network_producer_and_engine_consumer_together():
    class FakeOrderStream:
        def __init__(self):
            self.network_started = asyncio.Event()
            self.stop_requested = asyncio.Event()
            self.calls = []

        async def run_network(self):
            self.calls.append("producer-started")
            self.network_started.set()
            await self.stop_requested.wait()
            self.calls.append("producer-stopped")

        def request_stop(self):
            self.calls.append("stop-requested")
            self.stop_requested.set()

    class FakeConsumer:
        def __init__(self, stream):
            self.stream = stream
            self.calls = []

        async def run(self):
            await self.stream.network_started.wait()
            self.calls.append("consumer-started")
            self.stream.request_stop()
            self.calls.append("consumer-stopped")

    async def scenario():
        stream = FakeOrderStream()
        consumer = FakeConsumer(stream)
        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._container = SimpleNamespace(order_event_stream=stream)
        runtime._consumer = consumer
        runtime._reconcile_lock = asyncio.Lock()
        runtime._synchronized = asyncio.Event()

        await asyncio.wait_for(runtime.consume_order_events(), timeout=1)

        assert consumer.calls == ["consumer-started", "consumer-stopped"]
        assert "producer-started" in stream.calls
        assert "producer-stopped" in stream.calls

    asyncio.run(scenario())


def test_connected_and_reconnected_reconcile_before_runtime_is_ready(capsys):
    @dataclass(frozen=True)
    class Signal:
        kind: StreamLifecycleKind

    class FakeOrderStream:
        def __init__(self):
            self.stop_requested = asyncio.Event()
            self.connected_observed = asyncio.Event()

        async def run_network(self):
            await self.stop_requested.wait()

        async def lifecycle_events(self):
            yield Signal(StreamLifecycleKind.CONNECTED)
            await self.connected_observed.wait()
            yield Signal(StreamLifecycleKind.RECONNECTING)
            yield Signal(StreamLifecycleKind.LISTEN_KEY_REBUILT)
            yield Signal(StreamLifecycleKind.RECONNECTED)
            await self.stop_requested.wait()
            yield Signal(StreamLifecycleKind.STOPPED)

        def request_stop(self):
            self.stop_requested.set()

    class FakeConsumer:
        def __init__(self, runtime, reconciler):
            self.runtime = runtime
            self.reconciler = reconciler
            self.observed_ready = []

        async def run(self):
            while len(self.reconciler.thread_ids) < 1:
                await asyncio.sleep(0)
            await self.runtime.wait_until_synchronized()
            self.observed_ready.append(self.runtime.is_synchronized)
            self.runtime._container.order_event_stream.connected_observed.set()
            while len(self.reconciler.thread_ids) < 2:
                await asyncio.sleep(0)
            await self.runtime.wait_until_synchronized()
            self.observed_ready.append(self.runtime.is_synchronized)
            self.runtime._container.order_event_stream.request_stop()

    class RecordingReconciler:
        def __init__(self):
            self.thread_ids = []
            self.active = 0
            self.max_active = 0
            self.guard = threading.Lock()

        def reconcile_after_startup(self):
            with self.guard:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            self.thread_ids.append(threading.get_ident())
            with self.guard:
                self.active -= 1

    async def scenario():
        stream = FakeOrderStream()
        reconciler = RecordingReconciler()
        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._container = SimpleNamespace(order_event_stream=stream)
        runtime._reconciler = reconciler
        runtime._reconcile_lock = asyncio.Lock()
        runtime._synchronized = asyncio.Event()
        consumer = FakeConsumer(runtime, reconciler)
        runtime._consumer = consumer
        event_loop_thread = threading.get_ident()

        await asyncio.wait_for(runtime.consume_order_events(), timeout=1)

        assert len(reconciler.thread_ids) == 2
        assert all(thread_id != event_loop_thread for thread_id in reconciler.thread_ids)
        assert reconciler.max_active == 1
        assert consumer.observed_ready == [True, True]
        assert not runtime.is_synchronized

    asyncio.run(scenario())
    output = capsys.readouterr().out
    assert "[FUNDING][WEBSOCKET] CONNECTED sequence=0" in output
    assert "[FUNDING][RECONCILIATION] BEGIN cause=connected" in output
    assert (
        "[FUNDING][RECONCILIATION] COMPLETE "
        "reconciled_orders=0 unresolved_orders=0"
    ) in output
    assert "[FUNDING][RUNTIME] SYNCHRONIZED sequence=0" in output
    assert "[FUNDING][WEBSOCKET] RECONNECTING sequence=0 attempt=0" in output
    assert "[FUNDING][WEBSOCKET] LISTEN_KEY_REBUILT sequence=0" in output
    assert "[FUNDING][WEBSOCKET] RECONNECTED sequence=0" in output
    assert "[FUNDING][RUNTIME] STOPPED" in output


def test_failed_connection_reconciliation_never_sets_ready():
    @dataclass(frozen=True)
    class Signal:
        kind: StreamLifecycleKind

    class FakeOrderStream:
        def __init__(self):
            self.stop_requested = asyncio.Event()

        async def run_network(self):
            await self.stop_requested.wait()

        async def lifecycle_events(self):
            yield Signal(StreamLifecycleKind.CONNECTED)
            await self.stop_requested.wait()

        def request_stop(self):
            self.stop_requested.set()

    class IdleConsumer:
        async def run(self):
            await asyncio.Event().wait()

    class FailingReconciler:
        def reconcile_after_startup(self):
            raise RuntimeError("REST reconciliation failed")

    async def scenario():
        stream = FakeOrderStream()
        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._container = SimpleNamespace(order_event_stream=stream)
        runtime._consumer = IdleConsumer()
        runtime._reconciler = FailingReconciler()
        runtime._reconcile_lock = asyncio.Lock()
        runtime._synchronized = asyncio.Event()

        try:
            await asyncio.wait_for(runtime.consume_order_events(), timeout=1)
        except RuntimeError as exc:
            assert str(exc) == "REST reconciliation failed"
        else:
            raise AssertionError("reconciliation failure must stop the runtime")
        assert not runtime.is_synchronized

    asyncio.run(scenario())


def test_unresolved_order_after_reconciliation_never_sets_ready():
    @dataclass(frozen=True)
    class Signal:
        kind: StreamLifecycleKind

    class FakeOrderStream:
        def __init__(self):
            self.stop_requested = asyncio.Event()

        async def run_network(self):
            await self.stop_requested.wait()

        async def lifecycle_events(self):
            yield Signal(StreamLifecycleKind.CONNECTED)
            await self.stop_requested.wait()

        def request_stop(self):
            self.stop_requested.set()

    class IdleConsumer:
        async def run(self):
            await asyncio.Event().wait()

    class UnresolvedReconciler:
        def reconcile_after_startup(self):
            return (
                SimpleNamespace(
                    state=OrderState.UNKNOWN,
                    intent=SimpleNamespace(client_order_id="unresolved-order-1"),
                ),
            )

    async def scenario():
        stream = FakeOrderStream()
        runtime = ApplicationRuntime.__new__(ApplicationRuntime)
        runtime._container = SimpleNamespace(order_event_stream=stream)
        runtime._consumer = IdleConsumer()
        runtime._reconciler = UnresolvedReconciler()
        runtime._reconcile_lock = asyncio.Lock()
        runtime._synchronized = asyncio.Event()

        try:
            await asyncio.wait_for(runtime.consume_order_events(), timeout=1)
        except RuntimeError as exc:
            assert str(exc) == (
                "stream reconciliation left unresolved orders: unresolved-order-1"
            )
        else:
            raise AssertionError("unresolved orders must keep the runtime degraded")
        assert not runtime.is_synchronized

    asyncio.run(scenario())
