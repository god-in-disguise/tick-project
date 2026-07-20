from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from solders.keypair import Keypair

from .config import ProbeConfig
from .official_cli import BuiltOrder, build_exchange_transaction
from .rpc import SolanaRpc
from .transaction import sign_with_blockhash


@dataclass(frozen=True)
class DirectSubmitResult:
    signature: str
    order: str | None
    build_ms: float
    sign_ms: float
    send_ms: float
    confirm_ms: float
    elapsed_ms: float
    confirmation_status: dict


def submit_built_order(
    rpc: SolanaRpc,
    wallet: Keypair,
    built: BuiltOrder,
    *,
    skip_preflight: bool,
    max_retries: int,
    build_ms: float = 0.0,
) -> DirectSubmitResult:
    started = time.perf_counter()
    sign_started = time.perf_counter()
    transaction = sign_with_blockhash(built.message, rpc.latest_blockhash(), wallet)
    sign_ms = (time.perf_counter() - sign_started) * 1000

    send_started = time.perf_counter()
    signature = rpc.send_transaction(
        transaction,
        skip_preflight=skip_preflight,
        max_retries=max_retries,
    )
    send_ms = (time.perf_counter() - send_started) * 1000
    confirm_ms, status = rpc.wait_for_signature(signature)
    return DirectSubmitResult(
        signature=str(signature),
        order=str(built.order) if built.order is not None else None,
        build_ms=build_ms,
        sign_ms=sign_ms,
        send_ms=send_ms,
        confirm_ms=confirm_ms,
        elapsed_ms=build_ms + (time.perf_counter() - started) * 1000,
        confirmation_status=status,
    )


def submit_exchange(
    config: ProbeConfig,
    rpc: SolanaRpc,
    wallet: Keypair,
    arguments: Sequence[str],
    *,
    priority_lamports: int | None,
    skip_preflight: bool,
    max_retries: int = 3,
) -> DirectSubmitResult:
    build_started = time.perf_counter()
    built = build_exchange_transaction(
        cli_path=Path(config.cli_path),
        rpc_url=config.rpc_url,
        payer=wallet.pubkey(),
        arguments=list(arguments),
        priority_lamports=priority_lamports,
    )
    build_ms = (time.perf_counter() - build_started) * 1000
    result = submit_built_order(
        rpc,
        wallet,
        built,
        skip_preflight=skip_preflight,
        max_retries=max_retries,
        build_ms=build_ms,
    )
    return result
