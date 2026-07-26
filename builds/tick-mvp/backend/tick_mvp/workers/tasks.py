from __future__ import annotations

import logging

from tick_mvp.execution.service import ExecutionService


LOGGER = logging.getLogger("tick.worker")
_EXECUTION_SERVICE: ExecutionService | None = None


async def execute_trade_attempt(ctx: dict, execution_attempt_id: str) -> dict[str, str]:
    LOGGER.info("execution attempt queued", extra={"executionAttemptId": execution_attempt_id})
    service = _execution_service()
    result = service.execute(execution_attempt_id)
    return {key: str(value) for key, value in result.items() if value is not None}


async def execute_withdrawal_request(ctx: dict, withdrawal_id: str) -> dict[str, str]:
    """Placeholder withdrawal task.

    Production implementation validates available USDC, signs from the user's
    platform wallet, broadcasts on Arbitrum, and records gas charged in USDC.
    """
    LOGGER.info("withdrawal request queued", extra={"withdrawalId": withdrawal_id})
    return {"withdrawalId": withdrawal_id, "status": "queued"}


async def reconcile_positions(ctx: dict) -> dict[str, str]:
    LOGGER.info("reconciliation tick")
    return {"status": "ok"}


def _execution_service() -> ExecutionService:
    global _EXECUTION_SERVICE
    if _EXECUTION_SERVICE is None:
        _EXECUTION_SERVICE = ExecutionService()
    return _EXECUTION_SERVICE
