#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from time import perf_counter
from typing import Any

import requests
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from web3.exceptions import ContractLogicError


ROOT = Path(__file__).resolve().parents[1]
ARBITRUM_CHAIN_ID = 42161
BUILDER_API_URL = "https://builder.ostium.io"
SUBGRAPH_URL = f"{BUILDER_API_URL}/v1/subgraph/gn"

USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
TRADING = "0x6D0bA1f9996DBD8885827e1b2e8f6593e7702411"
TRADING_STORAGE = "0xcCd5891083A8acD2074690F65d3024E7D13d66E7"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = (1 << 256) - 1

MIN_OPEN_COLLATERAL_USD = Decimal("5")
DEFAULT_SLIPPAGE_BPS = 25

ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

TRADING_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "collateral", "type": "uint256"},
                    {"internalType": "uint192", "name": "openPrice", "type": "uint192"},
                    {"internalType": "uint192", "name": "tp", "type": "uint192"},
                    {"internalType": "uint192", "name": "sl", "type": "uint192"},
                    {"internalType": "address", "name": "trader", "type": "address"},
                    {"internalType": "uint32", "name": "leverage", "type": "uint32"},
                    {"internalType": "uint16", "name": "pairIndex", "type": "uint16"},
                    {"internalType": "uint8", "name": "index", "type": "uint8"},
                    {"internalType": "bool", "name": "buy", "type": "bool"},
                    {"internalType": "bool", "name": "isDayTrade", "type": "bool"},
                ],
                "internalType": "struct IOstiumTradingStorage.Trade",
                "name": "t",
                "type": "tuple",
            },
            {
                "components": [
                    {"internalType": "address", "name": "builder", "type": "address"},
                    {"internalType": "uint32", "name": "builderFee", "type": "uint32"},
                ],
                "internalType": "struct IOstiumTradingStorage.BuilderFee",
                "name": "bf",
                "type": "tuple",
            },
            {
                "internalType": "enum IOstiumTradingStorage.OpenOrderType",
                "name": "orderType",
                "type": "uint8",
            },
            {"internalType": "uint256", "name": "slippageP", "type": "uint256"},
        ],
        "name": "openTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint16", "name": "pairIndex", "type": "uint16"},
            {"internalType": "uint8", "name": "index", "type": "uint8"},
            {"internalType": "uint16", "name": "closePercentage", "type": "uint16"},
            {"internalType": "uint192", "name": "marketPrice", "type": "uint192"},
            {"internalType": "uint32", "name": "slippageP", "type": "uint32"},
        ],
        "name": "closeTradeMarket",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

PAIR_QUERY = """
query GetPairs {
  pairs(orderBy: id, orderDirection: asc, subgraphError: allow) {
    id
    from
    to
    maxLeverage
    overnightMaxLeverage
    takerFeeP
    group { id name maxLeverage }
  }
}
"""

OPEN_TRADES_QUERY = """
query GetTraderOpenTrades($trader: String!, $skip: Int!, $first: Int!) {
  trades(
    where: { isOpen: true, trader: $trader }
    skip: $skip
    first: $first
    orderBy: timestamp
    orderDirection: desc
  ) {
    id
    tradeID
    trader
    isOpen
    isBuy
    isDayTrade
    index
    collateral
    notional
    tradeNotional
    leverage
    openPrice
    stopLossPrice
    takeProfitPrice
    timestamp
    pair { id from to group { id name } }
  }
}
"""

ORDERS_BY_TX_QUERY = """
query GetOrders($txHashes: [String!]!, $skip: Int!, $first: Int!) {
  orders(
    where: { initiatedTx_in: $txHashes }
    skip: $skip
    first: $first
    orderBy: initiatedAt
    orderDirection: desc
  ) {
    id
    tradeID
    limitID
    trader
    orderAction
    orderType
    isBuy
    isPending
    isCancelled
    cancelReason
    collateral
    leverage
    price
    priceAfterImpact
    builder
    builderFee
    initiatedTx
    initiatedBlock
    initiatedAt
    executedTx
    executedBlock
    executedAt
    pair { id from to group { id name } }
  }
}
"""


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def normalize_private_key(value: str) -> str:
    key = value.strip()
    return key if key.startswith("0x") else f"0x{key}"


def quantize_units(value: Decimal, decimals: int) -> int:
    scale = Decimal(10) ** decimals
    return int((value * scale).to_integral_value(rounding=ROUND_DOWN))


def parse_decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"invalid {label}: {value}") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"{label} must be positive")
    return parsed


