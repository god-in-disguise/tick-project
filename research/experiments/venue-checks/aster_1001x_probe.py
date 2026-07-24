#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any

import requests
from dotenv import load_dotenv
from eth_account import Account
from eth_utils import to_checksum_address
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware


ASTER_1001X_CONTRACT = "0x1b6f2d3844c6ae7d56ceb3c3643b9060ba28feb0"
BSC_CHAIN_ID = 56
PUBLIC_BSC_RPCS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc-dataseed1.defibit.io/",
    "https://bsc-dataseed1.ninicoin.io/",
]

TOKENS = {
    "USDT": "0x55d398326f99059fF775485246999027B3197955",
    "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
}

PAIRS = {
    "BTC": {
        "symbol": "BTCUSDT",
        "base": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
    },
    "ETH": {
        "symbol": "ETHUSDT",
        "base": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    },
}

ASTER_ABI = [
    {
        "inputs": [],
        "name": "paused",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getTradingConfig",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "executionFeeUsd", "type": "uint256"},
                    {"internalType": "uint256", "name": "minNotionalUsd", "type": "uint256"},
                    {"internalType": "uint24", "name": "maxTakeProfitP", "type": "uint24"},
                    {"internalType": "bool", "name": "limitOrder", "type": "bool"},
                    {"internalType": "bool", "name": "executeLimitOrder", "type": "bool"},
                    {"internalType": "bool", "name": "marketTrading", "type": "bool"},
                    {"internalType": "bool", "name": "userCloseTrading", "type": "bool"},
                    {"internalType": "bool", "name": "tpSlCloseTrading", "type": "bool"},
                    {"internalType": "bool", "name": "liquidateTrading", "type": "bool"},
                ],
                "internalType": "struct ITradingConfig.TradingConfig",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "base", "type": "address"}],
        "name": "getPairForTrading",
        "outputs": [
            {
                "components": [
                    {"internalType": "address", "name": "base", "type": "address"},
                    {"internalType": "string", "name": "name", "type": "string"},
                    {"internalType": "enum IPairsManager.PairType", "name": "pairType", "type": "uint8"},
                    {"internalType": "enum IPairsManager.PairStatus", "name": "status", "type": "uint8"},
                    {
                        "components": [
                            {"internalType": "uint256", "name": "maxLongOiUsd", "type": "uint256"},
                            {"internalType": "uint256", "name": "maxShortOiUsd", "type": "uint256"},
                            {"internalType": "uint256", "name": "fundingFeePerBlockP", "type": "uint256"},
                            {"internalType": "uint256", "name": "minFundingFeeR", "type": "uint256"},
                            {"internalType": "uint256", "name": "maxFundingFeeR", "type": "uint256"},
                        ],
                        "internalType": "struct IPairsManager.PairMaxOiAndFundingFeeConfig",
                        "name": "pairConfig",
                        "type": "tuple",
                    },
                    {
                        "components": [
                            {"internalType": "uint256", "name": "notionalUsd", "type": "uint256"},
                            {"internalType": "uint16", "name": "maxLeverage", "type": "uint16"},
                            {"internalType": "uint16", "name": "initialLostP", "type": "uint16"},
                            {"internalType": "uint16", "name": "liqLostP", "type": "uint16"},
                        ],
                        "internalType": "struct IPairsManager.LeverageMargin[]",
                        "name": "leverageMargins",
                        "type": "tuple[]",
                    },
                    {
                        "components": [
                            {"internalType": "uint256", "name": "onePercentDepthAboveUsd", "type": "uint256"},
                            {"internalType": "uint256", "name": "onePercentDepthBelowUsd", "type": "uint256"},
                            {"internalType": "uint16", "name": "slippageLongP", "type": "uint16"},
                            {"internalType": "uint16", "name": "slippageShortP", "type": "uint16"},
                            {"internalType": "enum ISlippageManager.SlippageType", "name": "slippageType", "type": "uint8"},
                        ],
                        "internalType": "struct ISlippageManager.SlippageConfig",
                        "name": "slippageConfig",
                        "type": "tuple",
                    },
                    {
                        "components": [
                            {"internalType": "uint16", "name": "openFeeP", "type": "uint16"},
                            {"internalType": "uint16", "name": "closeFeeP", "type": "uint16"},
                            {"internalType": "uint24", "name": "shareP", "type": "uint24"},
                            {"internalType": "uint24", "name": "minCloseFeeP", "type": "uint24"},
                        ],
                        "internalType": "struct IPairsManager.FeeConfig",
                        "name": "feeConfig",
                        "type": "tuple",
                    },
                ],
                "internalType": "struct IPairsManager.TradingPair",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "tokenAddress", "type": "address"}],
        "name": "getTokenForTrading",
        "outputs": [
            {
                "components": [
                    {"internalType": "address", "name": "token", "type": "address"},
                    {"internalType": "bool", "name": "switchOn", "type": "bool"},
                    {"internalType": "uint8", "name": "decimals", "type": "uint8"},
                    {"internalType": "uint256", "name": "price", "type": "uint256"},
                ],
                "internalType": "struct IVault.MarginToken",
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "pairBase", "type": "address"},
                    {"internalType": "bool", "name": "isLong", "type": "bool"},
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "uint96", "name": "amountIn", "type": "uint96"},
                    {"internalType": "uint80", "name": "qty", "type": "uint80"},
                    {"internalType": "uint64", "name": "price", "type": "uint64"},
                    {"internalType": "uint64", "name": "stopLoss", "type": "uint64"},
                    {"internalType": "uint64", "name": "takeProfit", "type": "uint64"},
                    {"internalType": "uint24", "name": "broker", "type": "uint24"},
                ],
                "internalType": "struct IBook.OpenDataInput",
                "name": "data",
                "type": "tuple",
            }
        ],
        "name": "openMarketTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "tradeHash", "type": "bytes32"}],
        "name": "closeTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

