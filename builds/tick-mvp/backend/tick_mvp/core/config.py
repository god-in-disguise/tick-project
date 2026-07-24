import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    tick_env: str = "local"
    tick_api_host: str = "0.0.0.0"
    tick_api_port: int = 8787
    tick_allow_dev_auth: bool = True
    tick_enqueue_jobs: bool = False
    jwt_secret: str = "dev-only-change-me"
    jwt_ttl_seconds: int = 86400
    google_client_id: str = ""
    tick_google_auth_dev: bool = True

    database_url: str = "postgresql://tick:tick@postgres:5432/tick"
    redis_url: str = "redis://redis:6379/0"
    arq_max_jobs: int = 10
    arq_job_timeout: int = 300
    arq_keep_result_seconds: int = 86400

    default_venue: str = "gtrade"
    quote_ttl_seconds: int = 5
    arb_chain_id: int = 42161
    arb_rpc_url: str = ""
    arb_write_rpc_url: str = ""
    arb_wss_url: str = ""
    custody_provider: str = "development"
    custody_private_key_encryption_key: str = ""
    gas_payer_mode: str = "platform_agent"
    gas_charge_asset: str = "USDC"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        tick_env=os.getenv("TICK_ENV", "local"),
        tick_api_host=os.getenv("TICK_API_HOST", "0.0.0.0"),
        tick_api_port=_int_env("TICK_API_PORT", 8787),
        tick_allow_dev_auth=_bool_env("TICK_ALLOW_DEV_AUTH", True),
        tick_enqueue_jobs=_bool_env("TICK_ENQUEUE_JOBS", False),
        jwt_secret=os.getenv("JWT_SECRET", "dev-only-change-me"),
        jwt_ttl_seconds=_int_env("JWT_TTL_SECONDS", 86400),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        tick_google_auth_dev=_bool_env("TICK_GOOGLE_AUTH_DEV", True),
        database_url=os.getenv("DATABASE_URL", "postgresql://tick:tick@postgres:5432/tick"),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        arq_max_jobs=_int_env("ARQ_MAX_JOBS", 10),
        arq_job_timeout=_int_env("ARQ_JOB_TIMEOUT", 300),
        arq_keep_result_seconds=_int_env("ARQ_KEEP_RESULT_SECONDS", 86400),
        default_venue=os.getenv("DEFAULT_VENUE", "gtrade"),
        quote_ttl_seconds=_int_env("QUOTE_TTL_SECONDS", 5),
        arb_chain_id=_int_env("ARB_CHAIN_ID", 42161),
        arb_rpc_url=os.getenv("ARB_RPC_URL", ""),
        arb_write_rpc_url=os.getenv("ARB_WRITE_RPC_URL", ""),
        arb_wss_url=os.getenv("ARB_WSS_URL", ""),
        custody_provider=os.getenv("CUSTODY_PROVIDER", "development"),
        custody_private_key_encryption_key=os.getenv("CUSTODY_PRIVATE_KEY_ENCRYPTION_KEY", ""),
        gas_payer_mode=os.getenv("GAS_PAYER_MODE", "platform_agent"),
        gas_charge_asset=os.getenv("GAS_CHARGE_ASSET", "USDC"),
    )


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}
