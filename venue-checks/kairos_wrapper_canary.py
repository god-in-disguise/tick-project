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
WRAPPER_STATE = ROOT / "venue-checks" / "reports" / "kairos-wrapper" / "wrapper_state.json"


@dataclass(frozen=True)
class SignedTx:
    raw: str
    tx_hash: str


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy/test a tiny internal-payment wrapper through Kairos.")
    parser.add_argument("--account-env", default="GTRADE_AGENT_PK")
    parser.add_argument("--wrapper", default=os.getenv("KAIROS_PAYMENT_WRAPPER", ""))
    parser.add_argument("--deploy", action="store_true")
    parser.add_argument("--wrapper-kind", choices=["msg-value", "fixed-funded", "fixed-funded-2300"], default="msg-value")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--payment-wei", type=int, default=3_000_000_000_000)
    parser.add_argument("--fund-wrapper-wei", type=int, default=0)
    parser.add_argument("--gas", type=int, default=120_000)
    parser.add_argument("--deploy-gas", type=int, default=180_000)
    parser.add_argument(
        "--send-mode",
        choices=["kairos-express", "kairos-bundle", "primary", "direct"],
        default="kairos-express",
    )
    parser.add_argument("--call-data", default="0x", help="Optional calldata for wrapper payment tx.")
    parser.add_argument("--legacy", action="store_true", help="Sign legacy type-0 transactions with gasPrice.")
    parser.add_argument("--gas-price-wei", type=int, default=50_000_000)
    parser.add_argument("--priority-fee-wei", type=int, default=10_000_000)
    parser.add_argument("--base-fee-multiplier", type=Decimal, default=Decimal("2.0"))
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
    address = Web3.to_checksum_address(account.address)
    output_path = output_path_for(args.output)

    start = {
        "type": "kairos_wrapper_start",
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

    wrapper = resolve_wrapper(web3, account, args, output_path)
    print(json.dumps({"type": "wrapper_ready", "wrapper": wrapper}, indent=2))
    if args.fund_wrapper_wei:
        if not args.wrapper_kind.startswith("fixed-funded"):
            raise SystemExit("--fund-wrapper-wei is only valid with --wrapper-kind fixed-funded")
        fund_wrapper(web3, account, wrapper, args, output_path)

    session = requests.Session()
    for index in range(args.samples):
        result = run_wrapper_sample(web3, account, wrapper, args, session, index)
        append_jsonl(output_path, result)
        print(json.dumps(result, indent=2))
        time.sleep(max(0.0, args.interval_seconds))

    footer = {
        "type": "kairos_wrapper_end",
        "createdAt": utc_now(),
        "account": address,
        "wrapper": wrapper,
        "balanceAfterEth": eth_str(web3.eth.get_balance(address)),
        "noncePendingAfter": web3.eth.get_transaction_count(address, "pending"),
        "output": str(output_path),
    }
    append_jsonl(output_path, footer)
    print(json.dumps(footer, indent=2))


def resolve_wrapper(web3: Web3, account: Any, args: argparse.Namespace, output_path: Path) -> str:
    if args.wrapper:
        return Web3.to_checksum_address(args.wrapper)
    state = read_state()
    existing = state.get("wrapper")
    if existing and not args.deploy:
        code = web3.eth.get_code(Web3.to_checksum_address(existing))
        if code and code.hex() != "0x":
            return Web3.to_checksum_address(existing)
    if not args.deploy and not existing:
        raise SystemExit("No wrapper supplied/found. Rerun with --deploy.")
    return deploy_wrapper(web3, account, args, output_path)


def deploy_wrapper(web3: Web3, account: Any, args: argparse.Namespace, output_path: Path) -> str:
    address = Web3.to_checksum_address(account.address)
    nonce_started = time.perf_counter()
    nonce = web3.eth.get_transaction_count(address, "pending")
    nonce_ms = elapsed_ms(nonce_started)
    fees = fee_params(web3, args)
    bytecode = wrapper_initcode(
        Web3.to_checksum_address(KAIROS_PAYMENT_ADDRESS),
        kind=args.wrapper_kind,
        payment_wei=args.payment_wei,
    )
    tx = {
        "from": address,
        "chainId": CHAIN_ID,
        "nonce": nonce,
        "gas": int(args.deploy_gas),
        "data": bytecode,
        **fees,
    }
    signed = sign_tx(account, tx)
    started = time.perf_counter()
    tx_hash = web3.eth.send_raw_transaction(Web3.to_bytes(hexstr=signed.raw))
    send_ms = elapsed_ms(started)
    receipt_started = time.perf_counter()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout, poll_latency=args.receipt_poll)
    receipt_ms = elapsed_ms(receipt_started)
    wrapper = Web3.to_checksum_address(receipt.contractAddress)
    state = {
        "wrapper": wrapper,
        "deployedAt": utc_now(),
        "deployTxHash": tx_hash.hex(),
        "runtimeBytecode": wrapper_runtime_bytecode(
            Web3.to_checksum_address(KAIROS_PAYMENT_ADDRESS),
            kind=args.wrapper_kind,
            payment_wei=args.payment_wei,
        ),
        "wrapperKind": args.wrapper_kind,
        "paymentWei": str(args.payment_wei),
    }
    WRAPPER_STATE.parent.mkdir(parents=True, exist_ok=True)
    WRAPPER_STATE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    result = {
        "type": "wrapper_deploy",
        "createdAt": utc_now(),
        "nonce": nonce,
        "nonceMs": nonce_ms,
        "txHash": tx_hash.hex(),
        "sendMs": send_ms,
        "receiptMs": receipt_ms,
        "status": int(receipt.status),
        "gasUsed": int(receipt.gasUsed),
        "contractAddress": wrapper,
    }
    append_jsonl(output_path, result)
    print(json.dumps(result, indent=2))
    if int(receipt.status) != 1:
        raise SystemExit("Wrapper deployment failed")
    return wrapper


