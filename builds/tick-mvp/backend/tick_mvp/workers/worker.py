from __future__ import annotations

import asyncio
import logging
import time

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
from tick_mvp.infrastructure.queue import EXECUTION_JOB


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
    ctx["execution_recovery_task"] = asyncio.create_task(
        _run_execution_recovery(ctx, service)
    )
    ctx["withdrawal_service"] = WithdrawalService(
        gas_funding=gas_funding,
        gas_accounting=gas_accounting,
    )
    logging.getLogger("tick.worker").info("ARQ worker started")


async def shutdown(ctx: dict) -> None:
    for task_name in ("demo_monitor_task", "execution_recovery_task"):
        task: asyncio.Task | None = ctx.get(task_name)
        if task is not None:
            task.cancel()
            try:
                await task
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


async def _run_execution_recovery(ctx: dict, service: ExecutionService) -> None:
    while True:
        try:
            execution_ids = await asyncio.to_thread(service.recoverable_execution_ids)
            bucket = int(time.time() // 5)
            for execution_id in execution_ids:
                await ctx["redis"].enqueue_job(
                    EXECUTION_JOB,
                    execution_id,
                    _job_id=f"execution-recovery:{execution_id}:{bucket}",
                )
            await asyncio.to_thread(service.recover_ambiguous_executions)
        except Exception:
            logging.getLogger("tick.worker").exception("execution redispatch scan failed")
        await asyncio.sleep(1.0)


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
