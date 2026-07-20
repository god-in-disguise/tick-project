#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3


ROOT = Path(__file__).resolve().parents[1]
ARBITRUM_CHAIN_ID = 42161


def main() -> None:
    parser = argparse.ArgumentParser(description="Fund gTrade delegated agent wallet with Arbitrum ETH.")
    parser.add_argument("--amount-eth", type=Decimal, default=Decimal("0.001"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-live-transfer", action="store_true")
    args = parser.parse_args()
    if args.execute and not args.i_understand_live_transfer:
        raise SystemExit("Refusing live transfer without --i-understand-live-transfer")

    account, trader, agent, web3 = load()
    before = balances(web3, trader, agent)
    tx = build_transfer(web3, trader, agent, args.amount_eth)
    result: dict[str, Any] = {
        "network": "arbitrum",
        "chainId": web3.eth.chain_id,
        "trader": trader,
        "agent": agent,
        "amountEth": str(args.amount_eth),
        "balancesBefore": before,
        "txPreview": {
            "to": tx["to"],
            "valueWei": tx["value"],
            "gas": tx["gas"],
            "maxFeePerGas": tx["maxFeePerGas"],
            "maxPriorityFeePerGas": tx["maxPriorityFeePerGas"],
        },
        "execute": args.execute,
    }

    if not args.execute:
        print(json.dumps(result, indent=2))
        return

    started = time.perf_counter()
    signed = account.sign_transaction(tx)
    raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    tx_hash = web3.eth.send_raw_transaction(raw_tx)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=90, poll_latency=0.2)
    result["txHash"] = tx_hash.hex()
    result["receiptMs"] = round((time.perf_counter() - started) * 1000, 1)
    result["status"] = int(receipt.status)
    result["blockNumber"] = int(receipt.blockNumber)
    result["gasUsed"] = int(receipt.gasUsed)
    result["balancesAfter"] = balances(web3, trader, agent)
    print(json.dumps(result, indent=2))


def load() -> tuple[Any, str, str, Web3]:
    load_dotenv(ROOT / ".env")
    wallet_pk = os.getenv("WALLET_PK")
    agent_pk = os.getenv("GTRADE_AGENT_PK")
    rpc_url = os.getenv("ARB_RPC_URL")
    if not wallet_pk:
        raise SystemExit("WALLET_PK missing in root .env")
    if not agent_pk:
        raise SystemExit("GTRADE_AGENT_PK missing in root .env")
    if not rpc_url:
        raise SystemExit("ARB_RPC_URL missing in root .env")

    account = Account.from_key(normalize_pk(wallet_pk))
    agent = Account.from_key(normalize_pk(agent_pk)).address
    trader = Web3.to_checksum_address(account.address)
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        raise SystemExit("could not connect to ARB_RPC_URL")
    if web3.eth.chain_id != ARBITRUM_CHAIN_ID:
        raise SystemExit(f"RPC chain_id {web3.eth.chain_id}, expected {ARBITRUM_CHAIN_ID}")
    return account, trader, Web3.to_checksum_address(agent), web3


def build_transfer(web3: Web3, trader: str, agent: str, amount_eth: Decimal) -> dict[str, Any]:
    return {
        "from": trader,
        "to": agent,
        "chainId": ARBITRUM_CHAIN_ID,
        "nonce": web3.eth.get_transaction_count(trader, "pending"),
        "value": int(amount_eth * Decimal(10**18)),
        "gas": 50_000,
        **fee_params(web3),
    }


def balances(web3: Web3, trader: str, agent: str) -> dict[str, str]:
    return {
        "traderEth": str(Decimal(web3.eth.get_balance(trader)) / Decimal(10**18)),
        "agentEth": str(Decimal(web3.eth.get_balance(agent)) / Decimal(10**18)),
    }


def fee_params(web3: Web3) -> dict[str, int]:
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    try:
        priority = int(web3.eth.max_priority_fee)
    except Exception:
        priority = 0
    priority = max(priority, 10_000_000)
    return {
        "maxFeePerGas": int(Decimal(base_fee) * Decimal("2.0")) + priority,
        "maxPriorityFeePerGas": priority,
    }


def normalize_pk(value: str) -> str:
    key = value.strip().strip('"').strip("'")
    return key if key.startswith("0x") else f"0x{key}"


if __name__ == "__main__":
    main()
