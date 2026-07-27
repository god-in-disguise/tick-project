from __future__ import annotations

import logging

from tick_mvp.core.config import get_settings
from tick_mvp.execution.service import ExecutionService
from tick_mvp.workers.tasks import (
    execute_trade_attempt,
    execute_withdrawal_request,
    prepare_user_wallet,
    reconcile_positions,
)


settings = get_settings()
logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    service = ExecutionService()
    service.start()
    ctx["execution_service"] = service
    logging.getLogger("tick.worker").info("ARQ worker started")


async def shutdown(ctx: dict) -> None:
    service: ExecutionService | None = ctx.get("execution_service")
    if service is not None:
        service.stop()
    logging.getLogger("tick.worker").info("ARQ worker stopped")


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
