from decimal import Decimal

import pytest

from engine.execution import ExecutionTimingTrace, TimingMeasurement


class FakeClock:
    def __init__(self, *values: int) -> None:
        self._values = iter(values)

    def __call__(self) -> int:
        return next(self._values)


def test_measure_records_exact_monotonic_duration() -> None:
    trace = ExecutionTimingTrace(
        "execution-1",
        clock_ns=FakeClock(1_000_000, 3_750_000),
    )

    with trace.measure("submit_round_trip"):
        pass

    assert trace.measurements == (
        TimingMeasurement("submit_round_trip", 1_000_000, 3_750_000),
    )
    assert trace.milliseconds() == {
        "submit_round_trip": Decimal("2.75")
    }


def test_measure_between_records_fill_to_hedge_gap() -> None:
    trace = ExecutionTimingTrace(
        "execution-1",
        clock_ns=FakeClock(10_000_000, 10_420_000),
    )

    trace.mark("maker_fill_observed")
    trace.mark("hedge_submit_started")
    measurement = trace.measure_between(
        "fill_to_hedge_submit_gap",
        "maker_fill_observed",
        "hedge_submit_started",
    )

    assert measurement.duration_ns == 420_000
    assert measurement.duration_ms == Decimal("0.42")


def test_measure_records_failed_span() -> None:
    trace = ExecutionTimingTrace(
        "execution-1",
        clock_ns=FakeClock(100, 160),
    )

    with pytest.raises(RuntimeError, match="boom"):
        with trace.measure("failed_submit"):
            raise RuntimeError("boom")

    assert trace.measurements[0].duration_ns == 60


def test_duplicate_mark_and_missing_mark_are_rejected() -> None:
    trace = ExecutionTimingTrace(
        "execution-1",
        clock_ns=FakeClock(100, 200),
    )
    trace.mark("fill")

    with pytest.raises(ValueError, match="already exists"):
        trace.mark("fill")
    with pytest.raises(KeyError, match="unknown timing mark"):
        trace.measure_between("gap", "fill", "missing")


def test_wall_clock_regression_cannot_create_negative_duration() -> None:
    with pytest.raises(ValueError, match="moved backwards"):
        TimingMeasurement("invalid", 200, 100)
