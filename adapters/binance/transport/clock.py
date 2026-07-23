"""Shared server-time offset used by every signed Binance client."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class ServerClock:
    def __init__(self, monotonic_wall_time: Callable[[], float] = time.time):
        self._wall_time = monotonic_wall_time
        self._offset_ms = 0
        self._lock = threading.Lock()

    def now_ms(self) -> int:
        with self._lock:
            offset = self._offset_ms
        return int(self._wall_time() * 1_000) + offset

    @property
    def offset_ms(self) -> int:
        with self._lock:
            return self._offset_ms

    def sync(self, server_time_ms: int, sent_at_ms: int, received_at_ms: int) -> int:
        midpoint_ms = sent_at_ms + (received_at_ms - sent_at_ms) // 2
        offset = int(server_time_ms) - midpoint_ms
        with self._lock:
            self._offset_ms = offset
        return offset

    def sync_from(self, fetch_server_time: Callable[[], int]) -> int:
        sent = int(self._wall_time() * 1_000)
        server_time = int(fetch_server_time())
        received = int(self._wall_time() * 1_000)
        return self.sync(server_time, sent, received)
