from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tick_env: str = "local"
    tick_api_host: str = "0.0.0.0"
    tick_api_port: int = 8787

    database_url: str = "postgresql://tick:tick@postgres:5432/tick"
    redis_url: str = "redis://redis:6379/0"

    default_venue: str = "gtrade"
    arb_chain_id: int = 42161
    arb_rpc_url: str = ""
    arb_write_rpc_url: str = ""
    arb_wss_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

