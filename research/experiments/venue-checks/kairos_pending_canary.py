#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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
CHAIN_ID = 42161
KAIROS_RPC_URL = "https://rpc.kairos-timeboost.xyz"
KAIROS_PAYMENT_ADDRESS = "0x60E6a31591392f926e627ED871e670C3e81f1AB8"


@dataclass(frozen=True)
class SignedTx:
    raw: str
    tx_hash: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit a payable state-changing Kairos canary with raw dependency txs in pendingTxs."
    )
    parser.add_argument("--account-env", default="GTRADE_AGENT_PK")
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--contract", default="", help="Existing payable canary contract. Skips deployment when set.")
    parser.add_argument(
        "--submission-mode",
        choices=["bundle-pending", "single"],
        default="bundle-pending",
        help="single uses timeboost_sendTransaction; bundle-pending uses timeboost_sendBundle with raw dependency txs.",
    )
    parser.add_argument("--payment-wei", type=int, default=3_000_000_000_000)
    parser.add_argument(
        "--tx-value-wei",
        type=int,
        default=None,
        help="ETH value on the submitted tx. Defaults to --payment-wei; use 0 for fixed-funded wrappers.",
    )
    parser.add_argument("--deploy-gas", type=int, default=140_000)
    parser.add_argument("--payment-gas", type=int, default=100_000)
    parser.add_argument("--call-data", default="0x755f317c")
    parser.add_argument("--priority-fee-wei", type=int, default=1)
    parser.add_argument("--base-fee-multiplier", type=Decimal, default=Decimal("2.0"))
    parser.add_argument("--legacy", action="store_true", help="Use legacy type-0 gasPrice instead of EIP-1559 fees.")
    parser.add_argument("--gas-price-wei", type=int, default=45_000_000)
    parser.add_argument("--receipt-timeout", type=float, default=12.0)
    parser.add_argument("--receipt-poll", type=float, default=0.1)
    parser.add_argument("--interval-seconds", type=float, default=0.2)
    parser.add_argument("--output", default=None)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-live-risk", action="store_true")
    args = parser.parse_args()

    if args.execute and not args.i_understand_live_risk:
        raise SystemExit("Refusing live writes without --i-understand-live-risk")

    load_dotenv(ROOT / ".env")
    account = load_account(args.account_env)
    web3 = load_web3()
    session = requests.Session()
    address = Web3.to_checksum_address(account.address)
    output_path = output_path_for(args.output)

    start = {
        "type": "kairos_pending_start",
        "createdAt": utc_now(),
        "chainId": int(web3.eth.chain_id),
        "account": address,
        "paymentAddress": Web3.to_checksum_address(KAIROS_PAYMENT_ADDRESS),
        "paymentWei": str(args.payment_wei),
        "samples": args.samples,
        "execute": args.execute,
        "balanceBeforeEth": eth_str(web3.eth.get_balance(address)),
        "noncePendingBefore": web3.eth.get_transaction_count(address, "pending"),
        "output": str(output_path),
    }
    append_jsonl(output_path, start)
    print(json.dumps(start, indent=2))

    if not args.execute:
        print("Dry run only. Add --execute --i-understand-live-risk for live txs.")
        return

    deploy = resolve_canary(web3, account, args, output_path)
    print(json.dumps({"type": "canary_ready", "contract": deploy["contractAddress"]}, indent=2))

    landed: dict[str, Any] | None = None
    for index in range(args.samples):
        result = run_sample(web3, account, session, deploy, args, index)
        append_jsonl(output_path, result)
        print(json.dumps(result, indent=2))
        if result.get("sentToSequencer") or result.get("receiptFoundAfterError") or result.get("receiptStatus") == 1:
            landed = result
            break
        time.sleep(max(0.0, args.interval_seconds))

    footer = {
        "type": "kairos_pending_end",
        "createdAt": utc_now(),
        "account": address,
        "contract": deploy["contractAddress"],
        "landed": landed is not None,
        "landedTxHash": landed.get("txHash") if landed else None,
        "timeboosted": landed.get("timeboosted") if landed else None,
        "balanceAfterEth": eth_str(web3.eth.get_balance(address)),
        "noncePendingAfter": web3.eth.get_transaction_count(address, "pending"),
        "output": str(output_path),
    }
    append_jsonl(output_path, footer)
    print(json.dumps(footer, indent=2))


