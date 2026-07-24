from __future__ import annotations

import logging

from tick_mvp.core.config import get_settings
from tick_mvp.workers.tasks import execute_trade_attempt, reconcile_positions


settings = get_settings()
logging.basicConfig(level=logging.INFO)


async def startup(ctx: dict) -> None:
    logging.getLogger("tick.worker").info("ARQ worker started")


async def shutdown(ctx: dict) -> None:
    logging.getLogger("tick.worker").info("ARQ worker stopped")


class WorkerSettings:
    from arq.connections import RedisSettings

    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [execute_trade_attempt, reconcile_positions]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = settings.arq_max_jobs
    job_timeout = settings.arq_job_timeout
    keep_result = settings.arq_keep_result_seconds
