from __future__ import annotations

import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from time import perf_counter
from typing import Any

import requests
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

from .base import ConnectorError
from .ostium_definitions import (
    ASSET_NAMES,
    COMMODITY_SYMBOLS,
    CRYPTO_SYMBOLS,
    ERC20_ABI,
    FEED_CANDIDATES,
    INDEX_SYMBOLS,
    OPEN_TRADES_QUERY,
    ORDERS_BY_TX_QUERY,
    PAIR_QUERY,
    STOCK_SYMBOLS,
    TRADING_ABI,
)


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_ADDRESS = "0xeD1fa479504Ec60DB8a314BfF2DbbD1bB481Db78"
ARBITRUM_CHAIN_ID = 42161
BUILDER_API_URL = "https://builder.ostium.io"
SUBGRAPH_URL = f"{BUILDER_API_URL}/v1/subgraph/gn"

USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
TRADING = "0x6D0bA1f9996DBD8885827e1b2e8f6593e7702411"
TRADING_STORAGE = "0xcCd5891083A8acD2074690F65d3024E7D13d66E7"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

DEFAULT_PAIR = "BTC-USD"
DEFAULT_COLLATERAL = Decimal("20")
DEFAULT_LEVERAGE = Decimal("100")
DEFAULT_TAKER_FEE_RATE = Decimal(os.getenv("OSTIUM_TAKER_FEE_RATE", "0.001"))
DEFAULT_ORDER_RESERVE_USDC = Decimal(os.getenv("OSTIUM_ORDER_RESERVE_USDC", "0.10"))
DEFAULT_SLIPPAGE_BPS = int(os.getenv("OSTIUM_SLIPPAGE_BPS", "100"))
DEFAULT_APPROVE_USDC = Decimal("100")
DEFAULT_GAS_MULTIPLIER = Decimal(os.getenv("OSTIUM_GAS_MULTIPLIER", "5.0"))
DEFAULT_GAS_BUFFER = Decimal(os.getenv("OSTIUM_GAS_BUFFER", "1.50"))
OPEN_MAX_ATTEMPTS = int(os.getenv("OSTIUM_OPEN_ATTEMPTS", "3"))
CLOSE_MAX_ATTEMPTS = int(os.getenv("OSTIUM_CLOSE_ATTEMPTS", "3"))
ORDER_TIMEOUT_SECONDS = int(os.getenv("OSTIUM_ORDER_TIMEOUT_SECONDS", "12"))
POSITION_TIMEOUT_SECONDS = int(os.getenv("OSTIUM_POSITION_TIMEOUT_SECONDS", "24"))
MAX_UINT256 = (1 << 256) - 1

LOGGER = logging.getLogger("tick.ostium")
EXECUTION_LOCK = threading.RLock()
CONNECTION_LOCK = threading.Lock()
_CONNECTION_CACHE: dict[str, Any] = {}
_PRICE_CACHE: dict[str, Any] = {"expires": 0.0, "data": None}
_PAIR_CACHE: dict[str, Any] = {"expires": 0.0, "data": None}

_MARKET_CACHE: dict[str, Any] = {"expires": 0.0, "data": None}

class OstiumError(ConnectorError):
    pass


def _load() -> tuple[Any, str, Web3]:
    cached = _CONNECTION_CACHE.get("value")
    if cached is not None:
        return cached

    with CONNECTION_LOCK:
        cached = _CONNECTION_CACHE.get("value")
        if cached is not None:
            return cached

        value = _load_uncached()
        _CONNECTION_CACHE["value"] = value
        return value


