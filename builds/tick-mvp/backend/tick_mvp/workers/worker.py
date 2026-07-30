from __future__ import annotations

import asyncio
import logging

from tick_mvp.core.config import get_settings
from tick_mvp.execution.service import ExecutionService
from tick_mvp.wallets.accounting import GasAccountingService
from tick_mvp.wallets.gas import GasFundingService
from tick_mvp.wallets.service import WithdrawalService
from tick_mvp.workers.tasks import (
    execute_trade_attempt,
    execute_withdrawal_request,
    prepare_user_wallet,
    reconcile_positions,
)


settings = get_settings()
logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    gas_funding = GasFundingService()
    gas_accounting = GasAccountingService()
    service = ExecutionService(
        gas_funding=gas_funding,
        gas_accounting=gas_accounting,
    )
    service.start()
    ctx["execution_service"] = service
    ctx["demo_monitor_task"] = asyncio.create_task(_run_demo_monitor(service))
    ctx["withdrawal_service"] = WithdrawalService(
        gas_funding=gas_funding,
        gas_accounting=gas_accounting,
    )
    logging.getLogger("tick.worker").info("ARQ worker started")


async def shutdown(ctx: dict) -> None:
    monitor_task: asyncio.Task | None = ctx.get("demo_monitor_task")
    if monitor_task is not None:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
    service: ExecutionService | None = ctx.get("execution_service")
    if service is not None:
        service.stop()
    withdrawal_service: WithdrawalService | None = ctx.get("withdrawal_service")
    if withdrawal_service is not None:
        withdrawal_service.stop()
    logging.getLogger("tick.worker").info("ARQ worker stopped")


async def _run_demo_monitor(service: ExecutionService) -> None:
    while True:
        await asyncio.to_thread(service.check_demo_positions)
        await asyncio.sleep(0.20)


class WorkerSettings:
    from arq.connections import RedisSettings

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [execute_trade_attempt, prepare_user_wallet, execute_withdrawal_request, reconcile_positions]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = settings.arq_max_jobs
    job_timeout = settings.arq_job_timeout
    keep_result = settings.arq_keep_result_seconds
    poll_delay = 0.05
