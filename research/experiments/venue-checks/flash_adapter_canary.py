#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "builds" / "tick-mvp" / "backend"
sys.path.insert(0, str(BACKEND))

from tick_mvp.core.config import Settings  # noqa: E402
from tick_mvp.domain.states import TradeSide  # noqa: E402
from tick_mvp.venues.flash import FlashVenue  # noqa: E402
from tick_mvp.venues.flash.signing import keypair_from_secret  # noqa: E402


DEFAULT_ENV = Path(__file__).with_name(".env.solana-canary")


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def wallet_secret(env: dict[str, str]) -> str:
    configured = os.getenv("SOLANA_CANARY_KEYPAIR_PATH") or env.get(
        "SOLANA_CANARY_KEYPAIR_PATH"
    )
    if not configured:
        raise RuntimeError("SOLANA_CANARY_KEYPAIR_PATH is missing")
    path = Path(configured)
    if not path.is_absolute():
        path = ROOT / path
    return path.read_text().strip()


def compact_result(result) -> dict:
    payload = asdict(result)
    tx = payload.get("tx") or {}
    tx_payload = tx.get("payload") or {}
    payload["tx"] = {
        "status": tx.get("status"),
        "txHash": tx.get("tx_hash"),
        "hedged": tx_payload.get("hedged"),
    }
    result_payload = payload.get("payload") or {}
    payload["payload"] = {
        "visibleMs": result_payload.get("visibleMs"),
        "buildMs": result_payload.get("buildMs"),
        "signMs": result_payload.get("signMs"),
        "submitRequestMs": result_payload.get("submitRequestMs"),
        "hedged": result_payload.get("hedged"),
        "detectionSource": result_payload.get("detectionSource"),
        "quote": result_payload.get("quote"),
    }
    return payload


def run(args: argparse.Namespace) -> dict:
    env = load_env(Path(args.env))
    secret = wallet_secret(env)
    signer = keypair_from_secret(secret)
    expected = env.get("SOLANA_CANARY_PUBLIC_KEY")
    if expected and str(signer.pubkey()) != expected:
        raise RuntimeError("canary key does not match SOLANA_CANARY_PUBLIC_KEY")

    settings = Settings(
        flash_api_url=env.get("FLASH_API_URL", "https://flashapi.trade"),
        flash_real_execution_enabled=True,
        flash_slippage_percentage=Decimal(args.slippage),
    )
    venue = FlashVenue(settings)
    side = TradeSide(args.side.lower())
    market = f"FLASH-{args.market}-USD"
    report: dict = {
        "startedAt": datetime.now(UTC).isoformat(),
        "owner": str(signer.pubkey()),
        "market": market,
        "side": side.value,
        "amountUsd": args.amount,
        "leverage": args.leverage,
    }
    opened = None
    venue.start()
    try:
        report["wallet"] = venue.prepare_wallet(
            private_key_hex=secret,
            required_collateral_usd=Decimal(args.amount),
        )
        quote = venue.quote_open(
            market=market,
            side=side,
            ticket_usd=Decimal(args.amount),
            leverage=Decimal(args.leverage),
            max_loss_usd=None,
            take_profit_usd=None,
        )
        report["quote"] = {
            "openingAllowed": quote.opening_allowed,
            "effectiveNotionalUsd": str(quote.notional_usd),
            "openCostUsd": str(quote.estimated_open_cost_usd),
            "estimatedCloseCostUsd": str(quote.estimated_close_cost_usd),
            "liquidationPrice": str(quote.liquidation_price),
        }
        if not quote.opening_allowed:
            raise RuntimeError(f"Flash quote is blocked: {quote.payload}")

        prepared: list[dict] = []

        def note_prepared(tx_hash: str, nonce: int | None, _: str) -> None:
            prepared.append({"txHash": tx_hash, "nonce": nonce})

        open_started = time.perf_counter()
        opened = venue.open_position(
            private_key_hex=secret,
            market=market,
            side=side,
            ticket_usd=Decimal(args.amount),
            leverage=Decimal(args.leverage),
            quote_payload=quote.payload,
            stop_loss_price=None,
            take_profit_price=None,
            on_transaction_prepared=note_prepared,
        )
        report["openFullMs"] = round((time.perf_counter() - open_started) * 1000, 3)
        report["open"] = compact_result(opened)
        report["prepared"] = prepared
        time.sleep(args.hold_seconds)

        close_started = time.perf_counter()
        closed = venue.close_position(
            private_key_hex=secret,
            market=market,
            side=side,
            venue_position_id=opened.venue_position_id,
            on_transaction_prepared=note_prepared,
        )
        report["closeFullMs"] = round((time.perf_counter() - close_started) * 1000, 3)
        report["close"] = compact_result(closed)
        report["completedAt"] = datetime.now(UTC).isoformat()
        return report
    finally:
        if opened is not None:
            try:
                owner = str(signer.pubkey())
                basket = venue._client.owner(owner).get("basketPubkey")
                if basket and (venue._client.raw_basket(str(basket)).get("account") or {}).get(
                    "positions"
                ):
                    venue.close_position(
                        private_key_hex=secret,
                        market=market,
                        side=side,
                        venue_position_id=opened.venue_position_id,
                    )
            except Exception:
                pass
        venue.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the production Flash adapter against the dedicated canary wallet"
    )
    parser.add_argument("--env", default=str(DEFAULT_ENV))
    parser.add_argument("--market", choices=["BTC", "ETH"], default="BTC")
    parser.add_argument("--side", choices=["long", "short"], default="long")
    parser.add_argument("--amount", default="10")
    parser.add_argument("--leverage", default="500")
    parser.add_argument("--slippage", default="0.5")
    parser.add_argument("--hold-seconds", type=float, default=1.0)
    parser.add_argument("--json-report")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.execute:
        raise SystemExit("live adapter canary requires --execute")
    result = run(args)
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.json_report:
        path = Path(args.json_report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