def _load_uncached() -> tuple[Any, str, Web3]:
    load_dotenv(ROOT / ".env")
    wallet_pk = os.getenv("WALLET_PK")
    rpc_url = os.getenv("ARB_RPC_URL")
    if not wallet_pk:
        raise OstiumError("WALLET_PK missing in root .env")
    if not rpc_url:
        raise OstiumError("ARB_RPC_URL missing in root .env")

    key = wallet_pk.strip()
    account = Account.from_key(key if key.startswith("0x") else f"0x{key}")
    address = Web3.to_checksum_address(account.address)
    expected = Web3.to_checksum_address(EXPECTED_ADDRESS)
    if address != expected:
        raise OstiumError(f"WALLET_PK derives {address}, expected hardcoded {expected}")

    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        raise OstiumError("could not connect to ARB_RPC_URL")
    chain_id = web3.eth.chain_id
    if chain_id != ARBITRUM_CHAIN_ID:
        raise OstiumError(f"RPC chain_id {chain_id}, expected {ARBITRUM_CHAIN_ID}")
    return account, address, web3


def _dec(value: Any) -> Decimal:
    return Decimal(str(value))


def _units(value: Decimal, decimals: int) -> int:
    return int((value * (Decimal(10) ** decimals)).to_integral_value(rounding=ROUND_DOWN))


def _parse_usdc(value: Decimal | str) -> int:
    return _units(_dec(value), 6)


def _parse_price(value: Decimal | str) -> int:
    return _units(_dec(value), 18)


def _parse_leverage(value: Decimal | str) -> int:
    return int((_dec(value) * Decimal(100)).to_integral_value(rounding=ROUND_DOWN))


def _format_units(value: int | str, decimals: int, places: int = 6) -> str:
    rendered = Decimal(str(value)) / (Decimal(10) ** decimals)
    q = Decimal(10) ** -places
    return f"{rendered.quantize(q):f}".rstrip("0").rstrip(".") or "0"


def _format_allowance(value: int) -> float | str:
    if value > _parse_usdc(Decimal("1000000000")):
        return "max"
    return float(_format_units(value, 6, 6))


def _format_contract_leverage(value: Any) -> Decimal:
    raw = _dec(value or 0)
    if raw == 0:
        return Decimal(0)
    if raw == raw.to_integral_value() and raw > 1000:
        return raw / Decimal(100)
    return raw


def _pair_key(pair: dict[str, Any]) -> str:
    return f"{pair['from']}-{pair['to']}".upper()


def _normalize_pair(pair_name: str = DEFAULT_PAIR) -> str:
    return pair_name.upper().replace("/", "-")


def _asset_class(symbol: str) -> str:
    if symbol in CRYPTO_SYMBOLS:
        return "CRYPTO"
    if symbol in INDEX_SYMBOLS:
        return "INDEX"
    if symbol in COMMODITY_SYMBOLS:
        return "COMMODITY"
    if symbol in STOCK_SYMBOLS:
        return "STOCK"
    if len(symbol) == 3 and symbol not in {"XAU", "XAG", "WTI"}:
        return "FX"
    return "STOCK"


def _feed_label(asset_class: str, move_pct: float, span_pct: float) -> str:
    if span_pct >= 0.45:
        return "High volatility"
    if abs(move_pct) >= 0.25:
        return "Fast move"
    if asset_class == "CRYPTO":
        return "Crypto flow"
    if asset_class == "STOCK":
        return "Stock move"
    if asset_class == "COMMODITY":
        return "Commodity move"
    if asset_class == "INDEX":
        return "Macro move"
    return "FX move"


def _pct_change(current: float, previous: float) -> float:
    return ((current - previous) / previous) * 100 if previous else 0.0


def _range_pct(candles: list[dict[str, Any]], mid: float) -> float:
    if not candles or not mid:
        return 0.0
    lows = [float(candle["low"]) for candle in candles if candle.get("low") is not None]
    highs = [float(candle["high"]) for candle in candles if candle.get("high") is not None]
    if not lows or not highs:
        return 0.0
    return ((max(highs) - min(lows)) / mid) * 100


def _avg_step_pct(values: list[float]) -> float:
    steps = [abs(values[i] - values[i - 1]) / values[i - 1] * 100 for i in range(1, len(values)) if values[i - 1]]
    return float(sum(steps) / len(steps)) if steps else 0.0


def _open_cost(collateral: Decimal, leverage: Decimal, taker_fee_rate: Decimal = DEFAULT_TAKER_FEE_RATE) -> Decimal:
    return collateral * leverage * taker_fee_rate + DEFAULT_ORDER_RESERVE_USDC


