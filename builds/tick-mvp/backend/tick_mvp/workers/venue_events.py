from __future__ import annotations

import asyncio
import logging

from tick_mvp.core.config import get_settings
from tick_mvp.execution.terminal_reducer import TerminalEventReducer
from tick_mvp.venues.gtrade.terminal_monitor import GTradeTerminalMonitor


LOGGER = logging.getLogger("tick.venue-events")
OWNER_REFRESH_SECONDS = 1.0
RECOVERY_BLOCKS = 20_000


async def run() -> None:
    settings = get_settings()
    reducer = TerminalEventReducer(settings)
    monitor = GTradeTerminalMonitor(settings)
    monitor.track_owners(await asyncio.to_thread(reducer.wallet_addresses))
    monitor.start()
    try:
        recovered = await asyncio.to_thread(
            monitor.recover_recent,
            from_block=max(0, await asyncio.to_thread(monitor.latest_block) - RECOVERY_BLOCKS),
        )
        for event in recovered:
            await _apply(monitor, reducer, event)

        last_owner_refresh = 0.0
        loop = asyncio.get_running_loop()
        while True:
            now = loop.time()
            if now - last_owner_refresh >= OWNER_REFRESH_SECONDS:
                monitor.track_owners(await asyncio.to_thread(reducer.wallet_addresses))
                last_owner_refresh = now
            event = await asyncio.to_thread(monitor.next_event, 0.25)
            if event is not None:
                await _apply(monitor, reducer, event)
    finally:
        monitor.stop()


async def _apply(monitor, reducer, event) -> None:
    position_id = await asyncio.to_thread(reducer.apply, event)
    if position_id is None:
        return
    LOGGER.info(
        "terminal venue event applied positionId=%s reason=%s source=%s txHash=%s",
        position_id,
        event.reason,
        event.source,
        event.transaction_hash,
    )
    try:
        balance = await asyncio.to_thread(monitor.collateral_balance_usd, event.owner)
        await asyncio.to_thread(reducer.reconcile_wallet, position_id, balance)
    except Exception:
        LOGGER.exception("terminal wallet reconciliation deferred positionId=%s", position_id)