def fund_wrapper(web3: Web3, account: Any, wrapper: str, args: argparse.Namespace, output_path: Path) -> None:
    address = Web3.to_checksum_address(account.address)
    nonce_started = time.perf_counter()
    nonce = web3.eth.get_transaction_count(address, "pending")
    nonce_ms = elapsed_ms(nonce_started)
    fees = fee_params(web3, args)
    signed = sign_tx(
        account,
        {
            "from": address,
            "to": Web3.to_checksum_address(wrapper),
            "value": int(args.fund_wrapper_wei),
            "chainId": CHAIN_ID,
            "nonce": nonce,
            "gas": 50_000,
            **fees,
        },
    )
    started = time.perf_counter()
    tx_hash = web3.eth.send_raw_transaction(Web3.to_bytes(hexstr=signed.raw))
    send_ms = elapsed_ms(started)
    receipt_started = time.perf_counter()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout, poll_latency=args.receipt_poll)
    receipt_ms = elapsed_ms(receipt_started)
    result = {
        "type": "wrapper_fund",
        "createdAt": utc_now(),
        "wrapper": wrapper,
        "nonce": nonce,
        "nonceMs": nonce_ms,
        "valueWei": str(args.fund_wrapper_wei),
        "txHash": tx_hash.hex(),
        "sendMs": send_ms,
        "receiptMs": receipt_ms,
        "status": int(receipt.status),
        "gasUsed": int(receipt.gasUsed),
        "wrapperBalanceWei": str(web3.eth.get_balance(Web3.to_checksum_address(wrapper))),
    }
    append_jsonl(output_path, result)
    print(json.dumps(result, indent=2))
    if int(receipt.status) != 1:
        raise SystemExit("Wrapper funding failed")


