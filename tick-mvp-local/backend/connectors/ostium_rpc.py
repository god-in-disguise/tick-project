from __future__ import annotations

import os
import time
from typing import Any, Iterable

from eth_abi import decode
from hexbytes import HexBytes
from web3 import Web3


TRADING = "0x6D0bA1f9996DBD8885827e1b2e8f6593e7702411"
TRADING_CALLBACKS = "0x7720fC8c8680bF4a1Af99d44c6c265a74e9742a9"
CONFIRM_TIMEOUT_SECONDS = float(os.getenv("OSTIUM_RPC_CONFIRM_SECONDS", "6"))
CONFIRM_POLL_SECONDS = float(os.getenv("OSTIUM_RPC_POLL_SECONDS", "0.2"))

OPEN_INITIATED = Web3.keccak(text="MarketOpenOrderInitiated(uint256,address,uint16)")
CLOSE_INITIATED = Web3.keccak(text="MarketCloseOrderInitiated(uint256,uint256,address,uint16)")
CLOSE_INITIATED_V2 = Web3.keccak(text="MarketCloseOrderInitiatedV2(uint256,uint256,address,uint16,uint16)")
OPEN_EXECUTED = Web3.keccak(
    text="MarketOpenExecuted(uint256,(uint256,uint192,uint192,uint192,address,uint32,uint16,uint8,bool,bool),uint256,uint256)"
)
OPEN_CANCELED = Web3.keccak(text="MarketOpenCanceled(uint256,address,uint256,uint8)")
CLOSE_EXECUTED = Web3.keccak(text="MarketCloseExecuted(uint256,uint256,uint256,uint256,int256,uint256)")
CLOSE_EXECUTED_V2 = Web3.keccak(text="MarketCloseExecutedV2(uint256,uint256,uint256,uint256,int256,uint256,uint256)")
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


def wait_for_open_callback(web3: Web3, tx_hash: str, pair: str) -> dict[str, Any]:
    initiated = _initiated_order(web3, tx_hash, "open")
    callback, error, elapsed = _wait_for_callback(
        web3,
        initiated,
        (OPEN_EXECUTED, OPEN_CANCELED),
    )
    confirmation = _confirmation(initiated, callback, elapsed, error)
    if callback is None:
        return {"status": "pending_execution", "position": None, "confirmation": confirmation}

    event = _topic(callback, 0)
    if event == OPEN_CANCELED:
        reason_code = int(decode(["uint8"], bytes(_value(callback, "data")))[0])
        return {
            "status": "cancelled",
            "position": None,
            "cancelReason": _cancel_reason(reason_code),
            "confirmation": confirmation,
        }

    trade, price_impact, notional = decode(
        ["(uint256,uint192,uint192,uint192,address,uint32,uint16,uint8,bool,bool)", "uint256", "uint256"],
        bytes(_value(callback, "data")),
    )
    collateral, open_price, _, _, _, leverage, pair_id, index, is_buy, _ = trade
    position = {
        "pair": pair,
        "pairId": int(pair_id),
        "idx": int(index),
        "tradeId": initiated["orderId"],
        "side": "long" if is_buy else "short",
        "entry": float(open_price) / 1e18,
        "mark": float(open_price) / 1e18,
        "collateral": float(collateral) / 1e6,
        "leverage": float(leverage) / 100,
        "pnl": 0.0,
        "roePct": 0.0,
        "openedAt": int(time.time()),
        "optimistic": False,
        "closeAvailable": True,
    }
    return {
        "status": "opened",
        "position": position,
        "priceImpact": int(price_impact),
        "tradeNotional": int(notional),
        "confirmation": confirmation,
    }