def deploy_canary(web3: Web3, account: Any, args: argparse.Namespace, output_path: Path) -> dict[str, Any]:
    address = Web3.to_checksum_address(account.address)
    nonce_started = time.perf_counter()
    nonce = web3.eth.get_transaction_count(address, "pending")
    nonce_ms = elapsed_ms(nonce_started)
    fee_started = time.perf_counter()
    fees = fee_params(web3, args)
    fee_ms = elapsed_ms(fee_started)
    signed = sign_tx(
        account,
        {
            "from": address,
            "chainId": CHAIN_ID,
            "nonce": nonce,
            "gas": int(args.deploy_gas),
            "data": kairos_canary_initcode(),
            **fees,
        },
    )
    send_started = time.perf_counter()
    tx_hash = web3.eth.send_raw_transaction(Web3.to_bytes(hexstr=signed.raw))
    send_ms = elapsed_ms(send_started)
    receipt_started = time.perf_counter()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout, poll_latency=args.receipt_poll)
    receipt_ms = elapsed_ms(receipt_started)
    if int(receipt.status) != 1:
        raise SystemExit("Canary deploy failed")
    result = {
        "type": "kairos_canary_deploy",
        "createdAt": utc_now(),
        "nonce": nonce,
        "nonceMs": nonce_ms,
        "feeParamsMs": fee_ms,
        "txHash": tx_hash.hex(),
        "rawTx": signed.raw,
        "sendMs": send_ms,
        "receiptMs": receipt_ms,
        "status": int(receipt.status),
        "gasUsed": int(receipt.gasUsed),
        "contractAddress": Web3.to_checksum_address(receipt.contractAddress),
    }
    append_jsonl(output_path, without_raw(result))
    print(json.dumps(without_raw(result), indent=2))
    return result


def resolve_canary(web3: Web3, account: Any, args: argparse.Namespace, output_path: Path) -> dict[str, Any]:
    if not args.contract:
        return deploy_canary(web3, account, args, output_path)
    contract = Web3.to_checksum_address(args.contract)
    code = web3.eth.get_code(contract)
    if not code or code.hex() == "0x":
        raise SystemExit(f"No code at supplied canary contract {contract}")
    return {
        "type": "kairos_canary_existing",
        "createdAt": utc_now(),
        "contractAddress": contract,
        "txHash": None,
        "rawTx": None,
        "codeLen": len(code),
    }


