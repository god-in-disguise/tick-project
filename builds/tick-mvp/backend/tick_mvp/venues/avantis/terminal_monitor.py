from __future__ import annotations

from decimal import Decimal

from tick_mvp.core.config import Settings
from tick_mvp.venues.avantis.runtime import AvantisRuntime
from tick_mvp.venues.base import TerminalPositionEvent


class AvantisTerminalMonitor:
    def __init__(self, settings: Settings) -> None:
        self._runtime = AvantisRuntime(settings)

    def start(self) -> None:
        self._runtime.start()

    def stop(self) -> None:
        self._runtime.stop()

    def track_owners(self, owners) -> None:
        del owners

    def next_event(self, timeout: float = 0.25) -> TerminalPositionEvent | None:
        return self._runtime.next_terminal_event(timeout)

    def collateral_balance_usd(self, owner: str) -> Decimal:
        return self._runtime.collateral_balance_for_owner(owner)

    def latest_block(self) -> int:
        return self._runtime.latest_block()

    def recover_recent(self, *, from_block: int) -> list[TerminalPositionEvent]:
        return self._runtime.recover_terminal_events(from_block=from_block)
