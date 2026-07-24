from __future__ import annotations

import argparse
import os
import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable

from hexbytes import HexBytes
from web3 import Web3


TRADING = Web3.to_checksum_address("0x6D0bA1f9996DBD8885827e1b2e8f6593e7702411")
TRADING_CALLBACKS = Web3.to_checksum_address("0x7720fC8c8680bF4a1Af99d44c6c265a74e9742a9")

OPEN_INITIATED = Web3.keccak(text="MarketOpenOrderInitiated(uint256,address,uint16)")
CLOSE_INITIATED = Web3.keccak(text="MarketCloseOrderInitiated(uint256,uint256,address,uint16)")
CLOSE_INITIATED_V2 = Web3.keccak(text="MarketCloseOrderInitiatedV2(uint256,uint256,address,uint16,uint16)")
OPEN_EXECUTED = Web3.keccak(
    text="MarketOpenExecuted(uint256,(uint256,uint192,uint192,uint192,address,uint32,uint16,uint8,bool,bool),uint256,uint256)"
)
OPEN_CANCELED = Web3.keccak(text="MarketOpenCanceled(uint256,address,uint256,uint8)")
CLOSE_EXECUTED = Web3.keccak(text="MarketCloseExecuted(uint256,uint256,uint256,uint256,int256,uint256)")
CLOSE_EXECUTED_V2 = Web3.keccak(
    text="MarketCloseExecutedV2(uint256,uint256,uint256,uint256,int256,uint256,uint256)"
)
CLOSE_CANCELED = Web3.keccak(text="MarketCloseCanceled(uint256,uint256,address,uint256,uint256,uint8)")

CANCEL_REASONS = (
    "none",
    "paused",
    "market_closed",
    "slippage",
    "tp_reached",
    "sl_reached",
    "exposure_limits",
    "price_impact",
    "max_leverage",
    "no_trade",
    "under_liquidation",
    "not_hit",
    "gain_loss",
    "day_trade_not_allowed",
    "close_day_trade_not_allowed",
    "wrong_trade",
)


@dataclass(frozen=True)
class Observation:
    order_id: int
    initiated_block: int
    callback_block: int
    timestamp_delta: int
    canceled: bool
    pair_id: int | None
    cancel_reason: str | None

    @property
    def block_delta(self) -> int:
        return self.callback_block - self.initiated_block


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Ostium callback latency probe")
    parser.add_argument("--blocks", type=int, default=40_000)
    parser.add_argument("--chunk", type=int, default=4_000)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--open-pair-ids",
        help="Optional comma-separated pair IDs used to filter open events",
    )
    args = parser.parse_args()

    rpc_url = os.environ.get("ARB_RPC_URL")
    if not rpc_url:
        raise SystemExit("ARB_RPC_URL is required")

    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    latest = web3.eth.block_number
    start = max(0, latest - args.blocks)

    open_initiated = _logs(web3, TRADING, start, latest, [OPEN_INITIATED], args.chunk)
    close_initiated = _logs(
        web3,
        TRADING,
        start,
        latest,
        [CLOSE_INITIATED, CLOSE_INITIATED_V2],
        args.chunk,
    )
    open_callbacks = _logs(
        web3,
        TRADING_CALLBACKS,
        start,
        latest,
        [OPEN_EXECUTED, OPEN_CANCELED],
        args.chunk,
    )
    close_callbacks = _logs(
        web3,
        TRADING_CALLBACKS,
        start,
        latest,
        [CLOSE_EXECUTED, CLOSE_EXECUTED_V2, CLOSE_CANCELED],
        args.chunk,
    )

    open_pair_ids = (
        {int(value) for value in args.open_pair_ids.split(",")}
        if args.open_pair_ids
        else None
    )
    open_rows = _match(
        open_initiated,
        open_callbacks,
        {OPEN_CANCELED},
        pair_ids=open_pair_ids,
        pair_id_topic=3,
    )[-args.limit :]
    close_rows = _match(close_initiated, close_callbacks, {CLOSE_CANCELED})[-args.limit :]
    block_numbers = {
        block
        for row in [*open_rows, *close_rows]
        for block in (row["initiatedBlock"], row["callbackBlock"])
    }
    timestamps = _block_timestamps(web3, block_numbers)

    opens = _observations(open_rows, timestamps)
    closes = _observations(close_rows, timestamps)

    print(f"range={start}..{latest} blocks={latest - start:,}")
    _print_summary("open_filtered" if open_pair_ids else "open", opens)
    _print_summary("close", closes)


def _logs(
    web3: Web3,
    address: str,
    start: int,
    end: int,
    topics: list[HexBytes],
    chunk: int,
) -> list[Any]:
    result: list[Any] = []
    cursor = start
    while cursor <= end:
        upper = min(end, cursor + chunk - 1)
        result.extend(
            web3.eth.get_logs(
                {
                    "address": address,
                    "fromBlock": cursor,
                    "toBlock": upper,
                    "topics": [topics],
                }
            )
        )
        cursor = upper + 1
    return result


