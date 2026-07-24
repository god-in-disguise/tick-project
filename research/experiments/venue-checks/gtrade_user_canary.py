#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3


ROOT = Path(__file__).resolve().parents[1]

ARBITRUM_CHAIN_ID = 42161
ARBITRUM_BACKEND = "https://backend-arbitrum.gains.trade"
PRICING_REST = "https://backend-pricing.eu.gains.trade"
DIAMOND_ARBITRUM = "0xFF162c694eAA571f685030649814282eA457f169"
USDC_ARBITRUM = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = (1 << 256) - 1

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
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "success", "type": "bool"}],
        "type": "function",
    },
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
    },
    {
        "inputs": [
            {"name": "_index", "type": "uint32"},
            {"name": "_expectedPrice", "type": "uint64"},
        ],
        "name": "closeTradeMarket",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

DELEGATE_ABI = [
    {
        "inputs": [{"name": "delegate", "type": "address"}],
        "name": "setTradingDelegate",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "trader", "type": "address"}],
        "name": "getTradingDelegate",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "trader", "type": "address"},
            {"name": "callData", "type": "bytes"},
        ],
        "name": "delegatedTradingAction",
        "outputs": [{"name": "", "type": "bytes"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


@dataclass(frozen=True)
class PairRow:
    pair_index: int
    symbol: str
    group: str
    leverage: Decimal
    open_fee_pct: Decimal
    min_position_usd: Decimal
    min_collateral_usd: Decimal
    spread_pct: Decimal


def main() -> None:
    parser = argparse.ArgumentParser(description="User-run live gTrade open/close canary on Arbitrum.")
    parser.add_argument("--pair", default="BTCDEGEN/USD")
    parser.add_argument("--side", choices=["long", "short"], default="long")
    parser.add_argument("--margin-usd", type=Decimal, default=Decimal("10"))
    parser.add_argument("--leverage", type=Decimal, default=None, help="Defaults to pair max leverage.")
    parser.add_argument("--hold-seconds", type=float, default=5)
    parser.add_argument("--slippage-bps", type=int, default=100, help="100 bps = 1 percent.")
    parser.add_argument("--approve-usdc", type=Decimal, default=None, help="Approve this exact USDC amount first.")
    parser.add_argument("--approve-max", action="store_true", help="Approve unlimited USDC to the gTrade diamond.")
    parser.add_argument("--execute", action="store_true", help="Broadcast real approval/open/close transactions.")
    parser.add_argument("--i-understand-live-risk", action="store_true")
    parser.add_argument("--gas-multiplier", type=Decimal, default=Decimal("1.25"))
    parser.add_argument("--skip-gas-estimate", action="store_true", help="Use fixed gas limits instead of estimating on the hot path.")
    parser.add_argument("--delegated", action="store_true", help="Submit open/close through gTrade delegatedTradingAction.")
    parser.add_argument("--agent-pk-env", default="GTRADE_AGENT_PK", help="Env var containing delegate/agent wallet private key.")
    parser.add_argument("--set-delegate", action="store_true", help="Set the agent as trader delegate before the canary.")
    parser.add_argument("--delegate-only", action="store_true", help="Only check/set delegate; do not open a trade.")
    parser.add_argument("--approve-gas", type=int, default=100_000)
    parser.add_argument("--delegate-gas", type=int, default=120_000)
    parser.add_argument("--open-gas", type=int, default=2_300_000)
    parser.add_argument("--close-gas", type=int, default=2_000_000)
    parser.add_argument("--delegate-open-gas", type=int, default=2_700_000)
    parser.add_argument("--delegate-close-gas", type=int, default=2_400_000)
    parser.add_argument("--poll-interval", type=float, default=0.35)
    args = parser.parse_args()
    if args.execute and not args.i_understand_live_risk:
        raise SystemExit("Refusing live broadcast without --i-understand-live-risk")

    started = time.perf_counter()
    account, address, web3 = load_wallet()
    trading = web3.eth.contract(address=Web3.to_checksum_address(DIAMOND_ARBITRUM), abi=TRADING_ABI + DELEGATE_ABI)
    usdc = web3.eth.contract(address=Web3.to_checksum_address(USDC_ARBITRUM), abi=ERC20_ABI)
    agent = load_agent(args.agent_pk_env) if args.delegated else None
    agent_address = Web3.to_checksum_address(agent.address) if agent else None

    payload = fetch_trading_variables()
    rows = build_rows(payload)
    row = resolve_pair(rows, args.pair)
    leverage = args.leverage or row.leverage
    if leverage > row.leverage:
        raise SystemExit(f"{row.symbol} max leverage is {row.leverage}x")
    if args.margin_usd < row.min_collateral_usd:
        raise SystemExit(f"{row.symbol} needs at least ${row.min_collateral_usd:.2f} margin at {row.leverage}x")

    before = read_balances(web3, usdc, address)
    price = current_price(row.pair_index)
    preview = {
        "network": "arbitrum",
        "chainId": web3.eth.chain_id,
        "diamond": DIAMOND_ARBITRUM,
        "wallet": address,
        "pair": row.symbol,
        "pairIndex": row.pair_index,
        "side": args.side,
        "marginUsd": str(args.margin_usd),
        "leverage": str(leverage),
        "notionalUsd": str(args.margin_usd * leverage),
        "referencePrice": str(price),
        "minMarginUsd": str(row.min_collateral_usd),
        "openFeePct": str(row.open_fee_pct),
        "spreadPct": str(row.spread_pct),
        "holdSeconds": args.hold_seconds,
        "skipGasEstimate": args.skip_gas_estimate,
        "delegated": args.delegated,
        "balancesBefore": before,
    }
    if args.delegated:
        current_delegate = Web3.to_checksum_address(trading.functions.getTradingDelegate(address).call())
        preview["agent"] = agent_address
        preview["currentDelegate"] = current_delegate
        preview["agentEth"] = str(Decimal(web3.eth.get_balance(agent_address)) / Decimal(10**18)) if agent_address else None
        if current_delegate == agent_address and args.delegate_only:
            print(
                json.dumps(
                    {
                        "preview": preview,
                        "startupMs": round((time.perf_counter() - started) * 1000, 1),
                        "delegateReady": True,
                        "execute": args.execute,
                    },
                    indent=2,
                )
            )
            return
        if current_delegate != agent_address:
            if not args.set_delegate:
                preview["blocked"] = "agent is not the active gTrade delegate; rerun with --set-delegate"
                print(json.dumps(preview, indent=2))
                return
            delegate_result = send_or_estimate(
                web3,
                account,
                address,
                trading.functions.setTradingDelegate(agent_address),
                "setDelegate",
                execute=args.execute,
                gas_multiplier=args.gas_multiplier,
                skip_gas_estimate=args.skip_gas_estimate,
                fixed_gas=args.delegate_gas,
            )
            if args.delegate_only or not args.execute:
                print(
                    json.dumps(
                        {
                            "preview": preview,
                            "startupMs": round((time.perf_counter() - started) * 1000, 1),
                            "setDelegate": delegate_result,
                            "delegateReady": args.execute,
                            "openRequest": None if args.delegate_only else {
                                "blocked": "delegated open requires setTradingDelegate to be mined first",
                                "execute": False,
                            },
                        },
                        indent=2,
                    )
                )
                return

    approval_result = None
    allowance = Decimal(str(before["allowanceUsdc"]))
    if allowance < args.margin_usd:
        if not args.approve_usdc and not args.approve_max:
            preview["blocked"] = "USDC allowance is too low; rerun with --approve-usdc 100 or --approve-max"
            print(json.dumps(preview, indent=2))
            return
        if args.approve_max:
            approval_amount_units = MAX_UINT256
            approval_label: str | Decimal = "max"
        else:
            approval_label = args.approve_usdc or args.margin_usd
            approval_amount_units = usdc_units(Decimal(approval_label))
        approval_fn = usdc.functions.approve(Web3.to_checksum_address(DIAMOND_ARBITRUM), approval_amount_units)
        approval_result = send_or_estimate(
            web3,
            account,
            address,
            approval_fn,
            "approve",
            execute=args.execute,
            gas_multiplier=args.gas_multiplier,
            skip_gas_estimate=args.skip_gas_estimate,
            fixed_gas=args.approve_gas,
        )
        approval_result["allowanceUsdc"] = str(approval_label)
        if not args.execute:
            print(
                json.dumps(
                    {
                        "preview": preview,
                        "startupMs": round((time.perf_counter() - started) * 1000, 1),
                        "approval": approval_result,
                        "openRequest": {
                            "blocked": "open gas estimate requires the approval to be mined first",
                            "execute": False,
                        },
                    },
                    indent=2,
                )
            )
            return

    open_trade = build_open_trade(address, row, args.side, args.margin_usd, leverage, price)
    open_fn = trading.functions.openTrade(open_trade, args.slippage_bps, ZERO_ADDRESS)
    if args.delegated:
        open_fn = trading.functions.delegatedTradingAction(
            address,
            bytes.fromhex(open_fn._encode_transaction_data()[2:]),
        )
    open_hot_started = time.perf_counter()
    open_request = send_or_estimate(
        web3,
        agent if args.delegated and agent is not None else account,
        agent_address if args.delegated and agent_address is not None else address,
        open_fn,
        "open",
        execute=args.execute,
        gas_multiplier=args.gas_multiplier,
        skip_gas_estimate=args.skip_gas_estimate,
        fixed_gas=args.delegate_open_gas if args.delegated else args.open_gas,
    )

    result: dict[str, Any] = {
        "preview": preview,
        "startupMs": round((time.perf_counter() - started) * 1000, 1),
        "approval": approval_result,
        "openRequest": open_request,
    }

    if not args.execute:
        result["execute"] = False
        print(json.dumps(result, indent=2))
        return
    visible_started = time.perf_counter()
    position = wait_for_position(address, row.pair_index, present=True, timeout_seconds=90, poll_interval=args.poll_interval)
    result["openVisibleMs"] = round((time.perf_counter() - visible_started) * 1000, 1)
    result["swipeToOpenReceiptMs"] = open_request["elapsedMs"]
    result["swipeToPositionVisibleMs"] = round((time.perf_counter() - open_hot_started) * 1000, 1)
    result["position"] = position

    time.sleep(max(0.0, args.hold_seconds))

    close_price = current_price(row.pair_index)
    close_fn = trading.functions.closeTradeMarket(int(position["trade"]["index"]), price_units(close_price))
    if args.delegated:
        close_fn = trading.functions.delegatedTradingAction(
            address,
            bytes.fromhex(close_fn._encode_transaction_data()[2:]),
        )
    close_hot_started = time.perf_counter()
    close_request = send_or_estimate(
        web3,
        agent if args.delegated and agent is not None else account,
        agent_address if args.delegated and agent_address is not None else address,
        close_fn,
        "close",
        execute=True,
        gas_multiplier=args.gas_multiplier,
        skip_gas_estimate=args.skip_gas_estimate,
        fixed_gas=args.delegate_close_gas if args.delegated else args.close_gas,
    )
    result["closeRequest"] = close_request
    gone_started = time.perf_counter()
    wait_for_position(address, row.pair_index, present=False, timeout_seconds=90, poll_interval=args.poll_interval)
    result["closeGoneMs"] = round((time.perf_counter() - gone_started) * 1000, 1)
    result["swipeToCloseReceiptMs"] = close_request["elapsedMs"]
    result["swipeToPositionClosedMs"] = round((time.perf_counter() - close_hot_started) * 1000, 1)
    after = read_balances(web3, usdc, address)
    result["balancesAfter"] = after
    result["balanceDelta"] = {
        "eth": str(Decimal(str(after["eth"])) - Decimal(str(before["eth"]))),
        "usdc": str(Decimal(str(after["usdc"])) - Decimal(str(before["usdc"]))),
    }
    if args.delegated and agent_address:
        result["agentBalancesAfter"] = {
            "eth": str(Decimal(web3.eth.get_balance(agent_address)) / Decimal(10**18)),
        }
        result["agentBalanceDelta"] = {
            "eth": str(Decimal(result["agentBalancesAfter"]["eth"]) - Decimal(str(preview["agentEth"]))),
        }
    result["endToEndMs"] = round((time.perf_counter() - started) * 1000, 1)
    print(json.dumps(result, indent=2))


def load_wallet() -> tuple[Any, str, Web3]:
    load_dotenv(ROOT / ".env")
    wallet_pk = os.getenv("WALLET_PK")
    rpc_url = os.getenv("ARB_RPC_URL")
    if not wallet_pk:
        raise SystemExit("WALLET_PK missing in root .env")
    if not rpc_url:
        raise SystemExit("ARB_RPC_URL missing in root .env")
    key = wallet_pk.strip()
    account = Account.from_key(key if key.startswith("0x") else f"0x{key}")
    address = Web3.to_checksum_address(account.address)
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        raise SystemExit("could not connect to ARB_RPC_URL")
    if web3.eth.chain_id != ARBITRUM_CHAIN_ID:
        raise SystemExit(f"RPC chain_id {web3.eth.chain_id}, expected {ARBITRUM_CHAIN_ID}")
    return account, address, web3


def load_agent(env_name: str) -> Any:
    load_dotenv(ROOT / ".env")
    value = os.getenv(env_name)
    if not value:
        raise SystemExit(f"{env_name} missing in root .env")
    key = value.strip()
    return Account.from_key(key if key.startswith("0x") else f"0x{key}")


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


def get_json(url: str) -> Any:
    response = requests.get(url, timeout=25, headers={"user-agent": "tick-gtrade-canary/0.1"})
    response.raise_for_status()
    return response.json()


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
        leverage = Decimal(max_leverage_raw) / Decimal(1000)
        fee = fees[fee_index]
        min_position = Decimal(str(fee["minPositionSizeUsd"])) / Decimal(100)
        rows.append(
            PairRow(
                pair_index=pair_index,
                symbol=f"{pair['from']}/{pair['to']}",
                group=groups[group_index]["name"],
                leverage=leverage,
                open_fee_pct=pct_from_p(fee["totalPositionSizeFeeP"]),
                min_position_usd=min_position,
                min_collateral_usd=min_position / leverage,
                spread_pct=pct_from_p(pair["spreadP"]),
            )
        )
    return rows


def resolve_pair(rows: list[PairRow], raw_pair: str) -> PairRow:
    normalized = raw_pair.upper().replace("-", "/")
    for row in rows:
        if row.symbol.upper() == normalized or str(row.pair_index) == normalized:
            return row
    raise SystemExit(f"Unknown pair: {raw_pair}")


def current_price(pair_index: int) -> Decimal:
    closes = fetch_charts().get("closes") or []
    if pair_index >= len(closes) or closes[pair_index] is None:
        raise RuntimeError(f"price not found for pair index {pair_index}")
    return Decimal(str(closes[pair_index]))


def build_open_trade(
    address: str,
    row: PairRow,
    side: str,
    margin_usd: Decimal,
    leverage: Decimal,
    price: Decimal,
) -> tuple[Any, ...]:
    return (
        address,
        0,
        row.pair_index,
        int((leverage * Decimal(1000)).to_integral_value(rounding=ROUND_DOWN)),
        side == "long",
        True,
        3,
        0,
        usdc_units(margin_usd),
        price_units(price),
        0,
        0,
        False,
        0,
        0,
    )


def send_or_estimate(
    web3: Web3,
    account: Any,
    address: str,
    fn: Any,
    label: str,
    *,
    execute: bool,
    gas_multiplier: Decimal,
    skip_gas_estimate: bool,
    fixed_gas: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    gas = fixed_gas if skip_gas_estimate else int(fn.estimate_gas({"from": address}))
    gas_ms = 0.0 if skip_gas_estimate else elapsed_ms(started)
    if not execute:
        return {
            "label": label,
            "estimateGas": gas,
            "gasEstimateMs": gas_ms,
            "gasEstimateSkipped": skip_gas_estimate,
            "execute": False,
        }

    sign_started = time.perf_counter()
    tx = fn.build_transaction(
        {
            "from": address,
            "chainId": ARBITRUM_CHAIN_ID,
            "nonce": web3.eth.get_transaction_count(address, "pending"),
            "gas": int(Decimal(gas) * gas_multiplier),
            **fee_params(web3),
        }
    )
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    sign_ms = elapsed_ms(sign_started)
    send_started = time.perf_counter()
    try:
        tx_hash = web3.eth.send_raw_transaction(raw_tx)
    except Exception as exc:
        if not is_base_fee_error(exc):
            raise
        tx = fn.build_transaction(
            {
                "from": address,
                "chainId": ARBITRUM_CHAIN_ID,
                "nonce": web3.eth.get_transaction_count(address, "pending"),
                "gas": int(Decimal(gas) * gas_multiplier),
                **fee_params(web3, aggressive=True),
            }
        )
        signed = account.sign_transaction(tx)
        raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = web3.eth.send_raw_transaction(raw_tx)
    send_ms = elapsed_ms(send_started)
    receipt_started = time.perf_counter()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=90, poll_latency=0.2)
    receipt_ms = elapsed_ms(receipt_started)
    return {
        "label": label,
        "txHash": tx_hash.hex(),
        "estimateGas": gas,
        "gasEstimateMs": gas_ms,
        "gasEstimateSkipped": skip_gas_estimate,
        "signMs": sign_ms,
        "sendMs": send_ms,
        "receiptMs": receipt_ms,
        "elapsedMs": elapsed_ms(started),
        "status": int(receipt.status),
        "blockNumber": int(receipt.blockNumber),
        "gasUsed": int(receipt.gasUsed),
        "fees": {key: tx[key] for key in ("maxFeePerGas", "maxPriorityFeePerGas") if key in tx},
        "execute": True,
    }


def fee_params(web3: Web3, *, aggressive: bool = False) -> dict[str, int]:
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    priority = int(web3.eth.max_priority_fee) if hasattr(web3.eth, "max_priority_fee") else 0
    minimum_priority = 50_000_000 if aggressive else 10_000_000
    priority = max(priority, minimum_priority)
    multiplier = Decimal("3.0") if aggressive else Decimal("2.0")
    max_fee = int(Decimal(base_fee) * multiplier) + priority
    return {
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority,
    }


def is_base_fee_error(exc: Exception) -> bool:
    return bool(re.search(r"max fee per gas less than block base fee|baseFee", str(exc), re.IGNORECASE))


def wait_for_position(
    address: str,
    pair_index: int,
    *,
    present: bool,
    timeout_seconds: float,
    poll_interval: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    last: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        positions = open_trades(address, pair_index)
        if bool(positions) is present:
            return positions[0] if positions else None
        last = positions
        time.sleep(poll_interval)
    state = "appear" if present else "disappear"
    raise TimeoutError(f"position did not {state}; last={last[:1]}")


def open_trades(address: str, pair_index: int | None = None) -> list[dict[str, Any]]:
    payload = get_json(f"{ARBITRUM_BACKEND}/open-trades/{Web3.to_checksum_address(address)}")
    if not isinstance(payload, list):
        raise RuntimeError("open-trades returned non-list JSON")
    if pair_index is None:
        return payload
    return [item for item in payload if int(item.get("trade", {}).get("pairIndex", -1)) == pair_index]


def read_balances(web3: Web3, usdc: Any, address: str) -> dict[str, Any]:
    diamond = Web3.to_checksum_address(DIAMOND_ARBITRUM)
    return {
        "eth": str(Decimal(web3.eth.get_balance(address)) / Decimal(10**18)),
        "usdc": str(Decimal(usdc.functions.balanceOf(address).call()) / Decimal(10**6)),
        "allowanceUsdc": str(Decimal(usdc.functions.allowance(address, diamond).call()) / Decimal(10**6)),
    }


def usdc_units(value: Decimal) -> int:
    return int((value * Decimal(10**6)).to_integral_value(rounding=ROUND_DOWN))


def price_units(value: Decimal) -> int:
    return int((value * Decimal(10**10)).to_integral_value(rounding=ROUND_UP))


def pct_from_p(value: Any) -> Decimal:
    return (Decimal(str(value)) / Decimal(10**12)) * Decimal(100)


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


if __name__ == "__main__":
    main()
