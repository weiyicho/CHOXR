"""Monotonic timing traces for latency-sensitive execution paths."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from threading import RLock
from time import perf_counter_ns


NanosecondClock = Callable[[], int]


@dataclass(frozen=True, slots=True)
class TimingMeasurement:
    """One elapsed interval measured by a monotonic clock."""

    name: str
    started_ns: int
    finished_ns: int

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            raise ValueError("timing measurement name is required")
        if self.started_ns < 0 or self.finished_ns < 0:
            raise ValueError("monotonic timestamps cannot be negative")
        if self.finished_ns < self.started_ns:
            raise ValueError("timing measurement moved backwards")
        object.__setattr__(self, "name", normalized_name)

    @property
    def duration_ns(self) -> int:
        return self.finished_ns - self.started_ns

    @property
    def duration_ms(self) -> Decimal:
        return Decimal(self.duration_ns) / Decimal(1_000_000)


class ExecutionTimingTrace:
    """Collect named spans and milestone-to-milestone execution latency.

    ``perf_counter_ns`` is intentionally used instead of wall-clock time.  The
    trace therefore remains valid when NTP or Binance server-time correction
    changes the process wall clock while an order is in flight.
    """

    def __init__(
        self,
        execution_id: str,
        *,
        clock_ns: NanosecondClock = perf_counter_ns,
    ) -> None:
        normalized_id = execution_id.strip()
        if not normalized_id:
            raise ValueError("execution_id is required")
        self.execution_id = normalized_id
        self._clock_ns = clock_ns
        self._marks: dict[str, int] = {}
        self._measurements: list[TimingMeasurement] = []
        self._lock = RLock()

    def mark(self, name: str) -> int:
        """Record a unique milestone and return its monotonic timestamp."""

        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("timing mark name is required")
        observed_ns = self._clock_ns()
        with self._lock:
            if normalized_name in self._marks:
                raise ValueError(f"timing mark {normalized_name!r} already exists")
            self._marks[normalized_name] = observed_ns
        return observed_ns

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        """Measure one code span, including spans that raise an exception."""

        started_ns = self._clock_ns()
        try:
            yield
        finally:
            finished_ns = self._clock_ns()
            self._append(name, started_ns, finished_ns)

    def measure_between(
        self,
        name: str,
        start_mark: str,
        finish_mark: str,
    ) -> TimingMeasurement:
        """Materialize latency between two previously recorded milestones."""

        with self._lock:
            try:
                started_ns = self._marks[start_mark]
                finished_ns = self._marks[finish_mark]
            except KeyError as exc:
                raise KeyError(f"unknown timing mark: {exc.args[0]}") from exc
        return self._append(name, started_ns, finished_ns)

    @property
    def measurements(self) -> tuple[TimingMeasurement, ...]:
        with self._lock:
            return tuple(self._measurements)

    def milliseconds(self) -> dict[str, Decimal]:
        """Return measurements keyed by name for logging or persistence."""

        with self._lock:
            result: dict[str, Decimal] = {}
            for measurement in self._measurements:
                if measurement.name in result:
                    raise ValueError(
                        f"duplicate timing measurement {measurement.name!r}"
                    )
                result[measurement.name] = measurement.duration_ms
            return result

    def _append(
        self,
        name: str,
        started_ns: int,
        finished_ns: int,
    ) -> TimingMeasurement:
        measurement = TimingMeasurement(name, started_ns, finished_ns)
        with self._lock:
            self._measurements.append(measurement)
        return measurement
