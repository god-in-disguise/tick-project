from __future__ import annotations

import time

from tick_mvp.core.config import get_settings
from tick_mvp.domain.schemas import ExecutionAttemptResponse, JobDispatchResponse, WithdrawalResponse


EXECUTION_JOB = "execute_trade_attempt"
WITHDRAWAL_JOB = "execute_withdrawal_request"
WALLET_PREPARATION_JOB = "prepare_user_wallet"


async def enqueue_execution_attempt(attempt: ExecutionAttemptResponse) -> JobDispatchResponse:
    settings = get_settings()
    # Import ARQ only on the real queue path so contract tests do not need Redis/ARQ installed.
    from arq import create_pool
    from arq.connections import RedisSettings

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(EXECUTION_JOB, attempt.id, _job_id=f"execution:{attempt.id}")
    finally:
        await redis.close()
    return JobDispatchResponse(jobId=job.job_id if job else None, queued=job is not None)


async def enqueue_wallet_preparation(
    user_id: str,
    required_collateral_usd: str,
    venue_name: str | None = None,
) -> JobDispatchResponse:
    settings = get_settings()
    from arq import create_pool
    from arq.connections import RedisSettings

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        normalized_venue = (venue_name or settings.default_venue).strip().lower()
        bucket_seconds = 30 if normalized_venue == "flash" else 10
        bucket = int(time.time() // bucket_seconds)
        job = await redis.enqueue_job(
            WALLET_PREPARATION_JOB,
            user_id,
            required_collateral_usd,
            venue_name,
            _job_id=(
                f"wallet-preparation:{user_id}:{venue_name or 'default'}:"
                f"{required_collateral_usd}:{bucket}"
            ),
        )
    finally:
        await redis.close()
    return JobDispatchResponse(jobId=job.job_id if job else None, queued=job is not None)


async def enqueue_withdrawal_request(withdrawal: WithdrawalResponse) -> JobDispatchResponse:
    settings = get_settings()
    from arq import create_pool
    from arq.connections import RedisSettings

    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job = await redis.enqueue_job(WITHDRAWAL_JOB, withdrawal.id, _job_id=f"withdrawal:{withdrawal.id}")
    finally:
        await redis.close()
    return JobDispatchResponse(jobId=job.job_id if job else None, queued=job is not None)