def _match(
    initiated: Iterable[Any],
    callbacks: Iterable[Any],
    canceled_topics: set[HexBytes],
    *,
    pair_ids: set[int] | None = None,
    pair_id_topic: int | None = None,
) -> list[dict[str, Any]]:
    by_order = {_topic_int(log, 1): log for log in callbacks}
    rows: list[dict[str, Any]] = []
    for event in initiated:
        pair_id = (
            _topic_int(event, pair_id_topic)
            if pair_id_topic is not None and len(event["topics"]) > pair_id_topic
            else None
        )
        if pair_ids is not None and pair_id not in pair_ids:
            continue
        order_id = _topic_int(event, 1)
        callback = by_order.get(order_id)
        if callback is None:
            continue
        canceled = HexBytes(callback["topics"][0]) in canceled_topics
        rows.append(
            {
                "orderId": order_id,
                "initiatedBlock": int(event["blockNumber"]),
                "callbackBlock": int(callback["blockNumber"]),
                "canceled": canceled,
                "pairId": pair_id,
                "cancelReason": _cancel_reason(callback) if canceled else None,
            }
        )
    return sorted(rows, key=lambda row: (row["initiatedBlock"], row["orderId"]))


def _block_timestamps(web3: Web3, blocks: set[int]) -> dict[int, int]:
    def fetch(block: int) -> tuple[int, int]:
        return block, int(web3.eth.get_block(block)["timestamp"])

    with ThreadPoolExecutor(max_workers=12) as executor:
        return dict(executor.map(fetch, sorted(blocks)))


def _observations(rows: list[dict[str, Any]], timestamps: dict[int, int]) -> list[Observation]:
    return [
        Observation(
            order_id=row["orderId"],
            initiated_block=row["initiatedBlock"],
            callback_block=row["callbackBlock"],
            timestamp_delta=timestamps[row["callbackBlock"]] - timestamps[row["initiatedBlock"]],
            canceled=row["canceled"],
            pair_id=row["pairId"],
            cancel_reason=row["cancelReason"],
        )
        for row in rows
    ]


def _print_summary(label: str, values: list[Observation]) -> None:
    if not values:
        print(f"{label}: no matched observations")
        return
    completed = [item for item in values if not item.canceled]
    canceled = [item for item in values if item.canceled]
    deltas = [item.block_delta for item in completed]
    seconds = [item.timestamp_delta for item in completed]
    print(
        f"{label}: matched={len(values)} executed={len(completed)} canceled={len(canceled)} "
        f"cancel_rate={len(canceled) / len(values):.1%}"
    )
    print(
        "  block_delta "
        f"min={min(deltas)} p50={_percentile(deltas, 50):.1f} "
        f"p90={_percentile(deltas, 90):.1f} p95={_percentile(deltas, 95):.1f} "
        f"p99={_percentile(deltas, 99):.1f} max={max(deltas)} mean={statistics.fmean(deltas):.2f}"
    )
    print(
        "  block_timestamp_delta_s "
        f"min={min(seconds)} p50={_percentile(seconds, 50):.1f} "
        f"p90={_percentile(seconds, 90):.1f} p95={_percentile(seconds, 95):.1f} "
        f"p99={_percentile(seconds, 99):.1f} max={max(seconds)} mean={statistics.fmean(seconds):.2f}"
    )
    if canceled:
        reasons = Counter(item.cancel_reason or "unknown" for item in canceled)
        print("  canceled_by_reason " + " ".join(f"{key}={value}" for key, value in sorted(reasons.items())))
    if any(item.pair_id is not None for item in values):
        executed_by_pair = Counter(item.pair_id for item in completed)
        canceled_by_pair = Counter(item.pair_id for item in canceled)
        pair_ids = sorted(set(executed_by_pair) | set(canceled_by_pair))
        print(
            "  by_pair_id "
            + " ".join(
                f"{pair_id}:executed={executed_by_pair[pair_id]},canceled={canceled_by_pair[pair_id]}"
                for pair_id in pair_ids
            )
        )


def _percentile(values: list[int], percentile: int) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (percentile / 100)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _topic_int(log: Any, index: int) -> int:
    return int.from_bytes(HexBytes(log["topics"][index]), "big")


def _cancel_reason(log: Any) -> str:
    data = bytes(HexBytes(log["data"]))
    code = int.from_bytes(data[-32:], "big") if data else -1
    return CANCEL_REASONS[code] if 0 <= code < len(CANCEL_REASONS) else f"reason_{code}"


if __name__ == "__main__":
    main()
