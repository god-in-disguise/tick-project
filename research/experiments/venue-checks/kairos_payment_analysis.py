#!/usr/bin/env python3
"""Summarize recent Kairos Timeboost payment-address activity on Arbitrum."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any


DEFAULT_ADDRESS = "0x60E6a31591392f926e627ED871e670C3e81f1AB8"
BLOCKSCOUT_BASE = "https://arbitrum.blockscout.com/api/v2"
WEI_PER_ETH = Decimal(10) ** 18


def get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/json",
            "user-agent": "tick-kairos-payment-analysis/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_pages(path: str, pages: int, sleep_seconds: float) -> list[dict[str, Any]]:
    url = f"{BLOCKSCOUT_BASE}{path}"
    params: dict[str, Any] | None = None
    items: list[dict[str, Any]] = []
    for _ in range(pages):
        payload = get_json(url, params)
        items.extend(payload.get("items") or [])
        params = payload.get("next_page_params")
        if not params:
            break
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return items


def nested_hash(item: dict[str, Any], key: str) -> str:
    value = item.get(key) or {}
    if isinstance(value, dict):
        return str(value.get("hash") or "")
    return ""


def eth_string(wei: int, places: int = 9) -> str:
    value = Decimal(wei) / WEI_PER_ETH
    return f"{value:.{places}f}".rstrip("0").rstrip(".") or "0"


def usd_string(wei: int, eth_usd: Decimal | None) -> str | None:
    if eth_usd is None:
        return None
    value = Decimal(wei) / WEI_PER_ETH * eth_usd
    return f"{value:.4f}".rstrip("0").rstrip(".")


def percentile(sorted_values: list[int], pct: float) -> int | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = pct / 100 * (len(sorted_values) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = Decimal(str(rank - low))
    return int(Decimal(sorted_values[low]) * (1 - fraction) + Decimal(sorted_values[high]) * fraction)


def summarize_values(values: list[int], eth_usd: Decimal | None) -> dict[str, Any]:
    sorted_values = sorted(values)
    keys = {
        "min": sorted_values[0] if sorted_values else None,
        "p25": percentile(sorted_values, 25),
        "median": int(statistics.median(sorted_values)) if sorted_values else None,
        "p75": percentile(sorted_values, 75),
        "p90": percentile(sorted_values, 90),
        "p95": percentile(sorted_values, 95),
        "max": sorted_values[-1] if sorted_values else None,
    }
    return {
        "count": len(values),
        "totalWei": str(sum(values)),
        "totalEth": eth_string(sum(values)),
        "stats": {
            name: {
                "wei": str(value) if value is not None else None,
                "eth": eth_string(value) if value is not None else None,
                "usd": usd_string(value, eth_usd) if value is not None else None,
            }
            for name, value in keys.items()
        },
    }


def tag_names(account: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for tag in ((account.get("metadata") or {}).get("tags") or []):
        name = tag.get("name")
        if name:
            names.append(str(name))
    return names


def analyze_internal(items: list[dict[str, Any]], address: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payments: list[dict[str, Any]] = []
    by_sender: dict[str, dict[str, Any]] = {}
    for item in items:
        to_hash = nested_hash(item, "to").lower()
        value = int(item.get("value") or 0)
        if to_hash != address.lower() or value <= 0 or item.get("success") is False:
            continue
        from_account = item.get("from") or {}
        from_hash = str(from_account.get("hash") or "")
        by_sender.setdefault(
            from_hash,
            {
                "address": from_hash,
                "isContract": bool(from_account.get("is_contract")),
                "tags": tag_names(from_account),
                "count": 0,
                "totalWei": 0,
                "valuesWei": [],
            },
        )
        by_sender[from_hash]["count"] += 1
        by_sender[from_hash]["totalWei"] += value
        by_sender[from_hash]["valuesWei"].append(value)
        payments.append(
            {
                "kind": "internal",
                "timestamp": item.get("timestamp"),
                "blockNumber": item.get("block_number"),
                "txHash": item.get("transaction_hash"),
                "transactionIndex": item.get("transaction_index"),
                "internalIndex": item.get("index"),
                "from": from_hash,
                "fromIsContract": bool(from_account.get("is_contract")),
                "fromTags": tag_names(from_account),
                "type": item.get("type"),
                "gasLimit": item.get("gas_limit"),
                "valueWei": str(value),
                "valueEth": eth_string(value, 12),
            }
        )
    sender_rows = []
    for row in by_sender.values():
        values = sorted(row.pop("valuesWei"))
        row["totalWei"] = str(row["totalWei"])
        row["totalEth"] = eth_string(int(row["totalWei"]))
        row["medianEth"] = eth_string(int(statistics.median(values))) if values else "0"
        sender_rows.append(row)
    sender_rows.sort(key=lambda row: (-row["count"], -int(row["totalWei"])))
    return payments, {"topSenders": sender_rows[:15]}


def analyze_direct(items: list[dict[str, Any]], address: str) -> list[dict[str, Any]]:
    payments: list[dict[str, Any]] = []
    for item in items:
        to_hash = nested_hash(item, "to").lower()
        value = int(item.get("value") or 0)
        if to_hash != address.lower() or value <= 0 or item.get("status") not in (None, "ok"):
            continue
        payments.append(
            {
                "kind": "direct",
                "timestamp": item.get("timestamp"),
                "blockNumber": item.get("block"),
                "txHash": item.get("hash"),
                "from": nested_hash(item, "from"),
                "to": nested_hash(item, "to"),
                "method": item.get("method"),
                "rawInput": item.get("raw_input"),
                "transactionTypes": item.get("transaction_types") or [],
                "gasUsed": item.get("gas_used"),
                "valueWei": str(value),
                "valueEth": eth_string(value, 12),
            }
        )
    return payments


def fetch_parent_details(payments: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    seen: set[str] = set()
    for payment in payments:
        tx_hash = payment.get("txHash")
        if not tx_hash or tx_hash in seen:
            continue
        seen.add(tx_hash)
        tx = get_json(f"{BLOCKSCOUT_BASE}/transactions/{tx_hash}")
        raw_input = str(tx.get("raw_input") or "")
        decoded = tx.get("decoded_input") or {}
        details.append(
            {
                "txHash": tx_hash,
                "timestamp": tx.get("timestamp"),
                "from": nested_hash(tx, "from"),
                "to": nested_hash(tx, "to"),
                "toIsContract": bool((tx.get("to") or {}).get("is_contract")),
                "toTags": tag_names(tx.get("to") or {}),
                "method": tx.get("method"),
                "decodedMethodCall": decoded.get("method_call"),
                "valueWei": tx.get("value"),
                "gasUsed": tx.get("gas_used"),
                "gasLimit": tx.get("gas_limit"),
                "transactionTypes": tx.get("transaction_types") or [],
                "rawInputSelector": raw_input[:10],
                "rawInputBytes": max((len(raw_input) - 2) // 2, 0) if raw_input.startswith("0x") else 0,
                "internalPaymentEth": payment.get("valueEth"),
                "internalPaymentFrom": payment.get("from"),
                "internalGasLimit": payment.get("gasLimit"),
            }
        )
        if len(details) >= limit:
            break
    return details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default=DEFAULT_ADDRESS)
    parser.add_argument("--internal-pages", type=int, default=10)
    parser.add_argument("--direct-pages", type=int, default=4)
    parser.add_argument("--detail-samples", type=int, default=8)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--eth-usd", type=Decimal, default=None)
    args = parser.parse_args()

    address = args.address
    internal_items = fetch_pages(f"/addresses/{address}/internal-transactions", args.internal_pages, args.sleep)
    direct_items = fetch_pages(f"/addresses/{address}/transactions", args.direct_pages, args.sleep)

    internal_payments, internal_extra = analyze_internal(internal_items, address)
    direct_payments = analyze_direct(direct_items, address)
    internal_values = [int(item["valueWei"]) for item in internal_payments]
    direct_values = [int(item["valueWei"]) for item in direct_payments]

    gas_limit_counts = Counter(str(item.get("gasLimit")) for item in internal_payments)
    type_counts = Counter(str(item.get("type")) for item in internal_payments)
    direct_shape_counts = Counter(
        "raw_transfer" if item.get("rawInput") == "0x" else "contract_call"
        for item in direct_payments
    )

    report = {
        "address": address,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {
            "internalTransactions": f"{BLOCKSCOUT_BASE}/addresses/{address}/internal-transactions",
            "directTransactions": f"{BLOCKSCOUT_BASE}/addresses/{address}/transactions",
        },
        "pagesFetched": {
            "internal": args.internal_pages,
            "direct": args.direct_pages,
        },
        "rawItemsFetched": {
            "internal": len(internal_items),
            "direct": len(direct_items),
        },
        "internalPayments": summarize_values(internal_values, args.eth_usd),
        "directPayments": summarize_values(direct_values, args.eth_usd),
        "combinedPayments": summarize_values(internal_values + direct_values, args.eth_usd),
        "structure": {
            "internalTypeCounts": dict(type_counts.most_common()),
            "internalGasLimitCountsTop": dict(gas_limit_counts.most_common(12)),
            "directShapeCounts": dict(direct_shape_counts.most_common()),
            **internal_extra,
        },
        "recentInternalSamples": internal_payments[:12],
        "recentDirectSamples": direct_payments[:8],
        "parentTxSamples": fetch_parent_details(internal_payments, args.detail_samples),
    }

    output_dir = Path("venue-checks/reports/kairos-payments")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps({
        "report": str(output_path),
        "internalPayments": report["internalPayments"],
        "directPayments": report["directPayments"],
        "combinedPayments": report["combinedPayments"],
        "topSenders": report["structure"]["topSenders"][:8],
        "parentTxSamples": report["parentTxSamples"][:3],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