def run_sample(
    web3: Web3,
    account: Any,
    session: requests.Session,
    deploy: dict[str, Any],
    args: argparse.Namespace,
    index: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    address = Web3.to_checksum_address(account.address)
    nonce_started = time.perf_counter()
    nonce = web3.eth.get_transaction_count(address, "pending")
    nonce_ms = elapsed_ms(nonce_started)
    fee_started = time.perf_counter()
    fees = fee_params(web3, args)
    fee_ms = elapsed_ms(fee_started)
    signed = sign_tx(
        account,
        {
            "from": address,
            "to": Web3.to_checksum_address(deploy["contractAddress"]),
            "value": int(args.payment_wei if args.tx_value_wei is None else args.tx_value_wei),
            "data": args.call_data,
            "chainId": CHAIN_ID,
            "nonce": nonce,
            "gas": int(args.payment_gas),
            **fees,
        },
    )
    result: dict[str, Any] = {
        "type": "kairos_pending_sample",
        "createdAt": utc_now(),
        "sample": index + 1,
        "sender": address,
        "contract": deploy["contractAddress"],
        "nonce": nonce,
        "txHash": signed.tx_hash,
        "deployTxHash": deploy["txHash"],
        "paymentWei": str(args.payment_wei),
        "txValueWei": str(args.payment_wei if args.tx_value_wei is None else args.tx_value_wei),
        "nonceMs": nonce_ms,
        "feeParamsMs": fee_ms,
        "fees": fees,
    }
    try:
        if args.submission_mode == "single":
            broadcast = send_single(session, signed.raw)
        else:
            pending = [str(deploy["rawTx"])] if deploy.get("rawTx") else []
            broadcast = send_bundle(session, signed.raw, pending)
        result.update(broadcast)
        order_id = ((broadcast.get("providerResult") or {}).get("id") if isinstance(broadcast.get("providerResult"), dict) else None)
        if order_id:
            # Kairos order state can lag the submission response, especially for bundles.
            time.sleep(1.0)
            result["orderInfo"] = kairos_order_info(session, str(order_id))
            order_info = result["orderInfo"] if isinstance(result["orderInfo"], dict) else {}
            result["sentToSequencer"] = bool(order_info.get("sent_to_sequencer"))
            result["paymentInitialSim"] = str(order_info.get("payment_initial_sim"))
            result["paymentBlockSim"] = str(order_info.get("payment_block_sim"))
            result["simStatus"] = order_info.get("sim_status")
            result["orderValidation"] = order_info.get("order_validation")
            result["expressLaneStatusCode"] = order_info.get("express_lane_status_code")
            result["expressLaneReason"] = order_info.get("express_lane_reason")
        provider_result = result.get("providerResult")
        if (
            isinstance(provider_result, dict)
            and provider_result.get("expressLaneController") is False
            and not result.get("sentToSequencer")
        ):
            result["skippedReceiptWait"] = "kairos_not_express_lane_controller"
            result["totalMs"] = elapsed_ms(started)
            return result
        if not result.get("sentToSequencer"):
            result["skippedReceiptWait"] = "kairos_not_sent_to_sequencer"
            result["totalMs"] = elapsed_ms(started)
            return result
        receipt_started = time.perf_counter()
        receipt = web3.eth.wait_for_transaction_receipt(
            Web3.to_bytes(hexstr=signed.tx_hash),
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
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        receipt = receipt_if_known(web3, signed.tx_hash)
        result["receiptFoundAfterError"] = receipt is not None
        if receipt is not None:
            result["receiptBlock"] = int(receipt.blockNumber)
            result["receiptStatus"] = int(receipt.status)
            result["gasUsed"] = int(receipt.gasUsed)
            if "timeboosted" in receipt:
                result["timeboosted"] = bool(receipt["timeboosted"])
    result["totalMs"] = elapsed_ms(started)
    return result


def send_bundle(session: requests.Session, raw_tx: str, pending_txs: list[str]) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": "timeboost_sendBundle",
        "params": [
            {
                "txs": [raw_tx],
                "pendingTxs": pending_txs,
                "revertingTxHashes": [],
                "replacementUuid": str(uuid.uuid4()),
            }
        ],
    }
    started = time.perf_counter()
    response = session.post(
        KAIROS_RPC_URL,
        timeout=10,
        headers={"content-type": "application/json", "user-agent": "tick-kairos-pending-canary/0.1"},
        json=payload,
        stream=True,
    )
    headers_ms = elapsed_ms(started)
    body = response.content
    total_ms = elapsed_ms(started)
    response.raise_for_status()
    decoded = json.loads(body.decode("utf-8"))
    if decoded.get("error"):
        raise RuntimeError(decoded["error"])
    return {
        "sendMode": "kairos-bundle-with-pending",
        "rpcMethod": "timeboost_sendBundle",
        "broadcastHeadersMs": headers_ms,
        "broadcastMs": total_ms,
        "providerResult": decoded.get("result"),
    }


def send_single(session: requests.Session, raw_tx: str) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": "timeboost_sendTransaction",
        "params": [{"tx": raw_tx}],
    }
    started = time.perf_counter()
    response = session.post(
        KAIROS_RPC_URL,
        timeout=10,
        headers={"content-type": "application/json", "user-agent": "tick-kairos-pending-canary/0.1"},
        json=payload,
        stream=True,
    )
    headers_ms = elapsed_ms(started)
    body = response.content
    total_ms = elapsed_ms(started)
    response.raise_for_status()
    decoded = json.loads(body.decode("utf-8"))
    if decoded.get("error"):
        raise RuntimeError(decoded["error"])
    return {
        "sendMode": "kairos-single",
        "rpcMethod": "timeboost_sendTransaction",
        "broadcastHeadersMs": headers_ms,
        "broadcastMs": total_ms,
        "providerResult": decoded.get("result"),
    }


