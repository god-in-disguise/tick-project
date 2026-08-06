#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import avantis_trader_sdk
from avantis_trader_sdk.config import CONTRACT_ADDRESSES
from web3 import AsyncWeb3
from web3.logs import DISCARD


DEFAULT_BASE_RPC_URL = "https://base-rpc.publicnode.com"
TRADING_CALLBACK_ABI = [
    {
        "type": "function",
        "name": "executeMarketOrders",
        "stateMutability": "payable",
        "inputs": [
            {"name": "orderId", "type": "uint256[]"},
            {"name": "priceUpdateData", "type": "bytes[]"},
            {"name": "_priceSourcing", "type": "uint8"},
            {"name": "spreadP", "type": "int256"},
        ],
        "outputs": [],
    }
]
PYTH_LAZER_EVM_MAGIC = 706_910_618
PYTH_LAZER_PAYLOAD_MAGIC = 2_479_346_549
PRICE_SOURCE_NAMES = {0: "pyth_core", 1: "pyth_lazer"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Decode Avantis oracle, execution, and fee events from canary reports."
    )
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument(
        "--rpc-url",
        default=os.getenv("BASE_RPC_URL", DEFAULT_BASE_RPC_URL),
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_abi(contract_name: str) -> list[dict[str, Any]]:
    path = (
        Path(avantis_trader_sdk.__file__).resolve().parent
        / "abis"
        / f"{contract_name}.sol"
        / f"{contract_name}.json"
    )
    return json.loads(path.read_text())["abi"]


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


def adjustment_pct(
    *,
    oracle_price: float,
    execution_price: float,
    is_long: bool,
    is_open: bool,
) -> float:
    if is_long == is_open:
        return (execution_price / oracle_price - 1) * 100
    return (oracle_price / execution_price - 1) * 100


def parse_pyth_lazer_update(update: bytes) -> dict[str, Any]:
    if len(update) < 71:
        raise ValueError("Pyth Lazer signed update is shorter than 71 bytes")

    envelope_magic = int.from_bytes(update[0:4], "big")
    if envelope_magic != PYTH_LAZER_EVM_MAGIC:
        raise ValueError(f"Unexpected Pyth Lazer EVM magic: {envelope_magic}")

    payload_length = int.from_bytes(update[69:71], "big")
    payload = update[71 : 71 + payload_length]
    if len(payload) != payload_length or len(payload) < 14:
        raise ValueError("Pyth Lazer payload is incomplete")

    payload_magic = int.from_bytes(payload[0:4], "big")
    if payload_magic != PYTH_LAZER_PAYLOAD_MAGIC:
        raise ValueError(f"Unexpected Pyth Lazer payload magic: {payload_magic}")

    timestamp_us = int.from_bytes(payload[4:12], "big")
    return {
        "signedUpdateBytes": len(update),
        "envelopeMagic": envelope_magic,
        "recoveryId": int(update[68]) + 27,
        "payloadBytes": payload_length,
        "payloadMagic": payload_magic,
        "oracleTimestampUs": timestamp_us,
        "oracleTimestampUtc": datetime.fromtimestamp(
            timestamp_us / 1_000_000,
            tz=timezone.utc,
        ).isoformat(),
        "channel": int(payload[12]),
        "feedCount": int(payload[13]),
    }


def latency_breakdown(
    report: dict[str, Any],
    leg: str,
    analysis: dict[str, Any],
) -> dict[str, float | int]:
    gesture = datetime.fromisoformat(report["timeline"][f"{leg}_gesture"]["utc"])
    receipt = datetime.fromisoformat(report["timeline"][f"{leg}_receipt"]["utc"])
    callback = datetime.fromisoformat(analysis["callbackPendingLogAt"])
    oracle_timestamp_us = max(
        update["oracleTimestampUs"] for update in analysis["signedPriceUpdates"]
    )
    oracle = datetime.fromtimestamp(oracle_timestamp_us / 1_000_000, tz=timezone.utc)
    initiation_block = int(report["timeline"][f"{leg}_receipt"]["blockNumber"])

    return {
        "gestureToInitiationPreconfirmMs": (receipt - gesture).total_seconds() * 1000,
        "initiationPreconfirmToOracleSampleMs": (
            oracle - receipt
        ).total_seconds()
        * 1000,
        "oracleSampleToEconomicExecutionObservedMs": (
            callback - oracle
        ).total_seconds()
        * 1000,
        "gestureToEconomicExecutionObservedMs": (
            callback - gesture
        ).total_seconds()
        * 1000,
        "initiationToCallbackBlockDelta": int(analysis["blockNumber"])
        - initiation_block,
    }


async def analyze_leg(
    w3: AsyncWeb3,
    aggregator: Any,
    pair_infos: Any,
    pyth_events: Any,
    trading_callback: Any,
    *,
    callback: dict[str, Any],
    margin_usdc: float,
    leverage: int,
    is_long: bool,
    is_open: bool,
) -> dict[str, Any]:
    tx_hash = callback["transactionHash"]
    receipt = await w3.eth.get_transaction_receipt(tx_hash)
    transaction = await w3.eth.get_transaction(tx_hash)
    block = await w3.eth.get_block(receipt["blockNumber"])
    order_id = int(callback["args"]["orderId"])

    price_events = aggregator.events.PriceReceived().process_receipt(
        receipt,
        errors=DISCARD,
    )
    price_event = next(
        event for event in price_events if int(event["args"]["orderId"]) == order_id
    )
    fee_events = pair_infos.events.FeesCharged().process_receipt(
        receipt,
        errors=DISCARD,
    )
    pyth_updates = pyth_events.events.PriceFeedUpdate().process_receipt(
        receipt,
        errors=DISCARD,
    )

    oracle_price = int(price_event["args"]["price"]) / 10**10
    execution_price = int(callback["args"]["price"]) / 10**10
    adjustment = adjustment_pct(
        oracle_price=oracle_price,
        execution_price=execution_price,
        is_long=is_long,
        is_open=is_open,
    )
    notional_usd = margin_usdc * leverage
    publish_times = [int(event["args"]["publishTime"]) for event in pyth_updates]
    newest_publish_time = max(publish_times) if publish_times else None
    position_timestamp = int(callback["args"]["t"]["timestamp"])
    callback_function, callback_input = trading_callback.decode_function_input(
        transaction["input"]
    )
    price_source = int(callback_input["_priceSourcing"])
    signed_updates = (
        [
            parse_pyth_lazer_update(bytes(update))
            for update in callback_input["priceUpdateData"]
        ]
        if price_source == 1
        else []
    )
    callback_received_at = datetime.fromisoformat(callback["receivedAt"])
    callback_received_us = int(callback_received_at.timestamp() * 1_000_000)
    for update in signed_updates:
        update["oracleToPendingLogMs"] = (
            callback_received_us - update["oracleTimestampUs"]
        ) / 1000
        update["oracleToCallbackBlockTimestampMs"] = (
            int(block["timestamp"]) * 1_000_000 - update["oracleTimestampUs"]
        ) / 1000

    return {
        "transactionHash": tx_hash,
        "blockNumber": receipt["blockNumber"],
        "blockTimestamp": block["timestamp"],
        "orderId": order_id,
        "callbackSender": transaction["from"],
        "callbackTarget": transaction["to"],
        "callbackSelector": transaction["input"][:4].hex(),
        "callbackMethod": callback_function.fn_name,
        "callbackOrderIds": [int(value) for value in callback_input["orderId"]],
        "priceSource": PRICE_SOURCE_NAMES.get(price_source, f"unknown_{price_source}"),
        "spreadP": int(callback_input["spreadP"]),
        "signedPriceUpdates": signed_updates,
        "callbackPendingLogAt": callback["receivedAt"],
        "pythPriceUpdates": [normalize(event["args"]) for event in pyth_updates],
        "newestOraclePublishTime": newest_publish_time,
        "oraclePublishToCallbackBlockMs": (
            (int(block["timestamp"]) - newest_publish_time) * 1000
            if newest_publish_time is not None
            else None
        ),
        "positionTimestamp": position_timestamp,
        "positionTimestampToCallbackBlockMs": (
            int(block["timestamp"]) - position_timestamp
        )
        * 1000,
        "oraclePrice": oracle_price,
        "executionPrice": execution_price,
        "executionAdjustmentPct": adjustment,
        "executionAdjustmentUsdAtRequestedNotional": adjustment
        / 100
        * notional_usd,
        "feesCharged": [normalize(event["args"]) for event in fee_events],
    }


async def analyze_report(w3: AsyncWeb3, path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text())
    aggregator = w3.eth.contract(
        address=CONTRACT_ADDRESSES["PriceAggregator"],
        abi=load_abi("PriceAggregator"),
    )
    pair_infos = w3.eth.contract(
        address=CONTRACT_ADDRESSES["PairInfos"],
        abi=load_abi("PairInfos"),
    )
    pyth_events = w3.eth.contract(abi=load_abi("IPythEvents"))
    trading_callback = w3.eth.contract(abi=TRADING_CALLBACK_ABI)
    is_long = report["side"] == "long"
    margin = float(report["marginUsdc"])
    leverage = int(report["leverage"])
    open_leg, close_leg = await asyncio.gather(
        analyze_leg(
            w3,
            aggregator,
            pair_infos,
            pyth_events,
            trading_callback,
            callback=report["openCallback"],
            margin_usdc=margin,
            leverage=leverage,
            is_long=is_long,
            is_open=True,
        ),
        analyze_leg(
            w3,
            aggregator,
            pair_infos,
            pyth_events,
            trading_callback,
            callback=report["closeCallback"],
            margin_usdc=margin,
            leverage=leverage,
            is_long=is_long,
            is_open=False,
        ),
    )
    open_leg["latency"] = latency_breakdown(report, "open", open_leg)
    close_leg["latency"] = latency_breakdown(report, "close", close_leg)
    return {
        "report": str(path),
        "pair": report["pair"],
        "side": report["side"],
        "marginUsdc": margin,
        "leverage": leverage,
        "usdcDelta": report["usdcDelta"],
        "ethDelta": report["ethDelta"],
        "open": open_leg,
        "close": close_leg,
        "totalExecutionAdjustmentUsd": open_leg[
            "executionAdjustmentUsdAtRequestedNotional"
        ]
        + close_leg["executionAdjustmentUsdAtRequestedNotional"],
    }


async def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    w3 = AsyncWeb3(
        AsyncWeb3.AsyncHTTPProvider(args.rpc_url, request_kwargs={"timeout": 30})
    )
    return await asyncio.gather(*(analyze_report(w3, path) for path in args.reports))


def print_table(rows: list[dict[str, Any]]) -> None:
    print("Avantis ZFP Receipt Analysis")
    for row in rows:
        print(
            f"- {row['leverage']:>3}x {row['side']:<5} "
            f"USDC={row['usdcDelta']:+.6f} "
            f"open_adj=${row['open']['executionAdjustmentUsdAtRequestedNotional']:.6f} "
            f"close_adj=${row['close']['executionAdjustmentUsdAtRequestedNotional']:.6f} "
            f"total_adj=${row['totalExecutionAdjustmentUsd']:.6f}"
        )
        print(f"  open fees:  {row['open']['feesCharged']}")
        print(f"  close fees: {row['close']['feesCharged']}")
        for leg in ("open", "close"):
            latency = row[leg]["latency"]
            print(
                f"  {leg:<5} preconfirm={latency['gestureToInitiationPreconfirmMs']:.1f}ms "
                f"keeper+price={latency['initiationPreconfirmToOracleSampleMs']:.1f}ms "
                f"oracle+callback={latency['oracleSampleToEconomicExecutionObservedMs']:.1f}ms "
                f"visible={latency['gestureToEconomicExecutionObservedMs']:.1f}ms"
            )


def main() -> None:
    args = parse_args()
    rows = asyncio.run(run(args))
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print_table(rows)


if __name__ == "__main__":
    main()
