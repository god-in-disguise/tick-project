from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLI_PATH = Path("/tmp/gmx-solana-v0.9.0/target/release/gmsol")
BTC_USDC_MARKET = "Dqq58gS1TgRMDouUbdvhhzc51XXTNHG921WLxH9X2eB8"
BTC_INDEX_TOKEN = "BtcTQYRj7HRRk7MwnWiTFj8rWqN2ALt2QYig4cSWqTbv"
DEFAULT_STORE = "CTDLvGGXnoxvqLyTpGzdGLg9pD6JexKxKXSV8tqqo8bN"
KEEPER_GRAPHQL_URL = "https://keeper-prod-api.gmtrade.xyz/graphql"
SOLANA_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@dataclass(frozen=True)
class ProbeConfig:
    rpc_url: str
    private_key: str
    cli_path: Path

    @classmethod
    def from_env(cls) -> "ProbeConfig":
        load_dotenv(REPO_ROOT / ".env")
        rpc_url = os.environ.get("GMTRADE_SOLANA_RPC_URL", "").strip()
        private_key = os.environ.get("GMTRADE_SOLANA_PRIVATE_KEY", "").strip()
        cli_path = Path(
            os.environ.get("GMTRADE_CLI_PATH", str(DEFAULT_CLI_PATH))
        ).expanduser()

        missing = [
            name
            for name, value in (
                ("GMTRADE_SOLANA_RPC_URL", rpc_url),
                ("GMTRADE_SOLANA_PRIVATE_KEY", private_key),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
        if not cli_path.is_file():
            raise RuntimeError(f"GMTrade CLI not found: {cli_path}")

        return cls(rpc_url=rpc_url, private_key=private_key, cli_path=cli_path)
