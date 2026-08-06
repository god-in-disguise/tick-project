#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import avantis_trader_sdk
from avantis_trader_sdk import TraderClient
from avantis_trader_sdk.types import TradeInput, TradeInputOrderType
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from web3.logs import DISCARD


BASE_CHAIN_ID = 8453
DEFAULT_BASE_RPC_URL = "https://base-rpc.publicnode.com"
EXPECTED_WALLET = "0xeD1fa479504Ec60DB8a314BfF2DbbD1bB481Db78"
PAIR_INDEX = 1
PAIR = "BTC/USD"
MARGIN_USDC = Decimal("10")
DEFAULT_LEVERAGE = 75
ALLOWED_LEVERAGES = (75, 100, 250, 500)
SLIPPAGE_PERCENTAGE = 1
APPROVAL_USDC = Decimal("10")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Guarded live Avantis BTC ZFP open/close canary."
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-live-risk", action="store_true")
    parser.add_argument("--side", choices=("long", "short"), default="long")
    parser.add_argument(
        "--leverage",
        type=int,
        choices=ALLOWED_LEVERAGES,
        default=DEFAULT_LEVERAGE,
    )
    parser.add_argument("--hold-seconds", type=float, default=1.0)
    parser.add_argument(
        "--rpc-url",
        default=os.getenv("BASE_RPC_URL", DEFAULT_BASE_RPC_URL),
    )
    parser.add_argument("--private-key-env", default="WALLET_PK")
    parser.add_argument(
        "--json-report",
        type=Path,
        help="Optional report path. RPC URLs and private keys are never stored.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(value: Any) -> Any:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "hex") and value.__class__.__name__ in {"HexBytes", "HexStr"}:
        return value.hex()
    if isinstance(value, Mapping):
        return {str(key): normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


class Timeline:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.events: dict[str, dict[str, Any]] = {}

    def mark(self, name: str, **details: Any) -> None:
        self.events[name] = {
            "utc": utc_now(),
            "elapsedMs": round((time.monotonic() - self.started) * 1000, 1),
            **normalize(details),
        }


def load_callbacks_abi() -> list[dict[str, Any]]:
    abi_path = (
        Path(avantis_trader_sdk.__file__).resolve().parent
        / "abis"
        / "TradingCallbacks.sol"
        / "TradingCallbacks.json"
    )
    return json.loads(abi_path.read_text())["abi"]


async def add_gas_buffer(client: TraderClient, tx: dict[str, Any]) -> dict[str, Any]:
    result = dict(tx)
    estimate = await client.get_gas_estimate(result)
    result["gas"] = int(estimate * 1.2)
    return result


async def sign_send_wait(
    client: TraderClient,
    tx: dict[str, Any],
    timeline: Timeline,
    prefix: str,
) -> tuple[Any, Any]:
    tx = dict(tx)
    sender = tx.get("from")
    if not sender:
        raise RuntimeError(f"{prefix} transaction has no sender")
    tx["nonce"] = await client.async_web3.eth.get_transaction_count(
        sender,
        "pending",
    )
    tx = await add_gas_buffer(client, tx)
    signed = await client.sign_transaction(tx)
    raw = signed.rawTransaction
    deterministic_hash = Web3.keccak(raw).hex()
    timeline.mark(
        f"{prefix}_signed",
        txHash=deterministic_hash,
        nonce=tx["nonce"],
        gas=tx["gas"],
        valueWei=tx.get("value", 0),
    )
    tx_hash = await client.send_and_get_transaction_hash(signed)
    timeline.mark(f"{prefix}_broadcast_returned", txHash=tx_hash.hex())
    receipt = await client.async_web3.eth.wait_for_transaction_receipt(
        tx_hash,
        timeout=90,
        poll_latency=0.1,
    )
    timeline.mark(
        f"{prefix}_receipt",
        txHash=tx_hash.hex(),
        blockNumber=receipt["blockNumber"],
        status=receipt["status"],
        gasUsed=receipt["gasUsed"],
        effectiveGasPrice=receipt.get("effectiveGasPrice"),
    )
    if receipt["status"] != 1:
        raise RuntimeError(f"{prefix} transaction reverted: {tx_hash.hex()}")
    return tx_hash, receipt


def decode_initiated(trading: Any, receipt: Any) -> dict[str, Any]:
    events = trading.events.MarketOrderInitiated().process_receipt(
        receipt,
        errors=DISCARD,
    )
    if len(events) != 1:
        raise RuntimeError(f"Expected one MarketOrderInitiated event, got {len(events)}")
    return normalize(events[0]["args"])


async def wait_for_callback(
    client: TraderClient,
    callbacks: Any,
    *,
    order_id: int,
    from_block: int,
    timeout_seconds: float = 45,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    next_block = from_block

    while time.monotonic() < deadline:
        latest = await client.async_web3.eth.block_number
        if latest >= next_block:
            executed = await callbacks.events.MarketExecuted().get_logs(
                fromBlock=next_block,
                toBlock=latest,
            )
            for event in executed:
                if int(event["args"]["orderId"]) == order_id:
                    return {
                        "event": "MarketExecuted",
                        "args": normalize(event["args"]),
                        "transactionHash": event["transactionHash"].hex(),
                        "blockNumber": event["blockNumber"],
                        "logIndex": event["logIndex"],
                        "observedAt": utc_now(),
                    }

            canceled = await callbacks.events.MarketOpenCanceled().get_logs(
                fromBlock=next_block,
                toBlock=latest,
            )
            for event in canceled:
                if int(event["args"]["orderId"]) == order_id:
                    return {
                        "event": "MarketOpenCanceled",
                        "args": normalize(event["args"]),
                        "transactionHash": event["transactionHash"].hex(),
                        "blockNumber": event["blockNumber"],
                        "logIndex": event["logIndex"],
                        "observedAt": utc_now(),
                    }
            next_block = latest + 1
        await asyncio.sleep(0.1)

    raise TimeoutError(f"No callback found for Avantis order {order_id}")


async def wallet_state(client: TraderClient, wallet: str) -> dict[str, float]:
    eth, usdc, allowance = await asyncio.gather(
        client.get_balance(wallet),
        client.get_usdc_balance(wallet),
        client.get_usdc_allowance_for_trading(wallet),
    )
    return {"eth": eth, "usdc": usdc, "allowanceUsdc": allowance}


async def preflight(
    client: TraderClient,
    wallet: str,
) -> dict[str, Any]:
    storage = client.contracts["TradingStorage"]
    state = await wallet_state(client, wallet)
    open_count, pending_open, pending_close, trade_index, callback_address = await asyncio.gather(
        storage.functions.openTradesCount(wallet, PAIR_INDEX).call(),
        storage.functions.pendingMarketOpenCount(wallet, PAIR_INDEX).call(),
        storage.functions.pendingMarketCloseCount(wallet, PAIR_INDEX).call(),
        storage.functions.firstEmptyTradeIndex(wallet, PAIR_INDEX).call(),
        storage.functions.callbacks().call(),
    )
    return {
        **state,
        "openCount": open_count,
        "pendingOpenCount": pending_open,
        "pendingCloseCount": pending_close,
        "nextTradeIndex": trade_index,
        "callbacks": callback_address,
    }


async def build_approval(client: TraderClient, wallet: str, amount: Decimal) -> dict[str, Any]:
    usdc = client.contracts["USDC"]
    storage = client.contracts["TradingStorage"]
    return await usdc.functions.approve(
        storage.address,
        int(amount * 10**6),
    ).build_transaction(
        {
            "from": wallet,
            "chainId": BASE_CHAIN_ID,
            "nonce": await client.get_transaction_count(wallet),
        }
    )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.execute and not args.i_understand_live_risk:
        raise RuntimeError("Live execution also requires --i-understand-live-risk")

    private_key = os.getenv(args.private_key_env, "").strip()
    if not private_key:
        raise RuntimeError(f"{args.private_key_env} is not configured")
    wallet = Account.from_key(private_key).address
    if wallet.lower() != EXPECTED_WALLET.lower():
        raise RuntimeError(f"Signer derives {wallet}, expected {EXPECTED_WALLET}")

    client = TraderClient(args.rpc_url)
    client.set_local_signer(private_key)
    if await client.get_chain_id() != BASE_CHAIN_ID:
        raise RuntimeError("RPC is not Base mainnet")

    timeline = Timeline()
    before = await preflight(client, wallet)
    timeline.mark("preflight_completed", **before)
    if before["openCount"] or before["pendingOpenCount"] or before["pendingCloseCount"]:
        raise RuntimeError(f"Canary wallet is not flat for {PAIR}: {before}")
    if before["usdc"] < float(MARGIN_USDC):
        raise RuntimeError("Insufficient Base USDC for the fixed $10 canary")
    if before["eth"] < 0.001:
        raise RuntimeError("Insufficient Base ETH for execution fees")

    callbacks = client.async_web3.eth.contract(
        address=Web3.to_checksum_address(before["callbacks"]),
        abi=load_callbacks_abi(),
    )

    approval_required = before["allowanceUsdc"] < float(MARGIN_USDC)
    report: dict[str, Any] = {
        "createdAt": utc_now(),
        "execute": args.execute,
        "wallet": wallet,
        "chainId": BASE_CHAIN_ID,
        "pair": PAIR,
        "pairIndex": PAIR_INDEX,
        "side": args.side,
        "marginUsdc": float(MARGIN_USDC),
        "leverage": args.leverage,
        "orderType": "MARKET_ZERO_FEE",
        "holdSeconds": args.hold_seconds,
        "before": before,
        "approvalRequired": approval_required,
    }
    if approval_required and not args.execute:
        report["dryRun"] = {
            "blockedByAllowance": True,
            "requiredAllowanceUsdc": float(APPROVAL_USDC),
        }
        report["timeline"] = timeline.events
        return report

    if approval_required and args.execute:
        approval_tx = await build_approval(client, wallet, APPROVAL_USDC)
        await sign_send_wait(
            client,
            approval_tx,
            timeline,
            "approval",
        )

    trade_input = TradeInput(
        trader=wallet,
        pair_index=PAIR_INDEX,
        trade_index=int(before["nextTradeIndex"]),
        collateral_in_trade=float(MARGIN_USDC),
        is_long=args.side == "long",
        leverage=args.leverage,
        tp=0,
        sl=0,
        timestamp=0,
    )
    timeline.mark("open_build_started")
    open_tx = await client.trade.build_trade_open_tx(
        trade_input,
        TradeInputOrderType.MARKET_ZERO_FEE,
        SLIPPAGE_PERCENTAGE,
    )
    timeline.mark(
        "open_build_completed",
        requestedOpenPrice=trade_input.openPrice / 10**10,
        executionFeeWei=open_tx.get("value", 0),
    )

    if not args.execute:
        gas = None
        if not approval_required:
            gas = await client.get_gas_estimate(open_tx)
        report["dryRun"] = {
            "openGasEstimate": gas,
            "openExecutionFeeWei": open_tx.get("value", 0),
            "openPrice": trade_input.openPrice / 10**10,
        }
        report["timeline"] = timeline.events
        return report

    _, open_receipt = await sign_send_wait(client, open_tx, timeline, "open")
    open_initiated = decode_initiated(client.contracts["Trading"], open_receipt)
    timeline.mark("open_initiated", **open_initiated)
    open_callback = await wait_for_callback(
        client,
        callbacks,
        order_id=int(open_initiated["orderId"]),
        from_block=open_receipt["blockNumber"],
    )
    timeline.mark("open_callback_observed", **open_callback)
    if open_callback["event"] != "MarketExecuted" or not open_callback["args"]["open"]:
        raise RuntimeError(f"Open did not execute: {open_callback}")

    opened_trade = open_callback["args"]["t"]
    trade_index = int(opened_trade["index"])
    collateral_to_close = int(opened_trade["initialPosToken"]) / 10**6
    await asyncio.sleep(args.hold_seconds)

    timeline.mark("close_build_started", tradeIndex=trade_index)
    close_tx = await client.trade.build_trade_close_tx(
        PAIR_INDEX,
        trade_index,
        collateral_to_close,
        trader=wallet,
    )
    timeline.mark(
        "close_build_completed",
        executionFeeWei=close_tx.get("value", 0),
    )
    _, close_receipt = await sign_send_wait(client, close_tx, timeline, "close")
    close_initiated = decode_initiated(client.contracts["Trading"], close_receipt)
    timeline.mark("close_initiated", **close_initiated)
    close_callback = await wait_for_callback(
        client,
        callbacks,
        order_id=int(close_initiated["orderId"]),
        from_block=close_receipt["blockNumber"],
    )
    timeline.mark("close_callback_observed", **close_callback)
    if close_callback["event"] != "MarketExecuted" or close_callback["args"]["open"]:
        raise RuntimeError(f"Close did not execute: {close_callback}")

    after = await preflight(client, wallet)
    timeline.mark("final_state_observed", **after)
    report.update(
        {
            "openInitiated": open_initiated,
            "openCallback": open_callback,
            "closeInitiated": close_initiated,
            "closeCallback": close_callback,
            "after": after,
            "usdcDelta": round(after["usdc"] - before["usdc"], 6),
            "ethDelta": after["eth"] - before["eth"],
            "timeline": timeline.events,
        }
    )
    return report


def print_report(report: dict[str, Any]) -> None:
    print("Avantis ZFP Canary")
    print(
        f"- {report['pair']} {report['side']} ${report['marginUsdc']:.2f} "
        f"at {report['leverage']}x"
    )
    print(f"- execute: {report['execute']}")
    print(f"- wallet: {report['wallet']}")
    print(f"- allowance approval required: {report['approvalRequired']}")
    if "dryRun" in report:
        if report["dryRun"].get("blockedByAllowance"):
            print("- dry run stopped before open build: exact USDC approval is required")
        else:
            print(f"- open gas estimate: {report['dryRun']['openGasEstimate']}")
            print(f"- requested open price: {report['dryRun']['openPrice']}")
        return

    print(f"- open callback tx: {report['openCallback']['transactionHash']}")
    print(f"- open execution price: {int(report['openCallback']['args']['price']) / 10**10}")
    print(f"- close callback tx: {report['closeCallback']['transactionHash']}")
    print(f"- close execution price: {int(report['closeCallback']['args']['price']) / 10**10}")
    print(f"- USDC delta: ${report['usdcDelta']:+.6f}")
    print(f"- ETH delta: {report['ethDelta']:+.9f} ETH")
    print(f"- USDC returned by close: {int(report['closeCallback']['args']['usdcSentToTrader']) / 10**6:.6f}")


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    load_dotenv(root / "builds" / "local-mvp" / ".env")
    args = parse_args()
    report = asyncio.run(run(args))
    print_report(report)

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(normalize(report), indent=2) + "\n")
        print(f"- report: {args.json_report}")


if __name__ == "__main__":
    main()