def kairos_order_info(session: requests.Session, order_id: str) -> dict[str, Any] | None:
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": "timeboost_getOrderInfo",
        "params": [order_id],
    }
    try:
        response = session.post(KAIROS_RPC_URL, timeout=10, headers={"content-type": "application/json"}, json=payload)
        response.raise_for_status()
        decoded = response.json()
        return decoded.get("result") or decoded
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def kairos_canary_runtime() -> str:
    # Runtime:
    # - increments storage slot 0
    # - forwards full msg.value to Kairos as the final external operation
    # - reverts if the internal payment fails
    runtime = (
        "600054600101600055"
        "600060006000600034"
        "7360e6a31591392f926e627ed871e670c3e81f1ab8"
        "5af115602e57005b60006000fd"
    )
    if len(bytes.fromhex(runtime)) != 52:
        raise RuntimeError("unexpected canary runtime length")
    return f"0x{runtime}"


def kairos_canary_initcode() -> str:
    return "0x6034600c60003960346000f3" + kairos_canary_runtime().removeprefix("0x")


def sign_tx(account: Any, tx: dict[str, Any]) -> SignedTx:
    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    raw_hex = raw.hex()
    if not raw_hex.startswith("0x"):
        raw_hex = f"0x{raw_hex}"
    return SignedTx(raw=raw_hex, tx_hash=Web3.keccak(raw).hex())


def fee_params(web3: Web3, args: argparse.Namespace) -> dict[str, int]:
    if args.legacy:
        return {"gasPrice": int(args.gas_price_wei)}
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    priority = max(int(args.priority_fee_wei), 0)
    return {
        "maxFeePerGas": int(Decimal(base_fee) * args.base_fee_multiplier) + priority,
        "maxPriorityFeePerGas": priority,
    }


def receipt_if_known(web3: Web3, tx_hash: str) -> Any | None:
    try:
        return web3.eth.get_transaction_receipt(Web3.to_bytes(hexstr=tx_hash))
    except Exception:
        return None


def without_raw(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "rawTx"}


def load_account(env_name: str) -> Any:
    value = os.getenv(env_name)
    if not value and env_name == "GTRADE_AGENT_PK":
        value = os.getenv("WALLET_PK")
        env_name = "WALLET_PK"
    if not value:
        raise SystemExit(f"{env_name} missing in root .env")
    key = value.strip().strip('"').strip("'")
    return Account.from_key(key if key.startswith("0x") else f"0x{key}")


def load_web3() -> Web3:
    rpc_url = os.getenv("ARB_RPC_URL")
    if not rpc_url:
        raise SystemExit("ARB_RPC_URL missing in root .env")
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        raise SystemExit("could not connect to ARB_RPC_URL")
    chain_id = int(web3.eth.chain_id)
    if chain_id != CHAIN_ID:
        raise SystemExit(f"RPC chain_id {chain_id}, expected {CHAIN_ID}")
    return web3


def output_path_for(raw: str | None) -> Path:
    if raw:
        path = Path(raw)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = ROOT / "venue-checks" / "reports" / "kairos-pending" / f"{stamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def eth_str(wei: int) -> str:
    return str(Decimal(wei) / Decimal(10**18))


if __name__ == "__main__":
    main()
