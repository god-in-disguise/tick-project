#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3


ROOT = Path(__file__).resolve().parents[1]
ARBITRUM_CHAIN_ID = 42161
DIRECT_SEQUENCER_URL = "https://arb1-sequencer.arbitrum.io/rpc"
KAIROS_RPC_URL = "https://rpc.kairos-timeboost.xyz"
KAIROS_PAYMENT_ADDRESS = "0x60E6a31591392f926e627ED871e670C3e81f1AB8"


@dataclass(frozen=True)
class Route:
    name: str
    url: str
    method: str
    requires_payment: bool = False


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Arbitrum write routes with tiny live transactions.")
    parser.add_argument("--routes", default="primary,direct,kairos-standard,kairos-express")
    parser.add_argument("--rpc", action="append", default=[], help="Extra route as name=url. Can be repeated.")
    parser.add_argument("--samples", type=int, default=3, help="Samples per route.")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle route order each round.")
    parser.add_argument("--account-env", default="GTRADE_AGENT_PK", help="Private-key env var. Falls back to WALLET_PK when default is missing.")
    parser.add_argument("--to", default="self", help="Transfer recipient: self, kairos, or an address.")
    parser.add_argument("--value-wei", type=int, default=0, help="ETH value sent to self for normal benchmark txs.")
    parser.add_argument("--gas", type=int, default=100_000)
    parser.add_argument("--priority-fee-wei", type=int, default=10_000_000)
    parser.add_argument("--base-fee-multiplier", type=Decimal, default=Decimal("2.0"))
    parser.add_argument("--kairos-payment-wei", type=int, default=0, help="Extra ETH transfer in Kairos bundle mode.")
    parser.add_argument("--allow-zero-kairos-payment", action="store_true")
    parser.add_argument("--receipt-timeout", type=float, default=20)
    parser.add_argument("--receipt-poll", type=float, default=0.1)
    parser.add_argument("--interval-seconds", type=float, default=0.15)
    parser.add_argument("--output", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-live-risk", action="store_true")
    args = parser.parse_args()

    if args.execute and not args.i_understand_live_risk:
        raise SystemExit("Refusing live writes without --i-understand-live-risk")

    load_dotenv(ROOT / ".env")
    account = load_account(args.account_env)
    read_web3 = load_read_web3()
    address = Web3.to_checksum_address(account.address)
    routes = build_routes(args)
    output_path = output_path_for(args.output)
    balances_before = {
        "eth": str(Decimal(read_web3.eth.get_balance(address)) / Decimal(10**18)),
        "noncePending": read_web3.eth.get_transaction_count(address, "pending"),
    }
    header = {
        "type": "benchmark_start",
        "createdAt": utc_now(),
        "chainId": read_web3.eth.chain_id,
        "account": address,
        "routes": [route.name for route in routes],
        "samplesPerRoute": args.samples,
        "execute": args.execute,
        "balancesBefore": balances_before,
        "output": str(output_path),
    }
    print(json.dumps(header, indent=2))
    append_jsonl(output_path, header)

    if not args.execute:
        print("Dry run only. Add --execute --i-understand-live-risk to submit live benchmark txs.")
        return

    sessions = {route.name: requests.Session() for route in routes}
    results: list[dict[str, Any]] = []
    for round_index in range(args.samples):
        round_routes = list(routes)
        if args.shuffle:
            random.shuffle(round_routes)
        for route in round_routes:
            result = run_one(
                read_web3,
                account,
                route,
                args,
                session=sessions[route.name],
                round_index=round_index,
            )
            results.append(result)
            append_jsonl(output_path, result)
            print(json.dumps(result, indent=2))
            time.sleep(max(0.0, args.interval_seconds))

    balances_after = {
        "eth": str(Decimal(read_web3.eth.get_balance(address)) / Decimal(10**18)),
        "noncePending": read_web3.eth.get_transaction_count(address, "pending"),
    }
    summary = summarize(results)
    footer = {
        "type": "benchmark_end",
        "createdAt": utc_now(),
        "account": address,
        "balancesAfter": balances_after,
        "ethDelta": str(Decimal(balances_after["eth"]) - Decimal(balances_before["eth"])),
        "summary": summary,
        "output": str(output_path),
    }
    append_jsonl(output_path, footer)
    print(json.dumps(footer, indent=2))


def load_account(env_name: str) -> Any:
    value = os.getenv(env_name)
    if not value and env_name == "GTRADE_AGENT_PK":
        value = os.getenv("WALLET_PK")
        env_name = "WALLET_PK"
    if not value:
        raise SystemExit(f"{env_name} missing in root .env")
    key = value.strip().strip('"').strip("'")
    return Account.from_key(key if key.startswith("0x") else f"0x{key}")


def load_read_web3() -> Web3:
    rpc_url = os.getenv("ARB_RPC_URL")
    if not rpc_url:
        raise SystemExit("ARB_RPC_URL missing in root .env")
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        raise SystemExit("could not connect to ARB_RPC_URL")
    chain_id = int(web3.eth.chain_id)
    if chain_id != ARBITRUM_CHAIN_ID:
        raise SystemExit(f"RPC chain_id {chain_id}, expected {ARBITRUM_CHAIN_ID}")
    return web3


def build_routes(args: argparse.Namespace) -> list[Route]:
    primary_url = os.getenv("ARB_RPC_URL")
    aliases = {
        "primary": Route("primary", primary_url or "", "eth_sendRawTransaction"),
        "direct": Route("direct", DIRECT_SEQUENCER_URL, "eth_sendRawTransaction"),
        "kairos-standard": Route("kairos-standard", KAIROS_RPC_URL, "eth_sendRawTransaction"),
        "kairos-express": Route("kairos-express", KAIROS_RPC_URL, "timeboost_sendTransaction"),
        "kairos-bundle": Route("kairos-bundle", KAIROS_RPC_URL, "timeboost_sendBundle", requires_payment=True),
    }
    routes: list[Route] = []
    for raw in [part.strip() for part in args.routes.split(",") if part.strip()]:
        if raw not in aliases:
            raise SystemExit(f"Unknown route {raw}; expected one of {', '.join(sorted(aliases))}")
        route = aliases[raw]
        if not route.url:
            raise SystemExit("ARB_RPC_URL missing for primary route")
        if route.requires_payment and args.kairos_payment_wei <= 0 and not args.allow_zero_kairos_payment:
            raise SystemExit("kairos-bundle needs --kairos-payment-wei or --allow-zero-kairos-payment")
        routes.append(route)
    for item in args.rpc:
        if "=" not in item:
            raise SystemExit("--rpc must be name=url")
        name, url = item.split("=", 1)
        routes.append(Route(name.strip(), url.strip(), "eth_sendRawTransaction"))
    if not routes:
        raise SystemExit("No routes configured")
    return routes


def run_one(
    web3: Web3,
    account: Any,
    route: Route,
    args: argparse.Namespace,
    *,
    session: requests.Session,
    round_index: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    address = Web3.to_checksum_address(account.address)
    nonce_started = time.perf_counter()
    nonce = web3.eth.get_transaction_count(address, "pending")
    nonce_ms = elapsed_ms(nonce_started)
    fee_started = time.perf_counter()
    fees = fee_params(web3, args.priority_fee_wei, args.base_fee_multiplier)
    fee_ms = elapsed_ms(fee_started)
    build_started = time.perf_counter()
    if route.name == "kairos-bundle":
        signed_txs = [
            sign_transfer(web3, account, nonce, resolve_recipient(args.to, address), args.value_wei, args.gas, fees),
            sign_transfer(
                web3,
                account,
                nonce + 1,
                Web3.to_checksum_address(KAIROS_PAYMENT_ADDRESS),
                args.kairos_payment_wei,
                args.gas,
                fees,
            ),
        ]
    else:
        signed_txs = [
            sign_transfer(web3, account, nonce, resolve_recipient(args.to, address), args.value_wei, args.gas, fees)
        ]
    build_ms = elapsed_ms(build_started)
    primary = signed_txs[0]
    result: dict[str, Any] = {
        "type": "write_sample",
        "createdAt": utc_now(),
        "round": round_index + 1,
        "route": route.name,
        "urlLabel": label_url(route.url),
        "method": route.method,
        "sender": address,
        "recipient": resolve_recipient(args.to, address),
        "nonce": nonce,
        "txHash": primary["txHash"],
        "paymentTxHash": signed_txs[1]["txHash"] if len(signed_txs) > 1 else None,
        "nonceMs": nonce_ms,
        "feeParamsMs": fee_ms,
        "buildSignMs": build_ms,
        "fees": fees,
    }
    try:
        broadcast_result = broadcast_route(route, signed_txs, session)
        result.update(broadcast_result)
        receipt_started = time.perf_counter()
        receipt = web3.eth.wait_for_transaction_receipt(
            Web3.to_bytes(hexstr=primary["txHash"]),
            timeout=args.receipt_timeout,
            poll_latency=args.receipt_poll,
        )
        result["receiptMs"] = elapsed_ms(receipt_started)
        result["receiptBlock"] = int(receipt.blockNumber)
        result["receiptStatus"] = int(receipt.status)
        result["gasUsed"] = int(receipt.gasUsed)
        result["effectiveGasPrice"] = int(
            getattr(receipt, "effectiveGasPrice", 0) or receipt.get("effectiveGasPrice", 0) or 0
        )
        if "timeboosted" in receipt:
            result["timeboosted"] = bool(receipt["timeboosted"])
        if len(signed_txs) > 1:
            payment_receipt = web3.eth.wait_for_transaction_receipt(
                Web3.to_bytes(hexstr=signed_txs[1]["txHash"]),
                timeout=args.receipt_timeout,
                poll_latency=args.receipt_poll,
            )
            result["paymentReceiptStatus"] = int(payment_receipt.status)
            result["paymentGasUsed"] = int(payment_receipt.gasUsed)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        found = receipt_if_known(web3, primary["txHash"])
        if found is not None:
            result["receiptFoundAfterError"] = True
            result["receiptBlock"] = int(found.blockNumber)
            result["receiptStatus"] = int(found.status)
            result["gasUsed"] = int(found.gasUsed)
        else:
            result["receiptFoundAfterError"] = False
    result["totalMs"] = elapsed_ms(started)
    return result


def sign_transfer(
    web3: Web3,
    account: Any,
    nonce: int,
    to: str,
    value_wei: int,
    gas: int,
    fees: dict[str, int],
) -> dict[str, str]:
    tx = {
        "from": Web3.to_checksum_address(account.address),
        "to": Web3.to_checksum_address(to),
        "value": int(value_wei),
        "chainId": ARBITRUM_CHAIN_ID,
        "nonce": int(nonce),
        "gas": int(gas),
        **fees,
    }
    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    return {
        "raw": raw.hex() if raw.hex().startswith("0x") else f"0x{raw.hex()}",
        "txHash": Web3.keccak(raw).hex(),
    }


def resolve_recipient(raw: str, sender: str) -> str:
    value = raw.strip()
    if value.lower() == "self":
        return Web3.to_checksum_address(sender)
    if value.lower() == "kairos":
        return Web3.to_checksum_address(KAIROS_PAYMENT_ADDRESS)
    return Web3.to_checksum_address(value)


def broadcast_route(route: Route, signed_txs: list[dict[str, str]], session: requests.Session) -> dict[str, Any]:
    if route.method == "eth_sendRawTransaction":
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "eth_sendRawTransaction",
            "params": [signed_txs[0]["raw"]],
        }
    elif route.method == "timeboost_sendTransaction":
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "timeboost_sendTransaction",
            "params": [{"tx": signed_txs[0]["raw"]}],
        }
    elif route.method == "timeboost_sendBundle":
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "timeboost_sendBundle",
            "params": [
                {
                    "txs": [item["raw"] for item in signed_txs],
                    "pendingTxs": [],
                    "replacementUuid": str(uuid.uuid5(uuid.NAMESPACE_URL, signed_txs[0]["txHash"])),
                }
            ],
        }
    else:
        raise RuntimeError(f"unsupported method {route.method}")

    started = time.perf_counter()
    response = session.post(
        route.url,
        timeout=10,
        headers={"content-type": "application/json", "user-agent": "tick-write-router-benchmark/0.1"},
        json=payload,
        stream=True,
    )
    response_headers_ms = elapsed_ms(started)
    body = response.content
    response_total_ms = elapsed_ms(started)
    response.raise_for_status()
    decoded = json.loads(body.decode("utf-8"))
    if decoded.get("error"):
        raise RuntimeError(decoded["error"])
    return {
        "broadcastHeadersMs": response_headers_ms,
        "broadcastMs": response_total_ms,
        "providerResult": decoded.get("result"),
    }