ERC20_ABI = [
    {"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "account", "type": "address"}], "name": "balanceOf", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass(frozen=True)
class RpcChoice:
    url: str
    chain_id: int
    elapsed_ms: float


def decimal_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    raise TypeError(f"Unsupported JSON type: {type(value)!r}")


def choose_rpc(explicit: str | None) -> tuple[Web3, RpcChoice]:
    candidates = [
        explicit,
        os.getenv("ASTER_1001X_RPC_URL"),
        os.getenv("BSC_RPC_URL"),
        os.getenv("BNB_RPC_URL"),
        *PUBLIC_BSC_RPCS,
    ]
    errors: list[str] = []
    for candidate in [item for item in candidates if item]:
        started = time.perf_counter()
        try:
            web3 = Web3(Web3.HTTPProvider(candidate, request_kwargs={"timeout": 12}))
            web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            chain_id = web3.eth.chain_id
            elapsed_ms = (time.perf_counter() - started) * 1000
            if chain_id != BSC_CHAIN_ID:
                errors.append(f"{candidate}: unexpected chain id {chain_id}")
                continue
            return web3, RpcChoice(candidate, chain_id, round(elapsed_ms, 1))
        except Exception as exc:  # noqa: BLE001 - probe should try every candidate.
            errors.append(f"{candidate}: {exc}")
    raise SystemExit("No working BSC RPC found:\n" + "\n".join(errors))


def wallet_from_env(name: str) -> str | None:
    private_key = os.getenv(name)
    if not private_key:
        return None
    try:
        return Account.from_key(private_key).address
    except Exception as exc:  # noqa: BLE001 - do not print the key, only config status.
        raise SystemExit(f"{name} is present but is not a valid EVM private key: {exc}") from exc


def fetch_price(symbol: str) -> Decimal | None:
    try:
        response = requests.get(
            "https://www.apollox.finance/fapi/v1/premiumIndex",
            params={"symbol": symbol},
            timeout=12,
            headers={"user-agent": "tick-venue-probe/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
        item = next((row for row in payload if row.get("symbol") == symbol), None) if isinstance(payload, list) else payload
        if not item:
            return None
        for key in ("indexPrice", "markPrice", "estimatedSettlePrice"):
            if item.get(key):
                return Decimal(str(item[key]))
    except Exception:
        return None
    return None


def scaled_usd(value: int) -> Decimal:
    return Decimal(value) / Decimal(10) ** 18


def pct_1e4(value: int) -> Decimal:
    return Decimal(value) / Decimal(10) ** 4


def pct_1e5(value: int) -> Decimal:
    return Decimal(value) / Decimal(10) ** 5


def pair_summary(pair: Any) -> dict[str, Any]:
    pair_config = pair[4]
    leverage_margins = pair[5]
    slippage = pair[6]
    fee = pair[7]
    return {
        "base": pair[0],
        "name": pair[1],
        "pairType": pair[2],
        "status": pair[3],
        "maxLongOiUsd": str(scaled_usd(pair_config[0])),
        "maxShortOiUsd": str(scaled_usd(pair_config[1])),
        "fundingFeePerBlockP": str(Decimal(pair_config[2]) / Decimal(10) ** 18),
        "leverageMargins": [
            {
                "notionalUsd": str(scaled_usd(item[0])),
                "maxLeverage": item[1],
                "initialLostPct": str(pct_1e4(item[2])),
                "liqLostPct": str(pct_1e4(item[3])),
            }
            for item in leverage_margins
        ],
        "slippage": {
            "onePercentDepthAboveUsd": str(scaled_usd(slippage[0])),
            "onePercentDepthBelowUsd": str(scaled_usd(slippage[1])),
            "slippageLongPct": str(pct_1e4(slippage[2])),
            "slippageShortPct": str(pct_1e4(slippage[3])),
            "slippageType": slippage[4],
        },
        "fee": {
            "openFeePct": str(pct_1e4(fee[0])),
            "closeFeePct": str(pct_1e4(fee[1])),
            "sharePct": str(pct_1e5(fee[2])),
            "minCloseFeePct": str(pct_1e5(fee[3])),
        },
    }


def trading_config_summary(config: Any) -> dict[str, Any]:
    return {
        "executionFeeUsd": str(scaled_usd(config[0])),
        "minNotionalUsd": str(scaled_usd(config[1])),
        "maxTakeProfitPct": str(pct_1e5(config[2])),
        "limitOrder": config[3],
        "executeLimitOrder": config[4],
        "marketTrading": config[5],
        "userCloseTrading": config[6],
        "tpSlCloseTrading": config[7],
        "liquidateTrading": config[8],
    }


def token_summary(token: Any) -> dict[str, Any]:
    return {
        "token": token[0],
        "switchOn": token[1],
        "decimals": token[2],
        "price": str(Decimal(token[3]) / Decimal(10) ** 8),
        "rawPrice": token[3],
    }


def build_open_tuple(
    *,
    pair_base: str,
    is_long: bool,
    token_in: str,
    collateral_usd: Decimal,
    leverage: Decimal,
    index_price: Decimal,
    slippage_bps: Decimal,
    broker: int,
) -> tuple[Any, ...]:
    notional = collateral_usd * leverage
    qty = (notional / index_price * Decimal("1e10")).quantize(Decimal("1"), rounding=ROUND_DOWN)
    multiplier = Decimal(1) + slippage_bps / Decimal(10000)
    if not is_long:
        multiplier = Decimal(1) - slippage_bps / Decimal(10000)
    worst_price = (index_price * multiplier * Decimal("1e8")).quantize(Decimal("1"), rounding=ROUND_DOWN)
    amount_in = (collateral_usd * Decimal("1e18")).quantize(Decimal("1"), rounding=ROUND_DOWN)
    return (
        to_checksum_address(pair_base),
        is_long,
        to_checksum_address(token_in),
        int(amount_in),
        int(qty),
        int(worst_price),
        0,
        0,
        broker,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Aster 1001x direct-contract trading on BNB Chain.")
    parser.add_argument("--rpc", help="BNB Chain RPC URL. Falls back to env/public RPCs.")
    parser.add_argument("--symbol", choices=sorted(PAIRS), default="BTC")
    parser.add_argument("--margin-token", choices=sorted(TOKENS), default="USDT")
    parser.add_argument("--wallet", help="Wallet address for balance/allowance reads.")
    parser.add_argument("--wallet-env", default="WALLET_PK")
    parser.add_argument("--simulate-open", action="store_true")
    parser.add_argument("--side", choices=["long", "short"], default="long")
    parser.add_argument("--collateral-usd", type=Decimal, default=Decimal("20"))
    parser.add_argument("--leverage", type=Decimal, default=Decimal("100"))
    parser.add_argument("--slippage-bps", type=Decimal, default=Decimal("30"))
    parser.add_argument("--broker", type=int, default=1)
    args = parser.parse_args()

    load_dotenv()
    web3, rpc = choose_rpc(args.rpc)
    contract = web3.eth.contract(address=to_checksum_address(ASTER_1001X_CONTRACT), abi=ASTER_ABI)
    pair = PAIRS[args.symbol]
    token_address = to_checksum_address(TOKENS[args.margin_token])
    base = to_checksum_address(pair["base"])
    wallet = args.wallet or wallet_from_env(args.wallet_env)
    wallet = to_checksum_address(wallet) if wallet else None

    started = time.perf_counter()
    code_size = len(web3.eth.get_code(contract.address))
    result: dict[str, Any] = {
        "network": {"rpc": asdict(rpc), "contract": contract.address, "codeBytes": code_size},
        "protocol": {
            "paused": contract.functions.paused().call(),
            "tradingConfig": trading_config_summary(contract.functions.getTradingConfig().call()),
            "pair": pair_summary(contract.functions.getPairForTrading(base).call()),
            "marginToken": token_summary(contract.functions.getTokenForTrading(token_address).call()),
        },
    }
    result["protocol"]["readElapsedMs"] = round((time.perf_counter() - started) * 1000, 1)

    if wallet:
        token = web3.eth.contract(address=token_address, abi=ERC20_ABI)
        decimals = token.functions.decimals().call()
        balance = token.functions.balanceOf(wallet).call()
        allowance = token.functions.allowance(wallet, contract.address).call()
        result["wallet"] = {
            "address": wallet,
            "bnb": str(web3.from_wei(web3.eth.get_balance(wallet), "ether")),
            "token": args.margin_token,
            "tokenBalance": str(Decimal(balance) / Decimal(10) ** decimals),
            "allowanceToAster1001x": str(Decimal(allowance) / Decimal(10) ** decimals),
        }

    price = fetch_price(pair["symbol"])
    result["price"] = {"symbol": pair["symbol"], "indexPrice": str(price) if price else None}

    if args.simulate_open:
        if not wallet:
            raise SystemExit("--simulate-open requires --wallet or a valid WALLET_PK")
        if price is None:
            raise SystemExit("Could not fetch index price for simulation")
        open_tuple = build_open_tuple(
            pair_base=base,
            is_long=args.side == "long",
            token_in=token_address,
            collateral_usd=args.collateral_usd,
            leverage=args.leverage,
            index_price=price,
            slippage_bps=args.slippage_bps,
            broker=args.broker,
        )
        nonce = web3.eth.get_transaction_count(wallet)
        tx = contract.functions.openMarketTrade(open_tuple).build_transaction(
            {
                "from": wallet,
                "chainId": BSC_CHAIN_ID,
                "nonce": nonce,
                "gas": 1_000_000,
                "gasPrice": web3.eth.gas_price,
            }
        )
        simulation: dict[str, Any] = {
            "side": args.side,
            "collateralUsd": str(args.collateral_usd),
            "leverage": str(args.leverage),
            "notionalUsd": str(args.collateral_usd * args.leverage),
            "tuple": list(open_tuple),
            "calldataBytes": len(tx["data"]) // 2 - 1,
        }
        call_tx = {
            "from": wallet,
            "to": contract.address,
            "data": tx["data"],
            "gas": tx["gas"],
            "gasPrice": 0,
        }
        try:
            call_started = time.perf_counter()
            web3.eth.call(call_tx)
            simulation["ethCallOk"] = True
            simulation["ethCallMs"] = round((time.perf_counter() - call_started) * 1000, 1)
        except Exception as exc:  # noqa: BLE001 - revert reason is useful output.
            simulation["ethCallOk"] = False
            simulation["ethCallError"] = str(exc)
        try:
            gas_started = time.perf_counter()
            simulation["gasEstimate"] = web3.eth.estimate_gas(tx)
            simulation["estimateGasMs"] = round((time.perf_counter() - gas_started) * 1000, 1)
        except Exception as exc:  # noqa: BLE001 - revert reason is useful output.
            simulation["gasEstimateError"] = str(exc)
        result["openSimulation"] = simulation

    print(json.dumps(result, indent=2, default=decimal_json))


if __name__ == "__main__":
    main()
