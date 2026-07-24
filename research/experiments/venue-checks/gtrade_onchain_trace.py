#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from web3 import Web3


ROOT = Path(__file__).resolve().parents[1]
ARBITRUM_CHAIN_ID = 42161
DIAMOND_ARBITRUM = "0xFF162c694eAA571f685030649814282eA457f169"

TRADE_FIELDS = [
    ("user", "address"),
    ("index", "uint32"),
    ("pairIndex", "uint16"),
    ("leverage", "uint24"),
    ("long", "bool"),
    ("isOpen", "bool"),
    ("collateralIndex", "uint8"),
    ("tradeType", "uint8"),
    ("collateralAmount", "uint120"),
    ("openPrice", "uint64"),
    ("tp", "uint64"),
    ("sl", "uint64"),
    ("isCounterTrade", "bool"),
    ("positionSizeToken", "uint160"),
    ("__placeholder", "uint24"),
]

MARKET_EXECUTED_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {
                "components": [
                    {"name": "user", "type": "address"},
                    {"name": "index", "type": "uint32"},
                ],
                "indexed": False,
                "name": "orderId",
                "type": "tuple",
            },
            {"indexed": False, "name": "user", "type": "address"},
            {"indexed": False, "name": "index", "type": "uint32"},
            {
                "components": [{"name": name, "type": typ} for name, typ in TRADE_FIELDS],
                "indexed": False,
                "name": "t",
                "type": "tuple",
            },
            {"indexed": False, "name": "open", "type": "bool"},
            {"indexed": False, "name": "oraclePrice", "type": "uint256"},
            {"indexed": False, "name": "marketPrice", "type": "uint256"},
            {"indexed": False, "name": "liqPrice", "type": "uint256"},
            {"indexed": False, "name": "priceImpactP", "type": "uint256"},
            {"indexed": False, "name": "percentProfit", "type": "int256"},
            {"indexed": False, "name": "amountSentToTrader", "type": "uint256"},
            {"indexed": False, "name": "collateralPriceUsd", "type": "uint256"},
        ],
        "name": "MarketExecuted",
        "type": "event",
    }
]

