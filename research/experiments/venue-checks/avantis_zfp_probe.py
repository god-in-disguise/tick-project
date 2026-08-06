#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from avantis_trader_sdk import TraderClient
from dotenv import load_dotenv
from web3 import Web3


BASE_CHAIN_ID = 8453
DEFAULT_BASE_RPC_URL = "https://base-rpc.publicnode.com"
DEFAULT_WALLET = "0xeD1fa479504Ec60DB8a314BfF2DbbD1bB481Db78"
SOCKET_API = "https://socket-api-pub.avantisfi.com/socket-api/v1/data"
TARGET_SYMBOLS = ("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "HYPE/USD")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Avantis Zero-Fee Perpetuals live configuration probe."
    )
    parser.add_argument(
        "--rpc-url",
        default=os.getenv("BASE_RPC_URL", DEFAULT_BASE_RPC_URL),
        help="Base read RPC URL.",
    )
    parser.add_argument(
        "--wallet",
        default=os.getenv("AVANTIS_WALLET_ADDRESS", DEFAULT_WALLET),
        help="Wallet whose balances, allowance, and positions are inspected.",
    )
    parser.add_argument(
        "--margin",
        type=Decimal,
        default=Decimal("10"),
        help="Collateral used for spread examples.",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        help="Optional path for the complete JSON report.",
    )
    return parser.parse_args()