def run_wrapper_sample(
    web3: Web3,
    account: Any,
    wrapper: str,
    args: argparse.Namespace,
    session: requests.Session,
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
    build_started = time.perf_counter()
    if args.send_mode == "kairos-bundle":
        signed_txs = [
            sign_tx(
                account,
                {
                    "from": address,
                    "to": address,
                    "value": 0,
                    "chainId": CHAIN_ID,
                    "nonce": nonce,
                    "gas": 30_000,
                    **fees,
                },
            ),
            sign_wrapper_payment(account, address, wrapper, nonce + 1, args, fees),
        ]
    else:
        signed_txs = [sign_wrapper_payment(account, address, wrapper, nonce, args, fees)]
    primary_signed = signed_txs[0]
    payment_signed = signed_txs[-1]
    build_ms = elapsed_ms(build_started)
    result: dict[str, Any] = {
        "type": "kairos_wrapper_sample",
        "createdAt": utc_now(),
        "sample": index + 1,
        "sender": address,
        "wrapper": wrapper,
        "nonce": nonce,
        "paymentWei": str(args.payment_wei),
        "txHash": primary_signed.tx_hash,
        "paymentTxHash": payment_signed.tx_hash if len(signed_txs) > 1 else None,
        "nonceMs": nonce_ms,
        "feeParamsMs": fee_ms,
        "buildSignMs": build_ms,
        "fees": fees,
    }
    try:
        broadcast = broadcast_signed(web3, session, args.send_mode, [item.raw for item in signed_txs])
        result.update(broadcast)
        provider_result = result.get("providerResult")
        if (
            args.send_mode.startswith("kairos")
            and isinstance(provider_result, dict)
            and provider_result.get("expressLaneController") is False
        ):
            result["skippedReceiptWait"] = "kairos_not_express_lane_controller"
            order_id = provider_result.get("id")
            if order_id:
                result["orderInfo"] = kairos_order_info(session, str(order_id))
            result["totalMs"] = elapsed_ms(started)
            return result
        receipt_started = time.perf_counter()
        receipt = web3.eth.wait_for_transaction_receipt(
            Web3.to_bytes(hexstr=primary_signed.tx_hash),
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
            payment_started = time.perf_counter()
            payment_receipt = web3.eth.wait_for_transaction_receipt(
                Web3.to_bytes(hexstr=payment_signed.tx_hash),
                timeout=args.receipt_timeout,
                poll_latency=args.receipt_poll,
            )
            result["paymentReceiptMs"] = elapsed_ms(payment_started)
            result["paymentReceiptBlock"] = int(payment_receipt.blockNumber)
            result["paymentReceiptStatus"] = int(payment_receipt.status)
            result["paymentGasUsed"] = int(payment_receipt.gasUsed)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        receipt = receipt_if_known(web3, primary_signed.tx_hash)
        result["receiptFoundAfterError"] = receipt is not None
        if receipt is not None:
            result["receiptBlock"] = int(receipt.blockNumber)
            result["receiptStatus"] = int(receipt.status)
            result["gasUsed"] = int(receipt.gasUsed)
    order_id = ((result.get("providerResult") or {}).get("id") if isinstance(result.get("providerResult"), dict) else None)
    if order_id:
        result["orderInfo"] = kairos_order_info(session, order_id)
    result["totalMs"] = elapsed_ms(started)
    return result


def sign_wrapper_payment(
    account: Any,
    address: str,
    wrapper: str,
    nonce: int,
    args: argparse.Namespace,
    fees: dict[str, int],
) -> SignedTx:
    return sign_tx(
        account,
        {
            "from": address,
            "to": Web3.to_checksum_address(wrapper),
            "value": 0 if args.wrapper_kind.startswith("fixed-funded") else int(args.payment_wei),
            "data": args.call_data,
            "chainId": CHAIN_ID,
            "nonce": nonce,
            "gas": int(args.gas),
            **fees,
        },
    )


def broadcast_signed(web3: Web3, session: requests.Session, send_mode: str, raw_txs: list[str]) -> dict[str, Any]:
    if send_mode == "kairos-express":
        url = KAIROS_RPC_URL
        method = "timeboost_sendTransaction"
        params: list[Any] = [{"tx": raw_txs[0]}]
    elif send_mode == "kairos-bundle":
        url = KAIROS_RPC_URL
        method = "timeboost_sendBundle"
        params = [
            {
                "txs": raw_txs,
                "pendingTxs": [],
                "replacementUuid": str(uuid.uuid5(uuid.NAMESPACE_URL, raw_txs[0])),
            }
        ]
    elif send_mode == "primary":
        url = os.environ["ARB_RPC_URL"]
        method = "eth_sendRawTransaction"
        params = [raw_txs[0]]
    elif send_mode == "direct":
        url = "https://arb1-sequencer.arbitrum.io/rpc"
        method = "eth_sendRawTransaction"
        params = [raw_txs[0]]
    else:
        raise ValueError(f"unsupported send mode {send_mode}")
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
        "params": params,
    }
    started = time.perf_counter()
    response = session.post(
        url,
        timeout=10,
        headers={"content-type": "application/json", "user-agent": "tick-kairos-wrapper-canary/0.1"},
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
        "sendMode": send_mode,
        "rpcMethod": method,
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


def wrapper_runtime_bytecode(payment_address: str, *, kind: str, payment_wei: int) -> str:
    if kind == "fixed-funded":
        return fixed_funded_wrapper_runtime(payment_address, payment_wei, call_gas=None)
    if kind == "fixed-funded-2300":
        return fixed_funded_wrapper_runtime(payment_address, payment_wei, call_gas=2300)
    # Runtime: payable fallback forwards msg.value to Kairos, reverts if the internal payment fails.
    address_bytes = payment_address.lower().removeprefix("0x")
    return f"0x60006000600060003473{address_bytes}5af11560295760006000f35b60006000fd"


def fixed_funded_wrapper_runtime(payment_address: str, payment_wei: int, *, call_gas: int | None) -> str:
    address_bytes = bytes.fromhex(payment_address.lower().removeprefix("0x"))
    payment_bytes = int(payment_wei).to_bytes(max(1, (int(payment_wei).bit_length() + 7) // 8), "big")
    if len(payment_bytes) > 32:
        raise ValueError("payment too large")
    code = bytearray()
    code.extend([0x36, 0x15, 0x60, 0x00, 0x57])  # if calldatasize == 0, jump to fund path.
    fund_placeholder = 3
    code.extend([0x60, 0x00, 0x60, 0x00, 0x60, 0x00, 0x60, 0x00])
    code.append(0x5F + len(payment_bytes))
    code.extend(payment_bytes)
    code.append(0x73)
    code.extend(address_bytes)
    if call_gas is None:
        code.append(0x5A)  # GAS
    else:
        gas_bytes = int(call_gas).to_bytes(max(1, (int(call_gas).bit_length() + 7) // 8), "big")
        code.append(0x5F + len(gas_bytes))
        code.extend(gas_bytes)
    code.extend([0xF1, 0x15, 0x60, 0x00, 0x57])
    fail_placeholder = len(code) - 2
    code.extend([0x60, 0x00, 0x60, 0x00, 0xF3])
    fail_dest = len(code)
    code[fail_placeholder] = fail_dest
    code.extend([0x5B, 0x60, 0x00, 0x60, 0x00, 0xFD])
    fund_dest = len(code)
    code[fund_placeholder] = fund_dest
    code.extend([0x5B, 0x00])
    return f"0x{code.hex()}"


def wrapper_initcode(payment_address: str, *, kind: str, payment_wei: int) -> str:
    runtime = wrapper_runtime_bytecode(payment_address, kind=kind, payment_wei=payment_wei).removeprefix("0x")
    runtime_len = len(runtime) // 2
    if runtime_len > 255:
        raise ValueError("runtime too large for simple initcode")
    return f"0x60{runtime_len:02x}600c60003960{runtime_len:02x}6000f3{runtime}"


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


def read_state() -> dict[str, Any]:
    if not WRAPPER_STATE.exists():
        return {}
    try:
        return json.loads(WRAPPER_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def output_path_for(raw: str | None) -> Path:
    if raw:
        path = Path(raw)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = ROOT / "venue-checks" / "reports" / "kairos-wrapper" / f"{stamp}.jsonl"
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