def wait_for_close_callback(web3: Web3, tx_hash: str) -> dict[str, Any]:
    initiated = _initiated_order(web3, tx_hash, "close")
    callback, error, elapsed = _wait_for_callback(
        web3,
        initiated,
        (CLOSE_EXECUTED, CLOSE_EXECUTED_V2, CLOSE_CANCELED),
    )
    confirmation = _confirmation(initiated, callback, elapsed, error)
    if callback is None:
        return {"status": "pending_execution", "closed": False, "confirmation": confirmation}

    event = _topic(callback, 0)
    if event == CLOSE_CANCELED:
        _, _, reason_code = decode(["uint256", "uint256", "uint8"], bytes(_value(callback, "data")))
        return {
            "status": "cancelled",
            "closed": False,
            "cancelReason": _cancel_reason(int(reason_code)),
            "confirmation": confirmation,
        }

    schema = ["uint256", "uint256", "int256", "uint256"]
    if event == CLOSE_EXECUTED_V2:
        schema.append("uint256")
    values = decode(schema, bytes(_value(callback, "data")))
    price, price_impact, percent_profit, usdc_sent = values[:4]
    return {
        "status": "closed",
        "closed": True,
        "price": float(price) / 1e18,
        "priceImpact": int(price_impact),
        "percentProfit": float(percent_profit) / 1e10,
        "usdcSentToTrader": float(usdc_sent) / 1e6,
        "percentageClosed": int(values[4]) if len(values) > 4 else 10000,
        "confirmation": confirmation,
    }


def _initiated_order(web3: Web3, tx_hash: str, action: str) -> dict[str, Any]:
    receipt = web3.eth.get_transaction_receipt(tx_hash)
    expected = {OPEN_INITIATED} if action == "open" else {CLOSE_INITIATED, CLOSE_INITIATED_V2}
    for log in _value(receipt, "logs"):
        if str(_value(log, "address")).lower() != TRADING.lower() or _topic(log, 0) not in expected:
            continue
        result = {
            "action": action,
            "orderId": _topic_int(log, 1),
            "initiatedBlock": int(_value(receipt, "blockNumber")),
            "initiatedTx": tx_hash,
        }
        if action == "open":
            result["pairId"] = _topic_int(log, 3)
        else:
            result["tradeId"] = _topic_int(log, 2)
        return result
    raise ValueError(f"{action} initiation event was not found in {tx_hash}")


def _wait_for_callback(
    web3: Web3,
    initiated: dict[str, Any],
    event_topics: Iterable[HexBytes],
) -> tuple[Any | None, str | None, float]:
    started = time.perf_counter()
    deadline = started + CONFIRM_TIMEOUT_SECONDS
    error: str | None = None
    order_topic = HexBytes(int(initiated["orderId"]).to_bytes(32, "big"))
    while time.perf_counter() <= deadline:
        try:
            logs = web3.eth.get_logs(
                {
                    "address": Web3.to_checksum_address(TRADING_CALLBACKS),
                    "fromBlock": int(initiated["initiatedBlock"]),
                    "toBlock": "latest",
                    "topics": [list(event_topics), order_topic],
                }
            )
            if logs:
                callback = sorted(logs, key=lambda item: (int(_value(item, "blockNumber")), int(_value(item, "logIndex"))))[0]
                return callback, None, time.perf_counter() - started
            error = None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        time.sleep(CONFIRM_POLL_SECONDS)
    return None, error, time.perf_counter() - started


def _confirmation(
    initiated: dict[str, Any],
    callback: Any | None,
    elapsed: float,
    error: str | None,
) -> dict[str, Any]:
    result = {
        **initiated,
        "source": "arbitrum_rpc",
        "latencySeconds": round(elapsed, 3),
        "error": error,
    }
    if callback is not None:
        callback_block = int(_value(callback, "blockNumber"))
        result.update(
            {
                "callbackBlock": callback_block,
                "callbackTx": Web3.to_hex(_value(callback, "transactionHash")),
                "blockDelta": callback_block - int(initiated["initiatedBlock"]),
            }
        )
    return result


def _cancel_reason(code: int) -> str:
    return CANCEL_REASONS[code] if 0 <= code < len(CANCEL_REASONS) else f"reason_{code}"


def _topic(log: Any, index: int) -> HexBytes:
    return HexBytes(_value(log, "topics")[index])


def _topic_int(log: Any, index: int) -> int:
    return int.from_bytes(_topic(log, index), "big")


def _value(value: Any, key: str) -> Any:
    return value[key] if isinstance(value, dict) else getattr(value, key)