def fetch_socket_data() -> dict[str, Any]:
    response = requests.get(
        SOCKET_API,
        timeout=30,
        headers={"user-agent": "tick-avantis-zfp-probe/0.1"},
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success") or not isinstance(payload.get("data"), dict):
        raise RuntimeError("Avantis socket API returned an unsuccessful payload")
    return payload["data"]


async def latest_price(client: TraderClient, pair_index: int) -> tuple[float, str]:
    if await client.pairs_cache.is_lazer_supported(pair_index):
        feed_id = await client.pairs_cache.get_lazer_feed_id(pair_index)
        result = await client.feed_client.get_latest_lazer_price([feed_id])
        feed = next(
            (item for item in result.price_feeds if item.price_feed_id == feed_id),
            result.price_feeds[0],
        )
        return float(feed.converted_price), "pyth_lazer"

    result = await client.feed_client.get_price_update_data(pair_index)
    return float(result.core.price), "pyth_hermes"


async def zfp_impact_percentage(
    client: TraderClient,
    *,
    pair_index: int,
    position_size_usd: Decimal,
    price: float,
    is_long: bool,
) -> float:
    pair_infos = client.contracts["PairInfos"]
    raw = await pair_infos.functions.getTradePriceImpact(
        int(price * 10**10),
        pair_index,
        is_long,
        int(position_size_usd * 10**6),
        True,
    ).call()
    impacted_price = raw / 10**10
    if is_long:
        return (impacted_price / price - 1) * 100
    return (1 - impacted_price / price) * 100


def pair_symbol(info: dict[str, Any]) -> str:
    return f"{info['from']}/{info['to']}"


async def inspect_pair(
    client: TraderClient,
    pair_index: int,
    info: dict[str, Any],
    margin: Decimal,
) -> dict[str, Any]:
    symbol = pair_symbol(info)
    leverages = info["leverages"]
    storage = info.get("storagePairParams") or {}
    zfp_override = info.get("zfpOverride") or {}
    zfp_deactivated = bool(zfp_override.get("deactivated", False))
    zfp_allowed = bool(storage.get("isPnlTypeAllowed")) and not zfp_deactivated
    min_leverage = Decimal(str(leverages["pnlMinLeverage"]))
    max_leverage = Decimal(
        str(zfp_override.get("maxPnlLeverage", leverages["pnlMaxLeverage"]))
    )
    min_notional = Decimal(str(info.get("pairMinLevPosUSDC", info["minLevPosUSDC"])))
    price, price_source = await latest_price(client, pair_index)

    quote_leverage = min_leverage
    position_size = margin * quote_leverage
    max_position_size = margin * max_leverage
    impact_long, impact_short, max_impact_long, max_impact_short = await asyncio.gather(
        zfp_impact_percentage(
            client,
            pair_index=pair_index,
            position_size_usd=position_size,
            price=price,
            is_long=True,
        ),
        zfp_impact_percentage(
            client,
            pair_index=pair_index,
            position_size_usd=position_size,
            price=price,
            is_long=False,
        ),
        zfp_impact_percentage(
            client,
            pair_index=pair_index,
            position_size_usd=max_position_size,
            price=price,
            is_long=True,
        ),
        zfp_impact_percentage(
            client,
            pair_index=pair_index,
            position_size_usd=max_position_size,
            price=price,
            is_long=False,
        ),
    )
    zfp_spread = float(info.get("pnlSpreadP", 0))

    return {
        "pairIndex": pair_index,
        "symbol": symbol,
        "listed": bool(info.get("isPairListed")),
        "marketOpen": bool(info.get("feed", {}).get("attributes", {}).get("isOpen")),
        "zfpAllowed": zfp_allowed,
        "zfpMinLeverage": float(min_leverage),
        "zfpMaxLeverage": float(max_leverage),
        "minimumNotionalUsd": float(min_notional),
        "minimumMarginAtZfpMinLeverageUsd": float(min_notional / min_leverage),
        "price": price,
        "priceSource": price_source,
        "lazerState": (info.get("lazerFeed") or {}).get("state"),
        "zfpConstantSpreadPct": zfp_spread,
        "sampleMarginUsd": float(margin),
        "sampleLeverage": float(quote_leverage),
        "sampleNotionalUsd": float(position_size),
        "sampleLongImpactPct": impact_long,
        "sampleShortImpactPct": impact_short,
        "sampleLongEntryCostPct": zfp_spread + impact_long,
        "sampleShortEntryCostPct": zfp_spread + impact_short,
        "maxLeverageSampleNotionalUsd": float(max_position_size),
        "maxLeverageSampleLongImpactPct": max_impact_long,
        "maxLeverageSampleShortImpactPct": max_impact_short,
        "maxLeverageSampleLongEntryCostPct": zfp_spread + max_impact_long,
        "maxLeverageSampleShortEntryCostPct": zfp_spread + max_impact_short,
        "profitShareTiers": info.get("pnlFees"),
        "openInterestUsd": info.get("pairOI"),
        "liquidityUsd": info.get("liquidity"),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    wallet = Web3.to_checksum_address(args.wallet)
    client = TraderClient(args.rpc_url)
    chain_id = await client.get_chain_id()
    if chain_id != BASE_CHAIN_ID:
        raise RuntimeError(f"Expected Base chain id {BASE_CHAIN_ID}, got {chain_id}")

    socket_data = await asyncio.to_thread(fetch_socket_data)
    pair_infos = socket_data["pairInfos"]
    targets = {
        pair_symbol(info): (int(index), info)
        for index, info in pair_infos.items()
        if pair_symbol(info) in TARGET_SYMBOLS
    }

    eth_balance, usdc_balance, allowance, execution_fee = await asyncio.gather(
        client.get_balance(wallet),
        client.get_usdc_balance(wallet),
        client.get_usdc_allowance_for_trading(wallet),
        client.trade.get_trade_execution_fee(),
    )

    pairs = []
    for symbol in TARGET_SYMBOLS:
        if symbol not in targets:
            continue
        pair_index, info = targets[symbol]
        pairs.append(await inspect_pair(client, pair_index, info, args.margin))

    return {
        "chainId": chain_id,
        "wallet": wallet,
        "balances": {"eth": eth_balance, "usdc": usdc_balance},
        "tradingStorageAllowanceUsdc": allowance,
        "executionFeeEth": execution_fee / 10**18,
        "socketDataVersion": socket_data.get("dataVersion"),
        "pairCount": socket_data.get("pairCount"),
        "pairs": pairs,
    }


def print_report(report: dict[str, Any]) -> None:
    balances = report["balances"]
    print("Avantis ZFP Read-Only Probe")
    print(f"- chain id: {report['chainId']}")
    print(f"- wallet: {report['wallet']}")
    print(f"- ETH: {balances['eth']:.9f}")
    print(f"- USDC: {balances['usdc']:.6f}")
    print(f"- trading allowance: ${report['tradingStorageAllowanceUsdc']:.6f}")
    print(f"- estimated execution fee: {report['executionFeeEth']:.9f} ETH")
    print(f"- live pairs: {report['pairCount']}")

    print("\nZFP majors")
    for pair in report["pairs"]:
        print(
            f"- {pair['symbol']:<9} index={pair['pairIndex']:<3} "
            f"open={pair['marketOpen']} zfp={pair['zfpAllowed']} "
            f"lev={pair['zfpMinLeverage']:g}-{pair['zfpMaxLeverage']:g}x "
            f"min_notional=${pair['minimumNotionalUsd']:g} "
            f"min_margin=${pair['minimumMarginAtZfpMinLeverageUsd']:.2f} "
            f"spread={pair['zfpConstantSpreadPct']:.4f}% "
            f"sample_impact=L{pair['sampleLongImpactPct']:.4f}%/"
            f"S{pair['sampleShortImpactPct']:.4f}% "
            f"max_lev_impact=L{pair['maxLeverageSampleLongImpactPct']:.4f}%/"
            f"S{pair['maxLeverageSampleShortImpactPct']:.4f}%"
        )


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[3] / "builds" / "local-mvp" / ".env")
    args = parse_args()
    report = asyncio.run(run(args))
    print_report(report)

    if args.json_report:
        args.json_report.parent.mkdir(parents=True, exist_ok=True)
        args.json_report.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\n- report: {args.json_report}")


if __name__ == "__main__":
    main()
