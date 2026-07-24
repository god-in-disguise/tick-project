from __future__ import annotations

from tick_mvp.core.config import get_settings
from tick_mvp.domain.schemas import ExecutionAttemptResponse, JobDispatchResponse, WithdrawalResponse


EXECUTION_JOB = "execute_trade_attempt"
WITHDRAWAL_JOB = "execute_withdrawal_request"


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


async def enqueue_withdrawal_request(withdrawal: WithdrawalResponse) -> JobDispatchResponse:
    settings = get_settings()
    from arq import create_pool
    from arq.connections import RedisSettings

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(WITHDRAWAL_JOB, withdrawal.id)
    finally:
        await redis.close()
    return JobDispatchResponse(jobId=job.job_id if job else None, queued=job is not None)