MARKET_EXECUTED_TOPIC = "0x" + Web3.keccak(
    text=(
        "MarketExecuted("
        "(address,uint32),"
        "address,"
        "uint32,"
        "(address,uint32,uint16,uint24,bool,bool,uint8,uint8,uint120,uint64,uint64,uint64,bool,uint160,uint24),"
        "bool,"
        "uint256,"
        "uint256,"
        "uint256,"
        "uint256,"
        "int256,"
        "uint256,"
        "uint256"
        ")"
    )
).hex().removeprefix("0x")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace real gTrade initiation txs to MarketExecuted callback txs on Arbitrum.")
    parser.add_argument("tx_hashes", nargs="+", help="Initiation transaction hashes.")
    parser.add_argument("--scan-blocks", type=int, default=20)
    parser.add_argument("--owner", default=None)
    parser.add_argument("--pair-index", type=int, default=None)
    parser.add_argument("--trade-index", type=int, default=None)
    parser.add_argument("--open", dest="is_open", action="store_true")
    parser.add_argument("--close", dest="is_close", action="store_true")
    parser.add_argument("--dump-diamond-logs", action="store_true", help="Also print raw diamond log topics in the scan range.")
    parser.add_argument("--matching-topic-logs-only", action="store_true", help="When dumping raw logs, keep only logs whose topics match owner/pair/trade filters.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    rpc_url = os.getenv("ARB_RPC_URL")
    if not rpc_url:
        raise SystemExit("ARB_RPC_URL missing in root .env")
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        raise SystemExit("could not connect to ARB_RPC_URL")
    if web3.eth.chain_id != ARBITRUM_CHAIN_ID:
        raise SystemExit(f"RPC chain_id {web3.eth.chain_id}, expected {ARBITRUM_CHAIN_ID}")

    contract = web3.eth.contract(address=Web3.to_checksum_address(DIAMOND_ARBITRUM), abi=MARKET_EXECUTED_ABI)
    target_open = True if args.is_open else False if args.is_close else None
    output = []
    for tx_hash in args.tx_hashes:
        receipt = web3.eth.get_transaction_receipt(tx_hash)
        tx_block = web3.eth.get_block(receipt.blockNumber)
        callbacks = []
        diamond_logs = []
        latest = min(int(web3.eth.block_number), int(receipt.blockNumber) + max(1, args.scan_blocks))
        raw_logs = web3.eth.get_logs(
            {
                "address": Web3.to_checksum_address(DIAMOND_ARBITRUM),
                "fromBlock": int(receipt.blockNumber),
                "toBlock": latest,
            }
        )
        if args.dump_diamond_logs:
            block_timestamps: dict[int, int] = {int(receipt.blockNumber): int(tx_block.timestamp)}
            for log in raw_logs:
                topic_values = {_hex(topic).lower() for topic in log["topics"]}
                owner_topic = topic_address(args.owner) if args.owner else None
                pair_topic = topic_u256(args.pair_index) if args.pair_index is not None else None
                index_topic = topic_u256(args.trade_index) if args.trade_index is not None else None
                matches = {
                    "owner": bool(owner_topic and owner_topic in topic_values),
                    "pairIndex": bool(pair_topic and pair_topic in topic_values),
                    "tradeIndex": bool(index_topic and index_topic in topic_values),
                }
                if args.matching_topic_logs_only and not any(matches.values()):
                    continue
                block_number = int(log["blockNumber"])
                if block_number not in block_timestamps:
                    block_timestamps[block_number] = int(web3.eth.get_block(block_number).timestamp)
                diamond_logs.append(
                    {
                        "blockNumber": block_number,
                        "blockTimestamp": block_timestamps[block_number],
                        "secondsAfterInitiationBlock": block_timestamps[block_number] - int(tx_block.timestamp),
                        "blocksAfterInitiation": block_number - int(receipt.blockNumber),
                        "transactionHash": _hex(log["transactionHash"]),
                        "logIndex": int(log["logIndex"]),
                        "topics": [_hex(topic) for topic in log["topics"]],
                        "dataBytes": len(bytes(log["data"])),
                        "topicMatches": matches,
                    }
                )
        logs = web3.eth.get_logs(
            {
                "address": Web3.to_checksum_address(DIAMOND_ARBITRUM),
                "fromBlock": int(receipt.blockNumber),
                "toBlock": latest,
                "topics": [MARKET_EXECUTED_TOPIC],
            }
        )
        for log in logs:
            decoded = decode_market_executed(contract, log)
            if not decoded:
                continue
            trade = decoded.get("trade") or {}
            if args.owner and str(decoded.get("user", "")).lower() != args.owner.lower():
                continue
            if args.pair_index is not None and int(trade.get("pairIndex", -1)) != args.pair_index:
                continue
            if args.trade_index is not None and int(trade.get("index", -1)) != args.trade_index:
                continue
            if target_open is not None and bool(decoded.get("open")) != target_open:
                continue
            block = web3.eth.get_block(decoded["blockNumber"])
            callbacks.append(
                {
                    **decoded,
                    "secondsAfterInitiationBlock": int(block.timestamp) - int(tx_block.timestamp),
                    "blocksAfterInitiation": int(decoded["blockNumber"]) - int(receipt.blockNumber),
                    "blockTimestamp": int(block.timestamp),
                }
            )
        output.append(
            {
                "initiationTxHash": tx_hash,
                "initiationStatus": int(receipt.status),
                "initiationBlock": int(receipt.blockNumber),
                "initiationBlockTimestamp": int(tx_block.timestamp),
                "scanToBlock": latest,
                "callbacks": callbacks,
                "diamondLogs": diamond_logs if args.dump_diamond_logs else None,
            }
        )
    print(json.dumps(output, indent=2))


def decode_market_executed(contract: Any, log: Any) -> dict[str, Any] | None:
    try:
        decoded = contract.events.MarketExecuted().process_log(log)
    except Exception:
        return None
    args = decoded["args"]
    return {
        "callbackTxHash": _hex(decoded["transactionHash"]),
        "blockNumber": int(decoded["blockNumber"]),
        "logIndex": int(decoded["logIndex"]),
        "user": Web3.to_checksum_address(args["user"]),
        "index": int(args["index"]),
        "open": bool(args["open"]),
        "trade": trade_to_dict(args["t"]),
        "oraclePrice": str(args["oraclePrice"]),
        "marketPrice": str(args["marketPrice"]),
        "liqPrice": str(args["liqPrice"]),
        "priceImpactP": str(args["priceImpactP"]),
        "percentProfit": str(args["percentProfit"]),
        "amountSentToTrader": str(args["amountSentToTrader"]),
        "collateralPriceUsd": str(args["collateralPriceUsd"]),
    }


def trade_to_dict(value: Any) -> dict[str, Any]:
    return {name: plain(value.get(name)) for name, _ in TRADE_FIELDS if value.get(name) is not None}


def plain(value: Any) -> Any:
    if isinstance(value, bytes):
        return _hex(value)
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if hasattr(value, "items"):
        return {str(key): plain(item) for key, item in value.items()}
    return value


def _hex(value: Any) -> str:
    raw = value.hex() if hasattr(value, "hex") else str(value)
    return raw if raw.startswith("0x") else f"0x{raw}"


def topic_address(value: str) -> str:
    return "0x" + value.lower().removeprefix("0x").rjust(64, "0")


def topic_u256(value: int) -> str:
    return "0x" + hex(int(value))[2:].rjust(64, "0")


if __name__ == "__main__":
    main()
