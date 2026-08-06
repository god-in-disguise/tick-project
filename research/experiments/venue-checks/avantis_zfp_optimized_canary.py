#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from avantis_trader_sdk import TraderClient
from avantis_trader_sdk.types import LazerPriceFeedResponse, TradeInput
from dotenv import load_dotenv
from eth_account import Account
from hexbytes import HexBytes
import websockets
from web3 import Web3
from web3.exceptions import MismatchedABI

from avantis_zfp_canary import (
    ALLOWED_LEVERAGES,
    APPROVAL_USDC,
    BASE_CHAIN_ID,
    DEFAULT_BASE_RPC_URL,
    DEFAULT_LEVERAGE,
    EXPECTED_WALLET,
    MARGIN_USDC,
    PAIR,
    PAIR_INDEX,
    SLIPPAGE_PERCENTAGE,
    Timeline,
    build_approval,
    decode_initiated,
    load_callbacks_abi,
    normalize,
    preflight,
    sign_send_wait,
    utc_now,
)
from avantis_zfp_receipt_analysis import TRADING_CALLBACK_ABI, analyze_leg, load_abi


OPEN_GAS_FALLBACK = 720_000
CLOSE_GAS_FALLBACK = 660_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prewarmed SSE/WSS Avantis BTC ZFP live latency canary."
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
    parser.add_argument("--wss-url", default=os.getenv("BASE_WSS_URL"))
    parser.add_argument("--private-key-env", default="WALLET_PK")
    parser.add_argument("--max-price-age-ms", type=float, default=1_000)
    parser.add_argument(
        "--callback-mode",
        choices=("pendingLogs", "logs"),
        default="pendingLogs",
    )
    parser.add_argument("--json-report", type=Path)
    return parser.parse_args()


def derive_wss_url(rpc_url: str) -> str:
    if rpc_url.startswith("https://"):
        return "wss://" + rpc_url.removeprefix("https://")
    if rpc_url.startswith("http://"):
        return "ws://" + rpc_url.removeprefix("http://")
    raise ValueError("Cannot derive WSS URL from RPC URL")


@dataclass
class PriceObservation:
    price: float
    source_timestamp_ms: int
    received_monotonic: float
    received_at: str


class LazerTape:
    def __init__(self, client: TraderClient, feed_id: int) -> None:
        self.client = client
        self.feed_id = feed_id
        self.latest: PriceObservation | None = None
        self.ready = asyncio.Event()
        self.task: asyncio.Task[Any] | None = None

    def _on_price(self, response: LazerPriceFeedResponse) -> None:
        feed = next(
            (
                item
                for item in response.price_feeds
                if item.price_feed_id == self.feed_id
            ),
            None,
        )
        if feed is None:
            return
        self.latest = PriceObservation(
            price=float(feed.converted_price),
            source_timestamp_ms=response.timestamp_ms,
            received_monotonic=time.monotonic(),
            received_at=utc_now(),
        )
        self.ready.set()

    async def start(self) -> None:
        self.task = asyncio.create_task(
            self.client.feed_client.listen_for_lazer_price_updates(
                [self.feed_id],
                self._on_price,
            )
        )
        await asyncio.wait_for(self.ready.wait(), timeout=15)

    async def fresh(self, max_age_ms: float) -> PriceObservation:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            observation = self.latest
            if observation is not None:
                age_ms = (time.monotonic() - observation.received_monotonic) * 1000
                if age_ms <= max_age_ms:
                    return observation
            self.ready.clear()
            await asyncio.wait_for(self.ready.wait(), timeout=5)
        raise TimeoutError("No fresh Pyth Lazer price")

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