def _fee_hurdle_pct(
    collateral: Decimal,
    leverage: Decimal,
    taker_fee_rate: Decimal = DEFAULT_TAKER_FEE_RATE,
) -> float:
    open_cost = _open_cost(collateral, leverage, taker_fee_rate)
    active_collateral = collateral - open_cost
    if active_collateral <= 0 or leverage <= 0:
        return 999.0
    return float((open_cost / (active_collateral * leverage)) * Decimal(100))


def _suggested_leverage(max_leverage: Decimal, active_tape_pct: float, span_pct: float, avg_step_pct: float) -> Decimal:
    if max_leverage < Decimal("25"):
        return Decimal("0")

    stress_move_pct = max(active_tape_pct, span_pct * 0.5, avg_step_pct * 6.0, 0.05)
    required_liquidation_distance_pct = stress_move_pct * 2.5 + 0.15
    for bucket in (Decimal("100"), Decimal("50"), Decimal("25")):
        approximate_liquidation_distance_pct = Decimal("90") / bucket
        if max_leverage >= bucket and approximate_liquidation_distance_pct >= Decimal(str(required_liquidation_distance_pct)):
            return bucket
    return Decimal("25")


def _taker_fee_rate(pair: dict[str, Any]) -> Decimal:
    raw = _dec(pair.get("takerFeeP") or 0)
    return raw / Decimal("100000000") if raw > 0 else DEFAULT_TAKER_FEE_RATE


def _liquidation_estimate(entry: Decimal, side: str, leverage: Decimal, max_leverage: Decimal) -> Decimal | None:
    if entry <= 0 or leverage <= 0 or max_leverage <= 0:
        return None
    threshold = Decimal(1) - (leverage / max_leverage) * Decimal("0.25")
    adverse_move = threshold / leverage
    return entry * (Decimal(1) - adverse_move if side == "long" else Decimal(1) + adverse_move)


