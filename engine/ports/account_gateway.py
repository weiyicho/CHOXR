"""Read-only account truth used by position planning and risk checks."""

from __future__ import annotations

from typing import Protocol

from engine.domain.account import AccountSnapshot
from engine.domain.instrument import InstrumentId
from engine.domain.position import PositionSnapshot


class AccountGateway(Protocol):
    def get_account_snapshot(self) -> AccountSnapshot: ...

    def get_position_snapshot(self, instrument: InstrumentId) -> PositionSnapshot: ...