class CallbackStream:
    def __init__(
        self,
        wss_url: str,
        callback_address: str,
        wallet: str,
        subscription_type: str,
    ) -> None:
        self.wss_url = wss_url
        self.callback_address = Web3.to_checksum_address(callback_address)
        self.wallet = wallet.lower()
        self.subscription_type = subscription_type
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.task: asyncio.Task[Any] | None = None
        self.websocket: Any = None
        self.contract = Web3().eth.contract(
            address=self.callback_address,
            abi=load_callbacks_abi(),
        )

    async def start(self) -> None:
        self.websocket = await websockets.connect(
            self.wss_url,
            ping_interval=20,
            ping_timeout=20,
            max_size=2**20,
        )
        await self.websocket.send(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": [
                        self.subscription_type,
                        {"address": self.callback_address},
                    ],
                }
            )
        )
        response = json.loads(await asyncio.wait_for(self.websocket.recv(), timeout=10))
        if "result" not in response:
            raise RuntimeError(f"Base WSS subscription failed: {response}")
        self.task = asyncio.create_task(self._consume())

    @staticmethod
    def _format_log(log: dict[str, Any]) -> dict[str, Any]:
        def optional_hex_bytes(value: Any) -> HexBytes | None:
            return HexBytes(value) if value else None

        def optional_hex_int(value: Any) -> int | None:
            return int(value, 16) if value is not None else None

        return {
            "address": Web3.to_checksum_address(log["address"]),
            "topics": [HexBytes(topic) for topic in log["topics"]],
            "data": HexBytes(log["data"]),
            "blockNumber": optional_hex_int(log.get("blockNumber")),
            "transactionHash": optional_hex_bytes(log.get("transactionHash")),
            "transactionIndex": optional_hex_int(log.get("transactionIndex")),
            "blockHash": optional_hex_bytes(log.get("blockHash")),
            "logIndex": optional_hex_int(log.get("logIndex")),
            "removed": bool(log.get("removed", False)),
        }

    async def _consume(self) -> None:
        async for raw_message in self.websocket:
            message = json.loads(raw_message)
            if message.get("method") != "eth_subscription":
                continue
            log = self._format_log(message["params"]["result"])
            for name in ("MarketExecuted", "MarketOpenCanceled"):
                try:
                    decoded = getattr(self.contract.events, name)().process_log(log)
                except (MismatchedABI, KeyError, TypeError, ValueError):
                    continue
                args = normalize(decoded["args"])
                trader = args.get("t", {}).get("trader") or args.get("trader")
                if not trader or trader.lower() != self.wallet:
                    continue
                await self.queue.put(
                    {
                        "event": name,
                        "args": args,
                        "transactionHash": decoded["transactionHash"].hex(),
                        "blockNumber": decoded["blockNumber"],
                        "logIndex": decoded["logIndex"],
                        "receivedMonotonic": time.monotonic(),
                        "receivedAt": utc_now(),
                    }
                )
                break

    async def wait_for(self, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            event = await asyncio.wait_for(
                self.queue.get(),
                timeout=max(0.1, deadline - time.monotonic()),
            )
            if predicate(event):
                return event
        raise TimeoutError("No matching Avantis callback arrived over WSS")

    async def close(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.websocket is not None:
            await self.websocket.close()


@dataclass
class FeeEnvelope:
    execution_fee_wei: int
    max_priority_fee_per_gas: int
    max_fee_per_gas: int


async def warm_fee_envelope(client: TraderClient) -> FeeEnvelope:
    block, tip, execution_fee = await asyncio.gather(
        client.async_web3.eth.get_block("latest"),
        client.async_web3.eth.max_priority_fee,
        client.trade.get_trade_execution_fee(),
    )
    base_fee = int(block["baseFeePerGas"])
    return FeeEnvelope(
        execution_fee_wei=int(execution_fee),
        max_priority_fee_per_gas=int(tip),
        max_fee_per_gas=base_fee * 2 + int(tip),
    )


def common_tx(
    *,
    wallet: str,
    nonce: int,
    data: str,
    to: str,
    gas: int,
    fees: FeeEnvelope,
) -> dict[str, Any]:
    return {
        "type": 2,
        "chainId": BASE_CHAIN_ID,
        "from": wallet,
        "to": to,
        "nonce": nonce,
        "gas": gas,
        "value": fees.execution_fee_wei,
        "data": data,
        "maxPriorityFeePerGas": fees.max_priority_fee_per_gas,
        "maxFeePerGas": fees.max_fee_per_gas,
    }


def open_tx(
    client: TraderClient,
    *,
    wallet: str,
    trade_index: int,
    leverage: int,
    is_long: bool,
    price: float,
    nonce: int,
    gas: int,
    fees: FeeEnvelope,
) -> dict[str, Any]:
    trade = TradeInput(
        trader=wallet,
        pair_index=PAIR_INDEX,
        trade_index=trade_index,
        collateral_in_trade=float(MARGIN_USDC),
        is_long=is_long,
        leverage=leverage,
        tp=0,
        sl=0,
        timestamp=0,
    )
    trade.openPrice = int(price * 10**10)
    trading = client.contracts["Trading"]
    data = trading.encodeABI(
        fn_name="openTrade",
        args=[trade.model_dump(), 3, SLIPPAGE_PERCENTAGE * 10**10],
    )
    return common_tx(
        wallet=wallet,
        nonce=nonce,
        data=data,
        to=trading.address,
        gas=gas,
        fees=fees,
    )


def close_tx(
    client: TraderClient,
    *,
    wallet: str,
    trade_index: int,
    collateral_to_close: float,
    nonce: int,
    gas: int,
    fees: FeeEnvelope,
) -> dict[str, Any]:
    trading = client.contracts["Trading"]
    data = trading.encodeABI(
        fn_name="closeTradeMarket",
        args=[PAIR_INDEX, trade_index, int(collateral_to_close * 10**6)],
    )
    return common_tx(
        wallet=wallet,
        nonce=nonce,
        data=data,
        to=trading.address,
        gas=gas,
        fees=fees,
    )


async def estimate_with_buffer(
    client: TraderClient,
    tx: dict[str, Any],
    fallback: int,
) -> int:
    try:
        return max(fallback, int(await client.async_web3.eth.estimate_gas(tx) * 1.15))
    except Exception:
        return fallback


async def wait_for_sealed_state(
    client: TraderClient,
    wallet: str,
    callback_block: int,
    timeline: Timeline,
) -> dict[str, Any]:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        sealed_head = await client.async_web3.eth.block_number
        if sealed_head >= callback_block:
            state = await preflight(client, wallet)
            if not (
                state["openCount"]
                or state["pendingOpenCount"]
                or state["pendingCloseCount"]
            ):
                timeline.mark(
                    "close_callback_sealed",
                    callbackBlock=callback_block,
                    sealedHead=sealed_head,
                )
                return state
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Avantis close callback block {callback_block} did not seal flat")


async def submit_and_race(
    client: TraderClient,
    stream: CallbackStream,
    tx: dict[str, Any],
    timeline: Timeline,
    prefix: str,
    predicate: Callable[[dict[str, Any]], bool],
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    async def observe_receipt(tx_hash: HexBytes) -> tuple[Any, float, str]:
        receipt = await client.async_web3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=45,
            poll_latency=0.05,
        )
        return receipt, time.monotonic(), utc_now()

    timeline.mark(f"{prefix}_sign_started")
    signed = await client.sign_transaction(tx)
    raw = signed.rawTransaction
    deterministic_hash = Web3.keccak(raw)
    timeline.mark(
        f"{prefix}_signed",
        txHash=deterministic_hash.hex(),
        nonce=tx["nonce"],
        gas=tx["gas"],
    )
    callback_task = asyncio.create_task(stream.wait_for(predicate))
    timeline.mark(f"{prefix}_broadcast_started")
    send_task = asyncio.create_task(client.async_web3.eth.send_raw_transaction(raw))
    receipt_task = asyncio.create_task(observe_receipt(deterministic_hash))
    returned_hash = await send_task
    timeline.mark(f"{prefix}_broadcast_returned", txHash=returned_hash.hex())
    receipt_result, callback = await asyncio.gather(receipt_task, callback_task)
    receipt, receipt_monotonic, receipt_utc = receipt_result
    timeline.events[f"{prefix}_receipt"] = {
        "utc": receipt_utc,
        "elapsedMs": round((receipt_monotonic - timeline.started) * 1000, 1),
        "txHash": returned_hash.hex(),
        "blockNumber": receipt["blockNumber"],
        "status": receipt["status"],
    }
    timeline.events[f"{prefix}_callback_direct"] = {
        "utc": callback["receivedAt"],
        "elapsedMs": round(
            (callback["receivedMonotonic"] - timeline.started) * 1000,
            1,
        ),
        **{key: value for key, value in callback.items() if key != "receivedMonotonic"},
    }
    if receipt["status"] != 1:
        raise RuntimeError(f"{prefix} initiation reverted")
    return receipt, callback, normalize(receipt)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if not args.execute or not args.i_understand_live_risk:
        raise RuntimeError(
            "Optimized canary requires --execute and --i-understand-live-risk"
        )
    private_key = os.getenv(args.private_key_env, "").strip()
    if not private_key:
        raise RuntimeError(f"{args.private_key_env} is not configured")
    wallet = Account.from_key(private_key).address
    if wallet.lower() != EXPECTED_WALLET.lower():
        raise RuntimeError(f"Signer derives {wallet}, expected {EXPECTED_WALLET}")

    setup_started = time.monotonic()
    client = TraderClient(args.rpc_url)
    client.set_local_signer(private_key)
    before = await preflight(client, wallet)
    if before["openCount"] or before["pendingOpenCount"] or before["pendingCloseCount"]:
        raise RuntimeError(f"Canary wallet is not flat: {before}")
    if before["usdc"] < float(MARGIN_USDC):
        raise RuntimeError("Insufficient Base USDC")
    if before["eth"] < 0.001:
        raise RuntimeError("Insufficient Base ETH")

    setup_timeline = Timeline()
    if before["allowanceUsdc"] < float(MARGIN_USDC):
        approval = await build_approval(client, wallet, APPROVAL_USDC)
        await sign_send_wait(client, approval, setup_timeline, "approval")

    feed_id = await client.pairs_cache.get_lazer_feed_id(PAIR_INDEX)
    tape = LazerTape(client, feed_id)
    stream = CallbackStream(
        args.wss_url or derive_wss_url(args.rpc_url),
        before["callbacks"],
        wallet,
        args.callback_mode,
    )
    await asyncio.gather(tape.start(), stream.start())
    fees = await warm_fee_envelope(client)
    nonce = await client.async_web3.eth.get_transaction_count(wallet, "pending")
    warm_price = await tape.fresh(args.max_price_age_ms)
    warm_open = open_tx(
        client,
        wallet=wallet,
        trade_index=int(before["nextTradeIndex"]),
        leverage=args.leverage,
        is_long=args.side == "long",
        price=warm_price.price,
        nonce=nonce,
        gas=OPEN_GAS_FALLBACK,
        fees=fees,
    )
    open_gas = await estimate_with_buffer(client, warm_open, OPEN_GAS_FALLBACK)
    setup_ms = round((time.monotonic() - setup_started) * 1000, 1)

    try:
        timeline = Timeline()
        price = await tape.fresh(args.max_price_age_ms)
        price_age_ms = round((time.monotonic() - price.received_monotonic) * 1000, 1)
        timeline.mark(
            "open_gesture",
            price=price.price,
            priceAgeMs=price_age_ms,
            sourceTimestampMs=price.source_timestamp_ms,
        )
        prepared_open = open_tx(
            client,
            wallet=wallet,
            trade_index=int(before["nextTradeIndex"]),
            leverage=args.leverage,
            is_long=args.side == "long",
            price=price.price,
            nonce=nonce,
            gas=open_gas,
            fees=fees,
        )
        timeline.mark("open_encoded")
        open_receipt, open_callback, _ = await submit_and_race(
            client,
            stream,
            prepared_open,
            timeline,
            "open",
            lambda event: event["event"] in {"MarketExecuted", "MarketOpenCanceled"}
            and int(event["args"].get("t", {}).get("pairIndex", PAIR_INDEX))
            == PAIR_INDEX
            and bool(event["args"].get("open", True)),
        )
        open_initiated = decode_initiated(client.contracts["Trading"], open_receipt)
        if open_callback["event"] != "MarketExecuted":
            raise RuntimeError(f"Open canceled: {open_callback}")
        opened_trade = open_callback["args"]["t"]
        trade_index = int(opened_trade["index"])
        collateral_to_close = int(opened_trade["initialPosToken"]) / 10**6

        close_nonce = nonce + 1
        warm_close = close_tx(
            client,
            wallet=wallet,
            trade_index=trade_index,
            collateral_to_close=collateral_to_close,
            nonce=close_nonce,
            gas=CLOSE_GAS_FALLBACK,
            fees=fees,
        )
        close_gas = await estimate_with_buffer(client, warm_close, CLOSE_GAS_FALLBACK)
        close_ready = time.monotonic()
        remaining_hold = args.hold_seconds - (close_ready - open_callback["receivedMonotonic"])
        if remaining_hold > 0:
            await asyncio.sleep(remaining_hold)

        timeline.mark("close_gesture", tradeIndex=trade_index)
        prepared_close = close_tx(
            client,
            wallet=wallet,
            trade_index=trade_index,
            collateral_to_close=collateral_to_close,
            nonce=close_nonce,
            gas=close_gas,
            fees=fees,
        )
        timeline.mark("close_encoded")
        close_receipt, close_callback, _ = await submit_and_race(
            client,
            stream,
            prepared_close,
            timeline,
            "close",
            lambda event: event["event"] == "MarketExecuted"
            and not bool(event["args"].get("open", True))
            and int(event["args"]["t"]["pairIndex"]) == PAIR_INDEX
            and int(event["args"]["t"]["index"]) == trade_index,
        )
        close_initiated = decode_initiated(client.contracts["Trading"], close_receipt)
        callback_block = int(close_callback["blockNumber"])
        after = await wait_for_sealed_state(
            client,
            wallet,
            callback_block,
            timeline,
        )

        analysis_w3 = client.async_web3
        aggregator = analysis_w3.eth.contract(
            address=client.contracts["PriceAggregator"].address,
            abi=load_abi("PriceAggregator"),
        )
        pair_infos = analysis_w3.eth.contract(
            address=client.contracts["PairInfos"].address,
            abi=load_abi("PairInfos"),
        )
        pyth_events = analysis_w3.eth.contract(abi=load_abi("IPythEvents"))
        trading_callback = analysis_w3.eth.contract(abi=TRADING_CALLBACK_ABI)
        margin = float(MARGIN_USDC)
        open_analysis, close_analysis = await asyncio.gather(
            analyze_leg(
                analysis_w3,
                aggregator,
                pair_infos,
                pyth_events,
                trading_callback,
                callback=open_callback,
                margin_usdc=margin,
                leverage=args.leverage,
                is_long=args.side == "long",
                is_open=True,
            ),
            analyze_leg(
                analysis_w3,
                aggregator,
                pair_infos,
                pyth_events,
                trading_callback,
                callback=close_callback,
                margin_usdc=margin,
                leverage=args.leverage,
                is_long=args.side == "long",
                is_open=False,
            ),
        )

        report = {
            "createdAt": utc_now(),
            "mode": "optimized_sse_wss",
            "wallet": wallet,
            "chainId": BASE_CHAIN_ID,
            "pair": PAIR,
            "pairIndex": PAIR_INDEX,
            "side": args.side,
            "marginUsdc": margin,
            "leverage": args.leverage,
            "holdSeconds": args.hold_seconds,
            "setupMs": setup_ms,
            "openGas": open_gas,
            "closeGas": close_gas,
            "executionFeeWei": fees.execution_fee_wei,
            "callbackMode": args.callback_mode,
            "before": before,
            "openInitiated": open_initiated,
            "openCallback": {
                key: value
                for key, value in open_callback.items()
                if key != "receivedMonotonic"
            },
            "closeInitiated": close_initiated,
            "closeCallback": {
                key: value
                for key, value in close_callback.items()
                if key != "receivedMonotonic"
            },
            "after": after,
            "usdcDelta": round(after["usdc"] - before["usdc"], 6),
            "ethDelta": after["eth"] - before["eth"],
            "costAnalysis": {
                "open": open_analysis,
                "close": close_analysis,
                "totalExecutionAdjustmentUsd": open_analysis[
                    "executionAdjustmentUsdAtRequestedNotional"
                ]
                + close_analysis["executionAdjustmentUsdAtRequestedNotional"],
            },
            "timeline": timeline.events,
            "setupTimeline": setup_timeline.events,
        }
        return report
    finally:
        await asyncio.gather(tape.close(), stream.close())


def print_report(report: dict[str, Any]) -> None:
    timeline = report["timeline"]
    open_ms = timeline["open_callback_direct"]["elapsedMs"] - timeline["open_gesture"][
        "elapsedMs"
    ]
    close_ms = timeline["close_callback_direct"]["elapsedMs"] - timeline[
        "close_gesture"
    ]["elapsedMs"]
    print("Avantis ZFP Optimized Canary")
    print(
        f"- {report['pair']} {report['side']} ${report['marginUsdc']:.2f} "
        f"at {report['leverage']}x"
    )
    print(f"- setup/prewarm: {report['setupMs']:.1f} ms")
    print(f"- gesture -> open callback WSS: {open_ms:.1f} ms")
    print(f"- gesture -> close callback WSS: {close_ms:.1f} ms")
    print(f"- USDC delta: ${report['usdcDelta']:+.6f}")
    print(f"- ETH delta: {report['ethDelta']:+.9f} ETH")
    print(
        "- execution adjustment: "
        f"${report['costAnalysis']['totalExecutionAdjustmentUsd']:.6f}"
    )
    print("- final state: flat")


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / "builds" / "local-mvp" / ".env")
    args = parse_args()
    report = asyncio.run(run(args))
    print_report(report)
    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(report, indent=2) + "\n")
        print(f"- report: {args.json_report}")


if __name__ == "__main__":
    main()
