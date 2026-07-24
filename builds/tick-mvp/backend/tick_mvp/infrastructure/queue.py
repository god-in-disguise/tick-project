from __future__ import annotations

from tick_mvp.core.config import get_settings
from tick_mvp.domain.schemas import ExecutionAttemptResponse, JobDispatchResponse


EXECUTION_JOB = "execute_trade_attempt"


async def enqueue_execution_attempt(attempt: ExecutionAttemptResponse) -> JobDispatchResponse:
    settings = get_settings()
    # Import ARQ only on the real queue path so contract tests do not need Redis/ARQ installed.
    from arq import create_pool
    from arq.connections import RedisSettings

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(EXECUTION_JOB, attempt.id)
    finally:
        await redis.close()
    return JobDispatchResponse(jobId=job.job_id if job else None, queued=job is not None)
