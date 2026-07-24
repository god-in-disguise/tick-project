from __future__ import annotations

import base64
import re
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from solders.message import VersionedMessage, from_bytes_versioned
from solders.pubkey import Pubkey

from .config import BTC_USDC_MARKET, SOLANA_USDC_MINT


ORDER_PATTERN = re.compile(r"^Order:\s+(\S+)", re.MULTILINE)
TRANSACTION_PATTERN = re.compile(r"^TXN\[0\]:\s+(\S+)", re.MULTILINE)


@dataclass(frozen=True)
class BuiltOrder:
    order: Pubkey | None
    message: VersionedMessage


def build_exchange_transaction(
    *,
    cli_path: Path,
    rpc_url: str,
    payer: Pubkey,
    arguments: list[str],
    priority_lamports: int | None = None,
) -> BuiltOrder:
    command = [
        str(cli_path),
        "--url",
        rpc_url,
        "--serialize-only",
        "base64",
        "--payer",
        str(payer),
    ]
    if priority_lamports is not None:
        command.extend(("--priority-lamports", str(priority_lamports)))
    command.extend(("exchange", *arguments))
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"GMTrade CLI build failed: {detail}")

    order_match = ORDER_PATTERN.search(result.stdout)
    transaction_match = TRANSACTION_PATTERN.search(result.stdout)
    if not transaction_match:
        raise RuntimeError("GMTrade CLI returned an unrecognized transaction build")

    message_bytes = base64.b64decode(transaction_match.group(1), validate=True)
    return BuiltOrder(
        order=Pubkey.from_string(order_match.group(1)) if order_match else None,
        message=from_bytes_versioned(message_bytes),
    )


def build_btc_market_increase(
    *,
    cli_path: Path,
    rpc_url: str,
    payer: Pubkey,
    collateral_usd: Decimal,
    leverage: Decimal,
    side: str,
    acceptable_price: Decimal | None = None,
    priority_lamports: int | None = None,
) -> BuiltOrder:
    if side not in {"long", "short"}:
        raise ValueError("side must be long or short")
    if collateral_usd <= 0 or leverage <= 0:
        raise ValueError("collateral and leverage must be positive")

    size_usd = collateral_usd * leverage
    arguments = [
        "market-increase",
        BTC_USDC_MARKET,
        "--collateral-side",
        "short",
        "--initial-collateral-token",
        SOLANA_USDC_MINT,
        "--initial-collateral-token-amount",
        str(collateral_usd),
        "--side",
        side,
        "--size",
        str(size_usd),
    ]
    if acceptable_price is not None:
        arguments.extend(("--acceptable-price", format(acceptable_price, "f")))
    return build_exchange_transaction(
        cli_path=cli_path,
        rpc_url=rpc_url,
        payer=payer,
        arguments=arguments,
        priority_lamports=priority_lamports,
    )
