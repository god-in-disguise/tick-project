#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_UP
from pathlib import Path
from typing import Any

import requests
import websockets
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3


ROOT = Path(__file__).resolve().parents[1]

ARBITRUM_CHAIN_ID = 42161
ARBITRUM_BACKEND = "https://backend-arbitrum.gains.trade"
PRICING_REST = "https://backend-pricing.eu.gains.trade"
PRICING_WS = "wss://backend-pricing.eu.gains.trade"
DIAMOND_ARBITRUM = "0xFF162c694eAA571f685030649814282eA457f169"

WATCH_PAIR_INDEXES = [0, 1, 33, 300, 313, 314, 90, 91, 21, 22]

COLLATERALS = {
    "DAI": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "GNS": "0x18c11FD286C5EC11c3b683Caa813B77f5163A122",
}

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "remaining", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]

DELEGATE_ABI = [
    {
        "inputs": [{"name": "trader", "type": "address"}],
        "name": "getTradingDelegate",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

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

TRADING_ABI = [
    {
        "inputs": [
            {
                "components": [{"name": name, "type": typ} for name, typ in TRADE_FIELDS],
                "name": "trade",
                "type": "tuple",
            },
            {"name": "maxSlippageP", "type": "uint16"},
            {"name": "referrer", "type": "address"},
        ],
        "name": "openTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]


@dataclass(frozen=True)
class PairRow:
    pair_index: int
    symbol: str
    group: str
    leverage: Decimal
    fee_index: int
    open_fee_pct: Decimal
    min_position_usd: Decimal
    min_collateral_usd: Decimal
    spread_pct: Decimal


def d(value: Any) -> Decimal:
    return Decimal(str(value))


def pct_from_p(value: Any) -> Decimal:
    # Gains percentage params are 1e12-scaled: 600000000 = 0.06%.
    return (d(value) / Decimal(10**12)) * Decimal(100)


def leverage_from_backend(value: Any) -> Decimal:
    return d(value) / Decimal(1000)


def money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01'), rounding=ROUND_UP):,.2f}"


def compact_decimal(value: Decimal, places: int = 4) -> str:
    q = Decimal(10) ** -places
    return f"{value.quantize(q):f}".rstrip("0").rstrip(".")


def get_json(url: str) -> Any:
    response = requests.get(
        url,
        timeout=30,
        headers={"user-agent": "tick-gtrade-probe/0.1"},
    )
    response.raise_for_status()
    return response.json()


def fetch_trading_variables() -> dict[str, Any]:
    payload = get_json(f"{ARBITRUM_BACKEND}/trading-variables")
    if not isinstance(payload, dict):
        raise RuntimeError("trading-variables returned non-object JSON")
    return payload


def fetch_charts() -> dict[str, Any]:
    payload = get_json(f"{PRICING_REST}/charts")
    if not isinstance(payload, dict):
        raise RuntimeError("charts returned non-object JSON")
    return payload


def build_rows(payload: dict[str, Any]) -> list[PairRow]:
    pairs = payload["pairs"]
    groups = payload["groups"]
    fees = payload["fees"]
    max_leverages = payload["pairInfos"]["maxLeverages"]

    rows: list[PairRow] = []
    for pair_index, pair in enumerate(pairs):
        group_index = int(pair["groupIndex"])
        fee_index = int(pair["feeIndex"])
        override = int(max_leverages[pair_index]) if pair_index < len(max_leverages) else 0
        max_leverage_raw = override if override else int(groups[group_index]["maxLeverage"])
        leverage = leverage_from_backend(max_leverage_raw)
        fee = fees[fee_index]
        min_position = d(fee["minPositionSizeUsd"]) / Decimal(100)
        rows.append(
            PairRow(
                pair_index=pair_index,
                symbol=f"{pair['from']}/{pair['to']}",
                group=groups[group_index]["name"],
                leverage=leverage,
                fee_index=fee_index,
                open_fee_pct=pct_from_p(fee["totalPositionSizeFeeP"]),
                min_position_usd=min_position,
                min_collateral_usd=min_position / leverage,
                spread_pct=pct_from_p(pair["spreadP"]),
            )
        )
    return rows


def print_overview(payload: dict[str, Any], rows: list[PairRow]) -> None:
    print("Gains / gTrade Arbitrum Public Probe")
    print(f"- refreshed: {payload.get('lastRefreshed')}")
    print(f"- tradingState: {payload.get('tradingState')} (0 means open)")
    print(f"- pairs: {len(payload.get('pairs', []))}")
    print(f"- marketOrdersTimeoutBlocks: {payload.get('marketOrdersTimeoutBlocks')}")
    print(f"- blockConfirmations: {payload.get('blockConfirmations')}")
    print(f"- forex open: {payload.get('isForexOpen')}")
    print(f"- commodities open: {payload.get('isCommoditiesOpen')}")
    print(f"- stocks open: {payload.get('isStocksOpen')}")

    print("\nTop Leverage Pairs")
    for row in sorted(rows, key=lambda item: item.leverage, reverse=True)[:18]:
        print(
            f"- {row.symbol:<14} index={row.pair_index:<3} "
            f"{compact_decimal(row.leverage, 1):>6}x "
            f"group={row.group:<14} open_fee={compact_decimal(row.open_fee_pct, 4)}% "
            f"min_notional={money(row.min_position_usd)} "
            f"min_margin={money(row.min_collateral_usd)} "
            f"spread={compact_decimal(row.spread_pct, 4)}%"
        )


def print_watchlist(rows: list[PairRow], charts: dict[str, Any]) -> None:
    by_index = {row.pair_index: row for row in rows}
    closes = charts.get("closes") or []
    print("\nTICK Watchlist")
    for pair_index in WATCH_PAIR_INDEXES:
        row = by_index.get(pair_index)
        if not row:
            continue
        close = closes[pair_index] if pair_index < len(closes) else None
        print(
            f"- {row.symbol:<14} index={row.pair_index:<3} "
            f"price={close} lev={compact_decimal(row.leverage, 1)}x "
            f"min_margin={money(row.min_collateral_usd)} fee={compact_decimal(row.open_fee_pct, 4)}%"
        )


async def sample_price_stream(rows: list[PairRow], seconds: float) -> None:
    by_index = {row.pair_index: row for row in rows}
    watch = set(WATCH_PAIR_INDEXES)
    stats: dict[int, dict[str, Any]] = {}
    message_count = 0
    update_count = 0
    started = time.perf_counter()

    async with websockets.connect(PRICING_WS, ping_interval=None, open_timeout=10) as ws:
        while time.perf_counter() - started < seconds:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            message_count += 1
            payload = json.loads(raw)
            if not isinstance(payload, list) or len(payload) < 2:
                continue

            for i in range(0, len(payload) - 1, 2):
                pair_index = int(payload[i])
                price = d(payload[i + 1])
                update_count += 1
                if pair_index not in watch:
                    continue
                item = stats.setdefault(
                    pair_index,
                    {"first": price, "last": price, "min": price, "max": price, "updates": 0},
                )
                item["last"] = price
                item["min"] = min(item["min"], price)
                item["max"] = max(item["max"], price)
                item["updates"] += 1

    elapsed = Decimal(str(time.perf_counter() - started))
    print(f"\nPrice Stream Sample ({compact_decimal(elapsed, 2)}s)")
    print(f"- messages: {message_count}")
    print(f"- pair updates: {update_count}")
    print(f"- messages/sec: {compact_decimal(Decimal(message_count) / elapsed, 2)}")
    print(f"- updates/sec: {compact_decimal(Decimal(update_count) / elapsed, 2)}")

    for pair_index in WATCH_PAIR_INDEXES:
        row = by_index.get(pair_index)
        item = stats.get(pair_index)
        if not row or not item:
            continue
        first = item["first"]
        last = item["last"]
        move_bps = Decimal(0) if first == 0 else ((last - first) / first) * Decimal(10_000)
        range_bps = Decimal(0) if first == 0 else ((item["max"] - item["min"]) / first) * Decimal(10_000)
        print(
            f"- {row.symbol:<14} updates={item['updates']:<3} "
            f"first={first} last={last} move={compact_decimal(move_bps, 2)}bps "
            f"range={compact_decimal(range_bps, 2)}bps"
        )


def normalize_private_key(value: str) -> str:
    key = value.strip()
    return key if key.startswith("0x") else f"0x{key}"


def wallet_address_from_env() -> str | None:
    wallet_address = os.getenv("WALLET_ADDRESS")
    if wallet_address:
        return Web3.to_checksum_address(wallet_address)

    wallet_pk = os.getenv("WALLET_PK")
    if not wallet_pk:
        return None
    return Web3.to_checksum_address(Account.from_key(normalize_private_key(wallet_pk)).address)


def print_wallet_state() -> None:
    load_dotenv(ROOT / ".env")
    rpc_url = os.getenv("ARB_RPC_URL")
    address = wallet_address_from_env()
    if not rpc_url or not address:
        print("\nWallet State")
        print("- skipped: set ARB_RPC_URL and WALLET_ADDRESS or WALLET_PK in .env")
        return

    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        print("\nWallet State")
        print("- error: could not connect to ARB_RPC_URL")
        return

    print("\nWallet State")
    print(f"- address: {address}")
    print(f"- chain_id: {web3.eth.chain_id}")
    print(f"- latest_block: {web3.eth.block_number}")
    eth_balance = d(web3.eth.get_balance(address)) / Decimal(10**18)
    print(f"- ETH balance: {compact_decimal(eth_balance, 8)}")

    diamond = Web3.to_checksum_address(DIAMOND_ARBITRUM)
    for symbol, raw_token in COLLATERALS.items():
        token = web3.eth.contract(address=Web3.to_checksum_address(raw_token), abi=ERC20_ABI)
        decimals = int(token.functions.decimals().call())
        scale = Decimal(10) ** decimals
        balance = d(token.functions.balanceOf(address).call()) / scale
        allowance = d(token.functions.allowance(address, diamond).call()) / scale
        print(
            f"- {symbol:<4} balance={compact_decimal(balance, 6):>14} "
            f"allowance_to_diamond={compact_decimal(allowance, 6):>14}"
        )

    try:
        contract = web3.eth.contract(address=diamond, abi=DELEGATE_ABI)
        delegate = contract.functions.getTradingDelegate(address).call()
        print(f"- trading_delegate: {delegate}")
    except Exception as exc:  # noqa: BLE001 - view may move across facets.
        print(f"- trading_delegate: unreadable ({exc})")


def resolve_pair(rows: list[PairRow], raw_pair: str) -> PairRow:
    normalized = raw_pair.upper().replace("-", "/")
    for row in rows:
        if row.symbol.upper() == normalized or str(row.pair_index) == normalized:
            return row
    raise SystemExit(f"Unknown pair: {raw_pair}")


def estimate_dry_open(rows: list[PairRow], charts: dict[str, Any], raw_pair: str, margin_usd: Decimal, long: bool) -> None:
    load_dotenv(ROOT / ".env")
    rpc_url = os.getenv("ARB_RPC_URL")
    address = wallet_address_from_env()
    if not rpc_url or not address:
        print("\nDry Open Estimate")
        print("- skipped: set ARB_RPC_URL and WALLET_ADDRESS or WALLET_PK in .env")
        return

    row = resolve_pair(rows, raw_pair)
    closes = charts.get("closes") or []
    price = d(closes[row.pair_index])
    collateral_amount = int((margin_usd * Decimal(10**6)).to_integral_value(rounding=ROUND_UP))
    open_price = int((price * Decimal(10**10)).to_integral_value(rounding=ROUND_UP))
    leverage = int((row.leverage * Decimal(1000)).to_integral_value())

    trade = (
        address,
        0,
        row.pair_index,
        leverage,
        long,
        True,
        3,
        0,
        collateral_amount,
        open_price,
        0,
        0,
        False,
        0,
        0,
    )

    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    contract = web3.eth.contract(address=Web3.to_checksum_address(DIAMOND_ARBITRUM), abi=TRADING_ABI)

    print("\nDry Open Estimate")
    print(f"- pair: {row.symbol} index={row.pair_index}")
    print(f"- side: {'long' if long else 'short'}")
    print(f"- margin: {money(margin_usd)}")
    print(f"- leverage: {compact_decimal(row.leverage, 1)}x")
    print(f"- notional: {money(margin_usd * row.leverage)}")
    print(f"- price: {price}")
    print(f"- min_margin_for_pair: {money(row.min_collateral_usd)}")

    try:
        gas = contract.functions.openTrade(
            trade,
            1000,
            "0x0000000000000000000000000000000000000000",
        ).estimate_gas({"from": address})
        print(f"- estimate_gas: {gas}")
        print("- dry_open: passed")
    except Exception as exc:  # noqa: BLE001 - probe reports contract reverts.
        print(f"- dry_open: reverted ({str(exc)[:500]})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Gains/gTrade venue probe.")
    parser.add_argument("--stream-seconds", type=float, default=3.0)
    parser.add_argument("--wallet", action="store_true", help="Read wallet balances and allowances from ARB_RPC_URL.")
    parser.add_argument("--dry-open", default="", help="Dry estimate an open for a pair, e.g. BTCDEGEN/USD or 300.")
    parser.add_argument("--dry-open-margin", type=Decimal, default=Decimal("10"))
    parser.add_argument("--dry-open-side", choices=["long", "short"], default="long")
    args = parser.parse_args()

    payload = fetch_trading_variables()
    charts = fetch_charts()
    rows = build_rows(payload)

    print_overview(payload, rows)
    print_watchlist(rows, charts)

    if args.stream_seconds > 0:
        asyncio.run(sample_price_stream(rows, args.stream_seconds))

    if args.wallet:
        print_wallet_state()

    if args.dry_open:
        estimate_dry_open(
            rows,
            charts,
            args.dry_open,
            args.dry_open_margin,
            long=args.dry_open_side == "long",
        )


if __name__ == "__main__":
    main()