def fee_params(web3: Web3, priority_fee_wei: int, base_fee_multiplier: Decimal) -> dict[str, int]:
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    priority = max(int(priority_fee_wei), 0)
    return {
        "maxFeePerGas": int(Decimal(base_fee) * base_fee_multiplier) + priority,
        "maxPriorityFeePerGas": priority,
    }


def receipt_if_known(web3: Web3, tx_hash: str) -> Any | None:
    try:
        return web3.eth.get_transaction_receipt(Web3.to_bytes(hexstr=tx_hash))
    except Exception:
        return None


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_route: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        by_route.setdefault(str(item["route"]), []).append(item)
    summary: dict[str, Any] = {}
    for route, items in by_route.items():
        ok = [item for item in items if not item.get("error") and item.get("receiptStatus") == 1]
        summary[route] = {
            "samples": len(items),
            "ok": len(ok),
            "errors": len(items) - len(ok),
            "broadcastMs": stats([float(item["broadcastMs"]) for item in ok if item.get("broadcastMs") is not None]),
            "receiptMs": stats([float(item["receiptMs"]) for item in ok if item.get("receiptMs") is not None]),
            "totalMs": stats([float(item["totalMs"]) for item in ok if item.get("totalMs") is not None]),
        }
    return summary


def stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None, "min": None, "max": None}
    ordered = sorted(values)
    return {
        "p50": percentile(ordered, 0.50),
        "p95": percentile(ordered, 0.95),
        "min": round(ordered[0], 1),
        "max": round(ordered[-1], 1),
    }


def percentile(ordered: list[float], pct: float) -> float:
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * pct))))
    return round(ordered[index], 1)


def output_path_for(raw: str | None) -> Path:
    if raw:
        path = Path(raw)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = ROOT / "venue-checks" / "reports" / "arbitrum-write-router" / f"{stamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def label_url(url: str) -> str:
    if "arb1-sequencer.arbitrum.io" in url:
        return "arbitrum_direct_sequencer"
    if "kairos-timeboost.xyz" in url:
        return "kairos_timeboost"
    if "quicknode" in url.lower():
        return "quicknode"
    if "alchemy" in url.lower():
        return "alchemy"
    if "chainstack" in url.lower():
        return "chainstack"
    return "custom_rpc"


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


if __name__ == "__main__":
    main()
