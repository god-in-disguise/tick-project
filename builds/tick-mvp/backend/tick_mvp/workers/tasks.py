from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from tick_mvp.execution.service import ExecutionService


LOGGER = logging.getLogger("tick.worker")


async def execute_trade_attempt(ctx: dict, execution_attempt_id: str) -> dict[str, str]:
    LOGGER.info("execution attempt queued", extra={"executionAttemptId": execution_attempt_id})
    service: ExecutionService = ctx["execution_service"]
    result = await asyncio.to_thread(service.execute, execution_attempt_id)
    return {key: str(value) for key, value in result.items() if value is not None}


async def prepare_user_wallet(ctx: dict, user_id: str, required_collateral_usd: str) -> dict[str, str]:
    service: ExecutionService = ctx["execution_service"]
    result = await asyncio.to_thread(
        service.prepare_user_wallet,
        user_id,
        Decimal(required_collateral_usd),
    )
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
