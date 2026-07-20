#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from decimal import Decimal

from gmtrade.config import ProbeConfig
from gmtrade.keeper import fetch_btc_oracle_price, guarded_prices
from gmtrade.official_cli import build_btc_market_increase
from gmtrade.rpc import SolanaRpc
from gmtrade.transaction import sign_with_blockhash
from gmtrade.wallet import load_keypair


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build, sign in memory, and simulate a GMTrade BTC order."
    )
    parser.add_argument("--collateral", type=Decimal, default=Decimal("20"))
    parser.add_argument("--leverage", type=Decimal, default=Decimal("100"))
    parser.add_argument("--side", choices=("long", "short"), default="long")
    parser.add_argument(
        "--acceptable-bps", type=Decimal, default=Decimal("30")
    )
    parser.add_argument(
        "--stop-loss-bps", type=Decimal, default=Decimal("35")
    )
    parser.add_argument("--max-price-age", type=float, default=30)
    parser.add_argument("--full-logs", action="store_true")
    args = parser.parse_args()

    config = ProbeConfig.from_env()
    wallet = load_keypair(config.private_key)
    rpc = SolanaRpc(config.rpc_url)
    balance_lamports = rpc.balance_lamports(wallet.pubkey())
    oracle = fetch_btc_oracle_price()
    if not oracle.is_open:
        raise SystemExit("GMTrade reports the BTC market as closed")
    if oracle.age_seconds > args.max_price_age:
        raise SystemExit(
            f"GMTrade BTC price is stale: {oracle.age_seconds:.1f}s old"
        )
    reference_price, acceptable_price, stop_loss_price = guarded_prices(
        oracle,
        side=args.side,
        acceptable_bps=args.acceptable_bps,
        stop_loss_bps=args.stop_loss_bps,
    )

    started = time.perf_counter()
    order = build_btc_market_increase(
        cli_path=config.cli_path,
        rpc_url=config.rpc_url,
        payer=wallet.pubkey(),
        collateral_usd=args.collateral,
        leverage=args.leverage,
        side=args.side,
        acceptable_price=acceptable_price,
    )
    built_at = time.perf_counter()
    transaction = sign_with_blockhash(
        order.message,
        rpc.latest_blockhash(),
        wallet,
    )
    signed_at = time.perf_counter()
    simulation = rpc.simulate(transaction)
    finished_at = time.perf_counter()

    result = {
        "broadcast": False,
        "wallet": str(wallet.pubkey()),
        "walletSol": str(Decimal(balance_lamports) / Decimal(1_000_000_000)),
        "order": str(order.order),
        "market": "BTC-USD",
        "side": args.side,
        "collateralUsd": str(args.collateral),
        "leverage": str(args.leverage),
        "notionalUsd": str(args.collateral * args.leverage),
        "oracle": {
            "min": str(oracle.minimum),
            "max": str(oracle.maximum),
            "timestamp": oracle.timestamp,
            "ageSeconds": round(oracle.age_seconds, 1),
            "isOpen": oracle.is_open,
        },
        "openGuard": {
            "referencePrice": str(reference_price),
            "acceptablePrice": str(acceptable_price),
            "acceptableBps": str(args.acceptable_bps),
        },
        "fallbackStop": {
            "triggerPrice": str(stop_loss_price),
            "distanceBps": str(args.stop_loss_bps),
            "atomicWithOpen": False,
        },
        "simulationError": simulation.get("err"),
        "unitsConsumed": simulation.get("unitsConsumed"),
        "timingMs": {
            "build": round((built_at - started) * 1000, 1),
            "blockhashAndSign": round((signed_at - built_at) * 1000, 1),
            "simulation": round((finished_at - signed_at) * 1000, 1),
            "total": round((finished_at - started) * 1000, 1),
        },
        "logs" if args.full_logs else "logTail": (
            simulation.get("logs") or []
        )
        if args.full_logs
        else (simulation.get("logs") or [])[-12:],
    }
    print(json.dumps(result, indent=2))
    if simulation.get("err") is not None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