def parse_usdc(value: Decimal | str) -> int:
    return quantize_units(Decimal(str(value)), 6)


def parse_price(value: Decimal | str) -> int:
    return quantize_units(Decimal(str(value)), 18)


def parse_leverage(value: Decimal | str) -> int:
    leverage = Decimal(str(value))
    return int((leverage * Decimal(100)).to_integral_value(rounding=ROUND_DOWN))


def format_units(value: int, decimals: int, places: int = 6) -> str:
    rendered = Decimal(value) / (Decimal(10) ** decimals)
    q = Decimal(10) ** -places
    return f"{rendered.quantize(q):f}".rstrip("0").rstrip(".") or "0"


def format_contract_leverage(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    raw = Decimal(str(value))
    if raw == 0:
        return Decimal("0")
    if raw == raw.to_integral_value() and raw > 1_000:
        return raw / Decimal(100)
    return raw


def normalize_pair(value: str) -> str:
    return value.strip().upper().replace("/", "-")


def pair_key(pair: dict[str, Any]) -> str:
    return f"{pair['from']}-{pair['to']}".upper()


def get_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    last_error: requests.HTTPError | None = None
    for attempt in range(5):
        response = requests.request(method, url, timeout=20, **kwargs)
        if response.status_code not in {429, 502, 503, 504}:
            response.raise_for_status()
            break
        last_error = requests.HTTPError(f"{response.status_code} retryable response", response=response)
        time.sleep(1.5 * (attempt + 1))
    else:
        if last_error:
            raise last_error
        response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        fail(f"{url} returned non-object JSON")
    return payload


def graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = get_json(
        "POST",
        SUBGRAPH_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Content-Type": "application/json"},
    )
    if payload.get("errors"):
        fail(f"subgraph errors: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        fail("subgraph returned no data object")
    return data


def load_account_and_web3() -> tuple[Any, str, Web3]:
    load_dotenv(ROOT / ".env")
    wallet_pk = os.getenv("WALLET_PK")
    rpc_url = os.getenv("ARB_RPC_URL")
    if not wallet_pk:
        fail("WALLET_PK missing in root .env")
    if not rpc_url:
        fail("ARB_RPC_URL missing in root .env")

    account = Account.from_key(normalize_private_key(wallet_pk))
    address = Web3.to_checksum_address(account.address)
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        fail("could not connect to ARB_RPC_URL")
    chain_id = web3.eth.chain_id
    if chain_id != ARBITRUM_CHAIN_ID:
        fail(f"RPC chain_id is {chain_id}, expected {ARBITRUM_CHAIN_ID}")
    return account, address, web3


def fetch_pairs() -> list[dict[str, Any]]:
    return graphql(PAIR_QUERY)["pairs"]


def fetch_prices() -> dict[str, dict[str, Any]]:
    payload = get_json("GET", f"{BUILDER_API_URL}/v1/prices")
    prices = payload.get("prices") or []
    by_pair: dict[str, dict[str, Any]] = {}
    for price in prices:
        if not isinstance(price, dict):
            continue
        from_asset = str(price.get("from") or "").upper()
        to_asset = str(price.get("to") or "").upper()
        if from_asset and to_asset:
            by_pair[f"{from_asset}-{to_asset}"] = price
    return by_pair


def find_pair(pairs: list[dict[str, Any]], wanted: str) -> dict[str, Any]:
    normalized = normalize_pair(wanted)
    for pair in pairs:
        if pair_key(pair) == normalized:
            return pair
    sample = ", ".join(pair_key(pair) for pair in pairs[:12])
    fail(f"pair {wanted} not found. first pairs: {sample}")


def fetch_open_trades(address: str) -> list[dict[str, Any]]:
    data = graphql(
        OPEN_TRADES_QUERY,
        {"trader": address.lower(), "skip": 0, "first": 50},
    )
    return data.get("trades") or []


def fetch_orders_by_tx(tx_hash: str) -> list[dict[str, Any]]:
    data = graphql(
        ORDERS_BY_TX_QUERY,
        {"txHashes": [tx_hash.lower()], "skip": 0, "first": 10},
    )
    return data.get("orders") or []


def get_balances(web3: Web3, address: str) -> dict[str, int]:
    usdc = web3.eth.contract(address=Web3.to_checksum_address(USDC), abi=ERC20_ABI)
    return {
        "eth": web3.eth.get_balance(address),
        "usdc": usdc.functions.balanceOf(address).call(),
        "allowance": usdc.functions.allowance(address, Web3.to_checksum_address(TRADING_STORAGE)).call(),
    }


def build_open_trade_fn(
    web3: Web3,
    address: str,
    pair: dict[str, Any],
    price: Decimal,
    collateral: Decimal,
    leverage: Decimal,
    buy: bool,
    slippage_bps: int,
    is_day_trade: bool,
):
    trading = web3.eth.contract(address=Web3.to_checksum_address(TRADING), abi=TRADING_ABI)
    trade_tuple = (
        parse_usdc(collateral),
        parse_price(price),
        0,
        0,
        Web3.to_checksum_address(address),
        parse_leverage(leverage),
        int(pair["id"]),
        0,
        buy,
        is_day_trade,
    )
    builder_fee_tuple = (Web3.to_checksum_address(ZERO_ADDRESS), 0)
    order_type_market = 0
    return trading.functions.openTrade(
        trade_tuple,
        builder_fee_tuple,
        order_type_market,
        int(slippage_bps),
    )


def build_close_trade_fn(
    web3: Web3,
    trade: dict[str, Any],
    price: Decimal,
    close_percent: Decimal,
    slippage_bps: int,
):
    trading = web3.eth.contract(address=Web3.to_checksum_address(TRADING), abi=TRADING_ABI)
    close_percentage = int((close_percent * Decimal(100)).to_integral_value(rounding=ROUND_DOWN))
    return trading.functions.closeTradeMarket(
        int(trade["pair"]["id"]),
        int(trade["index"]),
        close_percentage,
        parse_price(price),
        int(slippage_bps),
    )


def estimate_or_explain(web3: Web3, address: str, fn: Any, label: str) -> None:
    tx = {"from": address, "to": fn.address, "data": fn._encode_transaction_data(), "value": 0}
    started = perf_counter()
    try:
        gas = web3.eth.estimate_gas(tx)
        print(f"- {label} gas estimate: {gas} ({perf_counter() - started:.3f}s)")
    except ContractLogicError as exc:
        print(f"- {label} simulation reverted after {perf_counter() - started:.3f}s: {exc}")
    except Exception as exc:
        print(f"- {label} gas estimate failed after {perf_counter() - started:.3f}s: {type(exc).__name__}: {exc}")


def send_transaction(web3: Web3, account: Any, address: str, fn: Any, label: str) -> str:
    started = perf_counter()
    estimate_started = perf_counter()
    gas_estimate = web3.eth.estimate_gas(
        {"from": address, "to": fn.address, "data": fn._encode_transaction_data(), "value": 0}
    )
    estimate_elapsed = perf_counter() - estimate_started
    latest_block = web3.eth.get_block("latest")
    base_fee = int(latest_block.get("baseFeePerGas") or 0)
    suggested_gas_price = int(web3.eth.gas_price)
    gas_price = max(suggested_gas_price, base_fee)
    gas_price = int(gas_price * 1.25) + 1
    tx = fn.build_transaction(
        {
            "from": address,
            "nonce": web3.eth.get_transaction_count(address),
            "chainId": ARBITRUM_CHAIN_ID,
            "gas": int(gas_estimate * 1.25),
            "gasPrice": gas_price,
            "value": 0,
        }
    )
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    broadcast_started = perf_counter()
    tx_hash = web3.eth.send_raw_transaction(raw_tx).hex()
    broadcast_elapsed = perf_counter() - broadcast_started
    print(f"- {label} sent: {tx_hash}")
    receipt_started = perf_counter()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    receipt_elapsed = perf_counter() - receipt_started
    print(f"- {label} receipt: status={receipt.status} block={receipt.blockNumber} gasUsed={receipt.gasUsed}")
    print(
        f"- {label} timing: estimate={estimate_elapsed:.3f}s "
        f"broadcast={broadcast_elapsed:.3f}s receipt={receipt_elapsed:.3f}s total={perf_counter() - started:.3f}s"
    )
    if receipt.status != 1:
        fail(f"{label} transaction failed: {tx_hash}")
    return tx_hash


def print_positions(positions: list[dict[str, Any]]) -> None:
    print(f"- open positions: {len(positions)}")
    for pos in positions[:10]:
        side = "long" if pos.get("isBuy") else "short"
        collateral = format_units(int(pos.get("collateral") or 0), 6, 4)
        leverage = format_units(int(pos.get("leverage") or 0), 2, 2)
        entry = format_units(int(pos.get("openPrice") or 0), 18, 4)
        print(
            f"  pair={pos['pair']['from']}-{pos['pair']['to']} idx={pos.get('index')} "
            f"side={side} collateral={collateral} lev={leverage} entry={entry}"
        )


def find_matching_positions(
    positions: list[dict[str, Any]],
    wanted_pair_key: str,
) -> list[dict[str, Any]]:
    return [pos for pos in positions if pair_key(pos["pair"]) == wanted_pair_key]


def wait_for_matching_position(
    address: str,
    wanted_pair_key: str,
    timeout_seconds: int,
    interval_seconds: int = 5,
) -> dict[str, Any] | None:
    started = perf_counter()
    deadline = time.time() + timeout_seconds
    while time.time() <= deadline:
        positions = fetch_open_trades(address)
        matching = find_matching_positions(positions, wanted_pair_key)
        if matching:
            print(f"- {wanted_pair_key} position indexed after {perf_counter() - started:.3f}s")
            return matching[0]
        print(f"- waiting for open position on {wanted_pair_key}...")
        time.sleep(interval_seconds)
    return None


def wait_for_position_closed(
    address: str,
    wanted_pair_key: str,
    timeout_seconds: int,
    interval_seconds: int = 5,
) -> bool:
    started = perf_counter()
    deadline = time.time() + timeout_seconds
    while time.time() <= deadline:
        positions = fetch_open_trades(address)
        matching = find_matching_positions(positions, wanted_pair_key)
        if not matching:
            print(f"- {wanted_pair_key} close indexed after {perf_counter() - started:.3f}s")
            return True
        print(f"- waiting for {wanted_pair_key} position to close...")
        time.sleep(interval_seconds)
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ostium Python trade probe")
    parser.add_argument("--pair", default="BTC-USD", help="Pair to test, e.g. BTC-USD")
    parser.add_argument("--direction", choices=["long", "short"], default="long")
    parser.add_argument("--collateral", default="5", help="USDC collateral for open test")
    parser.add_argument("--leverage", default="25", help="Leverage, e.g. 25")
    parser.add_argument("--slippage-bps", type=int, default=DEFAULT_SLIPPAGE_BPS)
    parser.add_argument("--approve", action="store_true", help="Send limited USDC approval if needed")
    parser.add_argument("--approve-max", action="store_true", help="Approve max USDC instead of exact collateral")
    parser.add_argument("--open", action="store_true", help="Send the openTrade transaction")
    parser.add_argument("--close", action="store_true", help="Close the first matching open position")
    parser.add_argument("--close-after", type=int, default=0, help="Seconds to wait after open before closing")
    parser.add_argument("--position-timeout", type=int, default=180, help="Seconds to wait for position indexing")
    parser.add_argument("--yes", action="store_true", help="Required for any transaction-sending flag")
    return parser.parse_args()


def main() -> None:
    run_started = perf_counter()
    args = parse_args()
    collateral = Decimal(str(parse_decimal(args.collateral, "collateral")))
    leverage = Decimal(str(parse_decimal(args.leverage, "leverage")))
    if collateral < MIN_OPEN_COLLATERAL_USD:
        fail(f"collateral must be at least {MIN_OPEN_COLLATERAL_USD} USDC")
    if args.slippage_bps < 0:
        fail("slippage-bps must be non-negative")
    if (args.approve or args.approve_max or args.open or args.close) and not args.yes:
        fail("transaction flags require --yes")

    account, address, web3 = load_account_and_web3()
    pairs = fetch_pairs()
    pair = find_pair(pairs, args.pair)
    prices = fetch_prices()
    price_data = prices.get(pair_key(pair))
    if not price_data:
        fail(f"live price not found for {pair_key(pair)}")
    if not price_data.get("isMarketOpen", True):
        fail(f"{pair_key(pair)} market is closed")

    price = Decimal(str(price_data["ask" if args.direction == "long" else "bid"]))
    pair_max_leverage = format_contract_leverage(pair.get("maxLeverage"))
    group_max_leverage = format_contract_leverage(pair.get("group", {}).get("maxLeverage"))
    max_leverage = pair_max_leverage if pair_max_leverage > 0 else group_max_leverage
    overnight_max = format_contract_leverage(pair.get("overnightMaxLeverage"))
    is_day_trade = overnight_max > 0 and leverage > overnight_max
    if max_leverage > 0 and leverage > max_leverage:
        fail(f"requested leverage {leverage}x exceeds pair max {max_leverage}x")

    balances = get_balances(web3, address)
    required_allowance = parse_usdc(collateral)
    notional = collateral * leverage

    print("Ostium Python Probe")
    print(f"- address: {address}")
    print(f"- pair: {pair_key(pair)} pairId={pair['id']} category={pair.get('group', {}).get('name')}")
    print(f"- live price used: {price} ({'ask' if args.direction == 'long' else 'bid'})")
    print(f"- direction: {args.direction}")
    print(f"- collateral: {collateral} USDC")
    print(f"- leverage: {leverage}x")
    print(f"- notional: {notional} USD")
    print(f"- slippage: {args.slippage_bps} bps")
    print(f"- max leverage: {max_leverage}x, overnight max: {overnight_max}x, isDayTrade={is_day_trade}")
    print(f"- ETH balance: {format_units(balances['eth'], 18, 8)}")
    print(f"- USDC balance: {format_units(balances['usdc'], 6, 6)}")
    print(f"- USDC allowance to TradingStorage: {format_units(balances['allowance'], 6, 6)}")

    positions_before = fetch_open_trades(address)
    print_positions(positions_before)

    usdc = web3.eth.contract(address=Web3.to_checksum_address(USDC), abi=ERC20_ABI)
    if balances["allowance"] < required_allowance:
        print(f"- allowance needed for this test: {format_units(required_allowance, 6, 6)}")
        approve_amount = MAX_UINT256 if args.approve_max else required_allowance
        approve_fn = usdc.functions.approve(Web3.to_checksum_address(TRADING_STORAGE), approve_amount)
        estimate_or_explain(web3, address, approve_fn, "approve")
        if args.approve or args.approve_max:
            send_transaction(web3, account, address, approve_fn, "approve")
            balances = get_balances(web3, address)
            print(f"- updated allowance: {format_units(balances['allowance'], 6, 6)}")
    else:
        print("- allowance: sufficient")

    open_fn = build_open_trade_fn(
        web3=web3,
        address=address,
        pair=pair,
        price=price,
        collateral=collateral,
        leverage=leverage,
        buy=args.direction == "long",
        slippage_bps=args.slippage_bps,
        is_day_trade=is_day_trade,
    )
    estimate_or_explain(web3, address, open_fn, "openTrade")

    open_tx_hash: str | None = None
    if args.open:
        if balances["allowance"] < required_allowance:
            fail("allowance still insufficient; run with --approve --yes first")
        if balances["usdc"] < required_allowance:
            fail("USDC balance is below requested collateral")
        open_tx_hash = send_transaction(web3, account, address, open_fn, "openTrade")
        print("- waiting 8 seconds for subgraph/order indexing")
        time.sleep(8)
        orders = fetch_orders_by_tx(open_tx_hash)
        print(f"- indexed orders for open tx: {len(orders)}")
        for order in orders:
            print(
                f"  order={order.get('id')} pending={order.get('isPending')} "
                f"cancelled={order.get('isCancelled')} executedTx={order.get('executedTx')}"
            )

    if args.close_after and open_tx_hash:
        print(f"- waiting {args.close_after}s before close probe")
        time.sleep(args.close_after)

    if args.close or (args.close_after and open_tx_hash):
        positions_after = fetch_open_trades(address)
        matching = find_matching_positions(positions_after, pair_key(pair))
        trade = matching[0] if matching else None
        if trade is None and open_tx_hash:
            trade = wait_for_matching_position(address, pair_key(pair), args.position_timeout)
        if trade is None:
            fail("no matching open position found to close")
        latest_prices = fetch_prices()
        latest = latest_prices.get(pair_key(pair))
        if not latest:
            fail(f"no latest price for close on {pair_key(pair)}")
        close_price = Decimal(str(latest["bid" if trade.get("isBuy") else "ask"]))
        close_fn = build_close_trade_fn(
            web3=web3,
            trade=trade,
            price=close_price,
            close_percent=Decimal("100"),
            slippage_bps=args.slippage_bps,
        )
        print(f"- close target: pair={pair_key(pair)} idx={trade.get('index')} price={close_price}")
        estimate_or_explain(web3, address, close_fn, "closeTradeMarket")
        if args.close:
            tx_hash = send_transaction(web3, account, address, close_fn, "closeTradeMarket")
            print("- waiting 8 seconds for close indexing")
            time.sleep(8)
            orders = fetch_orders_by_tx(tx_hash)
            print(f"- indexed orders for close tx: {len(orders)}")
            if wait_for_position_closed(address, pair_key(pair), args.position_timeout):
                print(f"- {pair_key(pair)} position closed")
            else:
                print(f"- {pair_key(pair)} still appears open after timeout; inspect manually")

    print("Probe complete.")
    print(f"Total probe time: {perf_counter() - run_started:.3f}s")


if __name__ == "__main__":
    main()
