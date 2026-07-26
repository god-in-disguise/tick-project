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
    tick_store_backend: str = "memory"
    tick_run_migrations_on_start: bool = False
    redis_url: str = "redis://redis:6379/0"
    arq_max_jobs: int = 10
    arq_job_timeout: int = 300
    arq_keep_result_seconds: int = 86400

    default_venue: str = "gtrade"
    quote_ttl_seconds: int = 5
    arb_chain_id: int = 42161
    arb_rpc_url: str = ""
    arb_wss_url: str = ""
    custody_provider: str = "development"
    custody_private_key_encryption_key: str = ""
    gas_payer_mode: str = "platform_agent"
    gas_charge_asset: str = "USDC"
    tick_real_quotes_enabled: bool = False
    tick_real_execution_enabled: bool = False
    gtrade_backend_url: str = "https://backend-arbitrum.gains.trade"
    gtrade_pricing_url: str = "https://backend-pricing.eu.gains.trade"
    gtrade_diamond_address: str = "0xFF162c694eAA571f685030649814282eA457f169"
    gtrade_usdc_address: str = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    gtrade_slippage_bps: int = 100
    gtrade_open_wait_seconds: float = 9.0
    gtrade_close_wait_seconds: float = 9.0
    gtrade_rest_poll_seconds: float = 0.20
    gtrade_pairs_ttl_seconds: float = 300.0
    gtrade_charts_ttl_seconds: float = 0.50
    gtrade_auto_approve_usdc: bool = True
    gtrade_fixed_open_gas: int = 2_300_000
    gtrade_fixed_close_gas: int = 2_000_000
    gtrade_fixed_approve_gas: int = 100_000


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
        tick_store_backend=os.getenv("TICK_STORE_BACKEND", "memory"),
        tick_run_migrations_on_start=_bool_env("TICK_RUN_MIGRATIONS_ON_START", False),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        arq_max_jobs=_int_env("ARQ_MAX_JOBS", 10),
        arq_job_timeout=_int_env("ARQ_JOB_TIMEOUT", 300),
        arq_keep_result_seconds=_int_env("ARQ_KEEP_RESULT_SECONDS", 86400),
        default_venue=os.getenv("DEFAULT_VENUE", "gtrade"),
        quote_ttl_seconds=_int_env("QUOTE_TTL_SECONDS", 5),
        arb_chain_id=_int_env("ARB_CHAIN_ID", 42161),
        arb_rpc_url=os.getenv("ARB_RPC_URL", ""),
        arb_wss_url=os.getenv("ARB_WSS_URL", ""),
        custody_provider=os.getenv("CUSTODY_PROVIDER", "development"),
        custody_private_key_encryption_key=os.getenv("CUSTODY_PRIVATE_KEY_ENCRYPTION_KEY", ""),
        gas_payer_mode=os.getenv("GAS_PAYER_MODE", "platform_agent"),
        gas_charge_asset=os.getenv("GAS_CHARGE_ASSET", "USDC"),
        tick_real_quotes_enabled=_bool_env("TICK_REAL_QUOTES_ENABLED", False),
        tick_real_execution_enabled=_bool_env("TICK_REAL_EXECUTION_ENABLED", False),
        gtrade_backend_url=os.getenv("GTRADE_BACKEND_URL", "https://backend-arbitrum.gains.trade"),
        gtrade_pricing_url=os.getenv("GTRADE_PRICING_URL", "https://backend-pricing.eu.gains.trade"),
        gtrade_diamond_address=os.getenv("GTRADE_DIAMOND_ADDRESS") or "0xFF162c694eAA571f685030649814282eA457f169",
        gtrade_usdc_address=os.getenv("GTRADE_USDC_ADDRESS") or "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        gtrade_slippage_bps=_int_env("GTRADE_SLIPPAGE_BPS", 100),
        gtrade_open_wait_seconds=_float_env("GTRADE_OPEN_WAIT_SECONDS", 9.0),
        gtrade_close_wait_seconds=_float_env("GTRADE_CLOSE_WAIT_SECONDS", 9.0),
        gtrade_rest_poll_seconds=_float_env("GTRADE_REST_POLL_SECONDS", 0.20),
        gtrade_pairs_ttl_seconds=_float_env("GTRADE_PAIRS_TTL_SECONDS", 300.0),
        gtrade_charts_ttl_seconds=_float_env("GTRADE_CHARTS_TTL_SECONDS", 0.50),
        gtrade_auto_approve_usdc=_bool_env("GTRADE_AUTO_APPROVE_USDC", True),
        gtrade_fixed_open_gas=_int_env("GTRADE_OPEN_GAS", 2_300_000),
        gtrade_fixed_close_gas=_int_env("GTRADE_CLOSE_GAS", 2_000_000),
        gtrade_fixed_approve_gas=_int_env("GTRADE_APPROVE_GAS", 100_000),
    )


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value else default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default
