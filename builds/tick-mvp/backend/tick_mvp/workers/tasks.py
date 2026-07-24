from __future__ import annotations

import logging


LOGGER = logging.getLogger("tick.worker")


async def execute_trade_attempt(ctx: dict, execution_attempt_id: str) -> dict[str, str]:
    """Placeholder execution task.

    The next pass will load the execution attempt from Postgres and call the
    gTrade connector. Keeping this task tiny makes the worker boundary visible
    without mixing live venue code into the API process.
    """
    LOGGER.info("execution attempt queued", extra={"executionAttemptId": execution_attempt_id})
    return {"executionAttemptId": execution_attempt_id, "status": "queued"}


async def reconcile_positions(ctx: dict) -> dict[str, str]:
    LOGGER.info("reconciliation tick")
    return {"status": "ok"}

