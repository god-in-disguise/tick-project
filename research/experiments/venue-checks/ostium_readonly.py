#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3


ROOT = Path(__file__).resolve().parents[1]
OSTIUM_BASE_URL = "https://builder.ostium.io"
ARBITRUM_CHAIN_ID = 42161

USDC_TOKENS = {
    "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8",
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
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]

OSTIUM_CRYPTO_CAPS = {
    "BTC-USD": "200x",
    "ETH-USD": "200x",
    "SOL-USD": "150x",
    "XRP-USD": "100x",
    "BNB-USD": "100x",
    "ADA-USD": "100x",
    "LINK-USD": "100x",
    "TRX-USD": "100x",
    "HYPE-USD": "100x",
}

WATCHLIST = list(OSTIUM_CRYPTO_CAPS.keys())


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def normalize_private_key(value: str) -> str:
    key = value.strip()
    if not key:
        fail("WALLET_PK is empty")
    return key if key.startswith("0x") else f"0x{key}"


def fmt_decimal(value: Decimal, places: int = 6) -> str:
    q = Decimal(10) ** -places
    rendered = f"{value.quantize(q):f}".rstrip("0").rstrip(".")
    return "0" if rendered == "-0" else rendered


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def unix_timestamp_to_datetime(value: Any) -> datetime:
    raw = int(Decimal(str(value)))
    if raw > 10**12:
        raw = raw // 1000
    return datetime.fromtimestamp(raw, tz=timezone.utc)


def normalize_pair(price: dict[str, Any]) -> str:
    raw_pair = str(price.get("pair") or "").upper().replace("/", "-")
    if raw_pair:
        return raw_pair

    from_asset = str(price.get("from") or "").upper()
    to_asset = str(price.get("to") or "").upper()
    if from_asset and to_asset:
        return f"{from_asset}-{to_asset}"
    return ""


def spread_bps(price: dict[str, Any]) -> Decimal | None:
    bid_raw = price.get("bid")
    ask_raw = price.get("ask")
    mid_raw = price.get("mid")
    if bid_raw is None or ask_raw is None or mid_raw is None:
        return None

    mid = as_decimal(mid_raw)
    if mid == 0:
        return None
    return ((as_decimal(ask_raw) - as_decimal(bid_raw)) / mid) * Decimal(10_000)


def get_json(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    url = f"{OSTIUM_BASE_URL}{path}"
    response = requests.request(method, url, timeout=15, **kwargs)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        fail(f"{url} returned non-object JSON")
    return payload


def check_wallet_and_rpc() -> tuple[str, Web3]:
    load_dotenv(ROOT / ".env")

    wallet_pk = os.getenv("WALLET_PK")
    rpc_url = os.getenv("ARB_RPC_URL")
    if not wallet_pk:
        fail("WALLET_PK missing in root .env")
    if not rpc_url:
        fail("ARB_RPC_URL missing in root .env")

    account = Account.from_key(normalize_private_key(wallet_pk))
    address = Web3.to_checksum_address(account.address)
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))

    if not web3.is_connected():
        fail("could not connect to ARB_RPC_URL")

    chain_id = web3.eth.chain_id
    if chain_id != ARBITRUM_CHAIN_ID:
        fail(f"RPC chain_id is {chain_id}, expected Arbitrum {ARBITRUM_CHAIN_ID}")

    print("Wallet / RPC")
    print(f"- address: {address}")
    print(f"- chain_id: {chain_id} (Arbitrum)")
    print(f"- latest_block: {web3.eth.block_number}")

    eth_balance = Decimal(web3.eth.get_balance(address)) / Decimal(10**18)
    print(f"- ETH balance: {fmt_decimal(eth_balance, 8)}")

    for symbol, token_address in USDC_TOKENS.items():
        token = web3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )
        decimals = int(token.functions.decimals().call())
        raw_balance = Decimal(token.functions.balanceOf(address).call())
        balance = raw_balance / Decimal(10**decimals)
        print(f"- {symbol} balance: {fmt_decimal(balance, 6)}")

    return address, web3


def check_prices() -> dict[str, dict[str, Any]]:
    payload = get_json("GET", "/v1/prices")
    prices = payload.get("prices") or []
    if not isinstance(prices, list):
        fail("Ostium /v1/prices response did not contain a prices array")

    by_pair = {
        normalize_pair(price): price
        for price in prices
        if isinstance(price, dict) and normalize_pair(price)
    }

    print("\nOstium Prices")
    print(f"- stale: {payload.get('stale')}")
    print(f"- generatedAt: {payload.get('generatedAt')}")
    print(f"- total_pairs: {len(prices)}")
    print("- docs crypto caps: BTC/ETH 200x, SOL 150x, XRP/BNB/ADA/LINK/TRX/HYPE 100x")
    print("- docs crypto open fee: 10 bps")

    found = 0
    for pair in WATCHLIST:
        price = by_pair.get(pair)
        if not price:
            print(f"- {pair}: not returned")
            continue
        found += 1

        spread = spread_bps(price)
        spread_text = "n/a" if spread is None else f"{fmt_decimal(spread, 2)} bps"
        print(
            f"- {pair:<8} mid={price.get('mid')} bid={price.get('bid')} "
            f"ask={price.get('ask')} spread={spread_text} "
            f"open={price.get('isMarketOpen')} cap={OSTIUM_CRYPTO_CAPS[pair]}"
        )

    if found == 0:
        print("- no watchlist crypto pairs matched; showing first 8 returned pairs")
        for pair, price in list(by_pair.items())[:8]:
            print(f"  {pair}: mid={price.get('mid')} open={price.get('isMarketOpen')}")

    return by_pair


def check_ohlc(pair: str = "BTC-USD") -> None:
    now = int(time.time())
    body = {
        "pair": pair,
        "fromTimestampSeconds": now - int(timedelta(hours=2).total_seconds()),
        "toTimestampSeconds": now,
        "resolution": "5",
    }

    print(f"\nOstium OHLC ({pair}, 5m, last 2h)")
    try:
        payload = get_json("POST", "/v1/ohlc", json=body)
    except requests.HTTPError as exc:
        print(f"- failed: HTTP {exc.response.status_code} {exc.response.text[:300]}")
        return
    except requests.RequestException as exc:
        print(f"- failed: {exc}")
        return

    candles = payload.get("data") or []
    print(f"- candles: {len(candles)}")
    if not candles:
        return

    first = candles[0]
    last = candles[-1]
    first_time = unix_timestamp_to_datetime(first.get("time", 0))
    last_time = unix_timestamp_to_datetime(last.get("time", 0))
    print(
        f"- first: {first_time.isoformat()} "
        f"O={first.get('open')} H={first.get('high')} L={first.get('low')} C={first.get('close')}"
    )
    print(
        f"- last:  {last_time.isoformat()} "
        f"O={last.get('open')} H={last.get('high')} L={last.get('low')} C={last.get('close')}"
    )


def main() -> None:
    check_wallet_and_rpc()
    check_prices()
    check_ohlc()
    print("\nRead-only check complete. No approvals, signatures, or trades were sent.")


if __name__ == "__main__":
    main()