def _http_json(method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.request(method, url, timeout=20, **kwargs)
        except requests.RequestException as exc:
            last = exc
            time.sleep(0.6 * (attempt + 1))
            continue
        if response.status_code not in {429, 502, 503, 504}:
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise OstiumError(f"{url} returned non-object JSON")
            return payload
        last = requests.HTTPError(f"{response.status_code} retryable response", response=response)
        time.sleep(1.2 * (attempt + 1))
    raise OstiumError(f"{method} {url} failed after retries: {last}") from last


def _graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _http_json(
        "POST",
        SUBGRAPH_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Content-Type": "application/json"},
    )
    if payload.get("errors"):
        raise OstiumError(f"subgraph errors: {payload['errors']}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise OstiumError("subgraph returned no data object")
    return data


def _pairs(*, fresh: bool = False) -> list[dict[str, Any]]:
    now = time.time()
    cached = _PAIR_CACHE.get("data")
    if not fresh and cached is not None and float(_PAIR_CACHE.get("expires", 0)) > now:
        return cached
    pairs = _graphql(PAIR_QUERY)["pairs"]
    _PAIR_CACHE["data"] = pairs
    _PAIR_CACHE["expires"] = now + 300
    return pairs


def _prices(*, fresh: bool = False) -> dict[str, dict[str, Any]]:
    now = time.time()
    cached = _PRICE_CACHE.get("data")
    if not fresh and cached is not None and float(_PRICE_CACHE.get("expires", 0)) > now:
        return cached
    payload = _http_json("GET", f"{BUILDER_API_URL}/v1/prices")
    out: dict[str, dict[str, Any]] = {}
    for item in payload.get("prices") or []:
        if isinstance(item, dict) and item.get("from") and item.get("to"):
            out[f"{item['from']}-{item['to']}".upper()] = item
    _PRICE_CACHE["data"] = out
    _PRICE_CACHE["expires"] = now + 0.35
    return out


def _ohlc(pair_name: str = DEFAULT_PAIR, minutes: int = 45, resolution: str = "1") -> list[dict[str, Any]]:
    now = int(time.time())
    pair_name = _normalize_pair(pair_name)
    payload = _http_json(
        "POST",
        f"{BUILDER_API_URL}/v1/ohlc",
        json={
            "pair": pair_name,
            "fromTimestampSeconds": now - minutes * 60,
            "toTimestampSeconds": now,
            "resolution": resolution,
        },
        headers={"Content-Type": "application/json"},
    )
    candles = payload.get("data") or []
    if not isinstance(candles, list):
        return []
    return [candle for candle in candles if isinstance(candle, dict) and candle.get("close") is not None]


def _find_pair(pair_name: str = DEFAULT_PAIR) -> dict[str, Any]:
    wanted = _normalize_pair(pair_name)
    for pair in _pairs():
        if _pair_key(pair) == wanted:
            return pair
    raise OstiumError(f"pair not found: {pair_name}")


def _open_trades(address: str) -> list[dict[str, Any]]:
    return _graphql(
        OPEN_TRADES_QUERY,
        {"trader": address.lower(), "skip": 0, "first": 20},
    ).get("trades") or []


def _orders_by_tx(tx_hash: str) -> list[dict[str, Any]]:
    normalized = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"
    return _graphql(
        ORDERS_BY_TX_QUERY,
        {"txHashes": [normalized.lower()], "skip": 0, "first": 10},
    ).get("orders") or []


def _balances(web3: Web3, address: str) -> dict[str, int]:
    usdc = web3.eth.contract(address=Web3.to_checksum_address(USDC), abi=ERC20_ABI)
    with ThreadPoolExecutor(max_workers=3) as executor:
        eth_future = executor.submit(web3.eth.get_balance, address)
        usdc_future = executor.submit(usdc.functions.balanceOf(address).call)
        allowance_future = executor.submit(
            usdc.functions.allowance(address, Web3.to_checksum_address(TRADING_STORAGE)).call
        )
        eth_balance = int(eth_future.result())
        usdc_balance = int(usdc_future.result())
        allowance = int(allowance_future.result())
    return {
        "eth": eth_balance,
        "usdc": usdc_balance,
        "allowance": allowance,
    }


def _position_public(position: dict[str, Any], price: dict[str, Any] | None) -> dict[str, Any]:
    entry = Decimal(_format_units(position["openPrice"], 18, 8))
    collateral = Decimal(_format_units(position["collateral"], 6, 6))
    leverage = Decimal(_format_units(position["leverage"], 2, 2))
    mark = _dec((price or {}).get("mid") or entry)
    side = "long" if position["isBuy"] else "short"
    direction = Decimal(1) if side == "long" else Decimal(-1)
    pnl = ((mark - entry) / entry) * direction * collateral * leverage if entry else Decimal(0)
    return {
        "pair": _pair_key(position["pair"]),
        "pairId": int(position["pair"]["id"]),
        "idx": int(position["index"]),
        "side": side,
        "entry": float(entry),
        "mark": float(mark),
        "collateral": float(collateral),
        "leverage": float(leverage),
        "pnl": float(pnl),
        "roePct": float((pnl / collateral) * Decimal(100)) if collateral else 0,
        "openedAt": int(position.get("timestamp") or 0),
    }


def _send(
    web3: Web3,
    account: Any,
    address: str,
    fn: Any,
    label: str,
    *,
    wait_receipt: bool = True,
) -> dict[str, Any]:
    started = perf_counter()
    estimate_started = perf_counter()
    encoded_data = fn._encode_transaction_data()
    with ThreadPoolExecutor(max_workers=4) as executor:
        gas_future = executor.submit(
            web3.eth.estimate_gas,
            {"from": address, "to": fn.address, "data": encoded_data, "value": 0},
        )
        block_future = executor.submit(web3.eth.get_block, "latest")
        price_future = executor.submit(lambda: web3.eth.gas_price)
        nonce_future = executor.submit(web3.eth.get_transaction_count, address, "pending")
        gas_estimate = gas_future.result()
        latest_block = block_future.result()
        quoted_gas_price = int(price_future.result())
        nonce = int(nonce_future.result())
    estimate_elapsed = perf_counter() - estimate_started
    base_fee = int(latest_block.get("baseFeePerGas") or 0)
    gas_price = int(Decimal(max(quoted_gas_price, base_fee)) * DEFAULT_GAS_MULTIPLIER) + 1
    tx = fn.build_transaction(
        {
            "from": address,
            "nonce": nonce,
            "chainId": ARBITRUM_CHAIN_ID,
            "gas": int(Decimal(gas_estimate) * DEFAULT_GAS_BUFFER),
            "gasPrice": gas_price,
            "value": 0,
        }
    )
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    broadcast_started = perf_counter()
    tx_hash = web3.eth.send_raw_transaction(raw_tx).hex()
    tx_hash = tx_hash if tx_hash.startswith("0x") else f"0x{tx_hash}"
    broadcast_elapsed = perf_counter() - broadcast_started
    if not wait_receipt:
        return {
            "txHash": tx_hash,
            "gasEstimate": gas_estimate,
            "gasUsed": None,
            "block": None,
            "status": "broadcast",
            "timing": {
                "estimate": round(estimate_elapsed, 3),
                "broadcast": round(broadcast_elapsed, 3),
                "receipt": None,
                "total": round(perf_counter() - started, 3),
            },
        }
    receipt_started = perf_counter()
    try:
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        receipt_elapsed = perf_counter() - receipt_started
    except Exception as exc:
        if exc.__class__.__name__ == "TimeExhausted":
            return {
                "txHash": tx_hash,
                "gasEstimate": gas_estimate,
                "gasUsed": None,
                "block": None,
                "status": "receipt_timeout",
                "timing": {
                    "estimate": round(estimate_elapsed, 3),
                    "broadcast": round(broadcast_elapsed, 3),
                    "receipt": round(perf_counter() - receipt_started, 3),
                    "total": round(perf_counter() - started, 3),
                },
            }
        raise
    if receipt.status != 1:
        raise OstiumError(f"{label} transaction failed: {tx_hash}")
    return {
        "txHash": tx_hash,
        "gasEstimate": gas_estimate,
        "gasUsed": receipt.gasUsed,
        "block": receipt.blockNumber,
        "status": "confirmed",
        "timing": {
            "estimate": round(estimate_elapsed, 3),
            "broadcast": round(broadcast_elapsed, 3),
            "receipt": round(receipt_elapsed, 3),
            "total": round(perf_counter() - started, 3),
        },
    }


def _open_fn(
    web3: Web3,
    address: str,
    pair: dict[str, Any],
    price: Decimal,
    collateral: Decimal,
    leverage: Decimal,
    side: str,
) -> Any:
    trading = web3.eth.contract(address=Web3.to_checksum_address(TRADING), abi=TRADING_ABI)
    overnight = _format_contract_leverage(pair.get("overnightMaxLeverage"))
    is_day_trade = overnight > 0 and leverage > overnight
    trade = (
        _parse_usdc(collateral),
        _parse_price(price),
        0,
        0,
        Web3.to_checksum_address(address),
        _parse_leverage(leverage),
        int(pair["id"]),
        0,
        side == "long",
        is_day_trade,
    )
    return trading.functions.openTrade(
        trade,
        (Web3.to_checksum_address(ZERO_ADDRESS), 0),
        0,
        DEFAULT_SLIPPAGE_BPS,
    )


def _close_fn(web3: Web3, position: dict[str, Any], price: Decimal) -> Any:
    trading = web3.eth.contract(address=Web3.to_checksum_address(TRADING), abi=TRADING_ABI)
    return trading.functions.closeTradeMarket(
        int(position["pair"]["id"]),
        int(position["index"]),
        10000,
        _parse_price(price),
        DEFAULT_SLIPPAGE_BPS,
    )


def _wait_for_order(tx_hash: str, timeout: int = ORDER_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    deadline = time.time() + timeout
    latest: list[dict[str, Any]] = []
    while time.time() <= deadline:
        orders = _orders_by_tx(tx_hash)
        if orders:
            latest = orders
            if any(_order_is_terminal(order) for order in orders):
                return orders
        time.sleep(1.5)
    return latest


def _wait_for_position(address: str, pair_name: str, timeout: int = POSITION_TIMEOUT_SECONDS) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() <= deadline:
        for position in _open_trades(address):
            if _pair_key(position["pair"]) == pair_name:
                return position
        time.sleep(1.5)
    return None


def _wait_until_closed(address: str, pair_name: str, timeout: int = POSITION_TIMEOUT_SECONDS) -> bool:
    deadline = time.time() + timeout
    while time.time() <= deadline:
        if not any(_pair_key(pos["pair"]) == pair_name for pos in _open_trades(address)):
            return True
        time.sleep(1.5)
    return False


def _order_is_cancelled(order: dict[str, Any]) -> bool:
    return bool(order.get("isCancelled")) or bool(order.get("cancelReason"))


def _order_is_terminal(order: dict[str, Any]) -> bool:
    return _order_is_cancelled(order) or bool(order.get("executedTx")) or not bool(order.get("isPending"))


def _cancel_reason(orders: list[dict[str, Any]]) -> str:
    for order in orders:
        if _order_is_cancelled(order):
            return str(order.get("cancelReason") or "cancelled")
    return ""


def _max_leverage(pair: dict[str, Any]) -> Decimal:
    max_pair = _format_contract_leverage(pair.get("maxLeverage"))
    max_group = _format_contract_leverage(pair.get("group", {}).get("maxLeverage"))
    return max_pair if max_pair > 0 else max_group


def _public_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": order.get("id"),
            "tradeID": order.get("tradeID"),
            "orderAction": order.get("orderAction"),
            "orderType": order.get("orderType"),
            "isPending": bool(order.get("isPending")),
            "isCancelled": bool(order.get("isCancelled")),
            "cancelReason": order.get("cancelReason"),
            "initiatedTx": order.get("initiatedTx"),
            "executedTx": order.get("executedTx"),
            "initiatedAt": order.get("initiatedAt"),
            "executedAt": order.get("executedAt"),
            "price": order.get("price"),
            "priceAfterImpact": order.get("priceAfterImpact"),
        }
        for order in orders
    ]


def _execution_status(orders: list[dict[str, Any]], position: dict[str, Any] | None, closed: bool | None = None) -> str:
    if position is not None:
        return "opened"
    if closed is True:
        return "closed"
    if any(_order_is_cancelled(order) for order in orders):
        return "cancelled"
    if orders:
        return "pending_execution"
    return "pending_index"


def status(pair_name: str = DEFAULT_PAIR) -> dict[str, Any]:
    pair_name = _normalize_pair(pair_name)
    _, address, web3 = _load()
    pair = _find_pair(pair_name)
    prices = _prices()
    pair_name = _pair_key(pair)
    price = prices[pair_name]
    balances = _balances(web3, address)
    positions = _open_trades(address)
    matching = [pos for pos in positions if _pair_key(pos["pair"]) == pair_name]
    max_pair = _format_contract_leverage(pair.get("maxLeverage"))
    max_group = _format_contract_leverage(pair.get("group", {}).get("maxLeverage"))
    return {
        "address": address,
        "pair": pair_name,
        "pairId": int(pair["id"]),
        "category": pair.get("group", {}).get("name"),
        "price": {
            "mid": float(price["mid"]),
            "bid": float(price["bid"]),
            "ask": float(price["ask"]),
            "open": bool(price.get("isMarketOpen", True)),
        },
        "maxLeverage": float(max_pair if max_pair > 0 else max_group),
        "preset": {
            "collateral": float(DEFAULT_COLLATERAL),
            "leverage": float(DEFAULT_LEVERAGE),
            "notional": float(DEFAULT_COLLATERAL * DEFAULT_LEVERAGE),
            "marginMode": "isolated",
        },
        "balances": {
            "eth": float(_format_units(balances["eth"], 18, 8)),
            "usdc": float(_format_units(balances["usdc"], 6, 6)),
            "allowance": _format_allowance(balances["allowance"]),
        },
        "position": _position_public(matching[0], price) if matching else None,
    }


def positions() -> dict[str, Any]:
    _, address, web3 = _load()
    prices = _prices()
    balances = _balances(web3, address)
    open_positions = [
        _position_public(position, prices.get(_pair_key(position["pair"])))
        for position in _open_trades(address)
    ]
    return {
        "address": address,
        "balances": {
            "eth": float(_format_units(balances["eth"], 18, 8)),
            "usdc": float(_format_units(balances["usdc"], 6, 6)),
            "allowance": _format_allowance(balances["allowance"]),
        },
        "positions": open_positions,
    }


def price_tick() -> dict[str, Any]:
    return pair_price(DEFAULT_PAIR)


def pair_price(pair_name: str = DEFAULT_PAIR) -> dict[str, Any]:
    pair_name = _normalize_pair(pair_name)
    prices = _prices()
    price = prices.get(pair_name)
    if not price:
        raise OstiumError(f"price not found: {pair_name}")
    return {
        "pair": pair_name,
        "timestamp": int(time.time()),
        "price": {
            "mid": float(price["mid"]),
            "bid": float(price["bid"]),
            "ask": float(price["ask"]),
            "open": bool(price.get("isMarketOpen", True)),
        },
    }


def _market_summary_from_candles(
    pair_name: str,
    candles: list[dict[str, Any]],
    live: dict[str, Any],
    pair_config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    closes = [float(candle["close"]) for candle in candles if candle.get("close") is not None]
    if len(closes) < 4:
        return None
    mid = float(live["mid"])
    symbol = pair_name.split("-")[0]
    baseline_3 = closes[max(0, len(closes) - 4)]
    baseline_5 = closes[max(0, len(closes) - 6)]
    baseline_15 = closes[max(0, len(closes) - 16)]
    first = closes[0]
    recent_3 = candles[-3:]
    recent_5 = candles[-5:]
    recent_15 = candles[-15:]
    recent_closes = closes[-16:]
    move_3_pct = _pct_change(mid, baseline_3)
    move_5_pct = _pct_change(mid, baseline_5)
    move_15_pct = _pct_change(mid, baseline_15)
    session_pct = _pct_change(mid, first)
    range_3_pct = _range_pct(recent_3, mid)
    range_5_pct = _range_pct(recent_5, mid)
    span_pct = _range_pct(recent_15, mid)
    full_span_pct = _range_pct(candles, mid)
    latest_range_pct = _range_pct(candles[-1:], mid)
    avg_step_pct = _avg_step_pct(recent_closes)
    active_tape_pct = max(range_3_pct, abs(move_3_pct), latest_range_pct)
    cooling = full_span_pct >= 0.35 and active_tape_pct < 0.06 and avg_step_pct < 0.025
    score = (
        abs(move_3_pct) * 9.0
        + abs(move_5_pct) * 6.5
        + abs(move_15_pct) * 3.0
        + range_3_pct * 7.0
        + range_5_pct * 4.5
        + span_pct * 2.2
        + latest_range_pct * 8.0
        + avg_step_pct * 36.0
    )
    if cooling:
        score *= 0.35
    asset_class = _asset_class(symbol)
    max_pair = _format_contract_leverage((pair_config or {}).get("maxLeverage"))
    max_group = _format_contract_leverage((pair_config or {}).get("group", {}).get("maxLeverage"))
    max_leverage = max_pair if max_pair > 0 else max_group
    if max_leverage and max_leverage < Decimal("25"):
        return None
    suggested_leverage = _suggested_leverage(max_leverage, active_tape_pct, span_pct, avg_step_pct)
    fee_hurdle_pct = _fee_hurdle_pct(
        DEFAULT_COLLATERAL,
        suggested_leverage or Decimal("25"),
        _taker_fee_rate(pair_config or {}),
    )
    activity_surplus_pct = active_tape_pct - fee_hurdle_pct
    fee_coverage = active_tape_pct / fee_hurdle_pct if fee_hurdle_pct > 0 else 0.0
    tradability = max(
        0.0,
        min(
            100.0,
            (fee_coverage - 0.70) * 42.0
            + abs(move_3_pct) * 8.0
            + range_5_pct * 12.0
            + avg_step_pct * 95.0,
        ),
    )
    if cooling:
        tradability *= 0.35
    score = score * (0.45 if activity_surplus_pct < 0 else 1.0) + tradability * 4.8
    if cooling:
        feed_label = "Cooling"
    elif activity_surplus_pct >= fee_hurdle_pct * 0.75:
        feed_label = "Hot tape"
    elif activity_surplus_pct > 0:
        feed_label = "Cost covered"
    else:
        feed_label = "Live tape"
    return {
        "pair": pair_name,
        "symbol": symbol,
        "name": ASSET_NAMES.get(symbol, symbol),
        "assetClass": asset_class,
        "feedLabel": feed_label,
        "price": mid,
        "move": move_5_pct,
        "sessionMove": session_pct,
        "spanPct": span_pct,
        "range3Pct": range_3_pct,
        "range5Pct": range_5_pct,
        "latestRangePct": latest_range_pct,
        "activeTapePct": active_tape_pct,
        "avgStepPct": avg_step_pct,
        "feeHurdlePct": fee_hurdle_pct,
        "activitySurplusPct": activity_surplus_pct,
        "feeCoverage": fee_coverage,
        "tradability": tradability,
        "score": score,
        "cooling": cooling,
        "maxLeverage": float(max_leverage) if max_leverage > 0 else 25.0,
        "suggestedLeverage": float(suggested_leverage) if suggested_leverage > 0 else 25.0,
        "open": bool(live.get("isMarketOpen", True)),
        "points": closes,
    }


def markets(limit: int = 10) -> dict[str, Any]:
    now = time.time()
    cached = _MARKET_CACHE.get("data")
    if cached is not None and float(_MARKET_CACHE.get("expires", 0)) > now:
        return cached

    prices = _prices()
    pair_configs = {_pair_key(pair): pair for pair in _pairs()}
    summaries: list[dict[str, Any]] = []
    candidates = [pair for pair in FEED_CANDIDATES if pair in pair_configs]

    def load_summary(pair_name: str) -> dict[str, Any] | None:
        live = prices.get(pair_name)
        if not live or not live.get("isMarketOpen", True):
            return None
        try:
            candles = _ohlc(pair_name, minutes=20)
        except Exception:
            return None
        return _market_summary_from_candles(pair_name, candles, live, pair_configs.get(pair_name))

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(load_summary, pair_name): pair_name for pair_name in candidates}
        for future in as_completed(futures):
            summary = future.result()
            if summary is not None:
                summaries.append(summary)

    ranked = sorted(summaries, key=lambda item: item["score"], reverse=True)
    result = {
        "timestamp": int(now),
        "universe": candidates,
        "markets": ranked[:limit],
    }
    _MARKET_CACHE["expires"] = now + 8
    _MARKET_CACHE["data"] = result
    return result


def chart(pair_name: str = DEFAULT_PAIR, minutes: int = 120) -> dict[str, Any]:
    pair_name = _normalize_pair(pair_name)
    candles = _ohlc(pair_name, minutes=max(15, min(minutes, 180)))
    closes = [float(candle["close"]) for candle in candles]
    return {
        "pair": pair_name,
        "resolution": "1",
        "candles": [
            {
                "time": int(Decimal(str(candle.get("time", 0)))),
                "open": float(candle["open"]),
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "close": float(candle["close"]),
            }
            for candle in candles
        ],
        "points": closes,
    }


def approve(amount: Decimal | None = None) -> dict[str, Any]:
    account, address, web3 = _load()
    usdc = web3.eth.contract(address=Web3.to_checksum_address(USDC), abi=ERC20_ABI)
    approval_amount = MAX_UINT256 if amount is None else _parse_usdc(amount)
    fn = usdc.functions.approve(Web3.to_checksum_address(TRADING_STORAGE), approval_amount)
    result = _send(web3, account, address, fn, "approve")
    result["allowanceUsdc"] = "max" if amount is None else float(amount)
    return result
