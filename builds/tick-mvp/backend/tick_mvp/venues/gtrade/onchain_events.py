from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

from eth_abi import decode
from websockets.sync.client import connect


LOGGER = logging.getLogger("tick.gtrade.onchain")
MAX_ONCHAIN_FRAME_BYTES = 4 * 1024 * 1024

# Pinned from GainsNetwork-org/sdk GNSMultiCollatDiamond ABI.
MARKET_EXECUTED_TOPIC = "0xbdc1265da95238ea4c775f66ac8fe748af83982c4b356ac4d0c28a0f512c0a8b"
LIMIT_EXECUTED_TOPIC = "0x9c19bc42a9be820f3366fa0563f85e5c227966eaea4c45acd2f7cd868086a17d"

TRADE_TYPE = "(address,uint32,uint16,uint24,bool,bool,uint8,uint8,uint120,uint64,uint64,uint64,bool,uint160,uint24)"
PRICE_IMPACT_TYPE = "(uint256,int256,int256,int256,int256,uint64)"
MARKET_EXECUTED_DATA_TYPES = [
    "(address,uint32)",
    TRADE_TYPE,
    "bool",
    "uint256",
    "uint256",
    "uint256",
    PRICE_IMPACT_TYPE,
    "int256",
    "uint256",
    "uint256",
]
LIMIT_EXECUTED_DATA_TYPES = [
    "(address,uint32)",
    TRADE_TYPE,
    "address",
    "uint8",
    "uint256",
    "uint256",
    "uint256",
    PRICE_IMPACT_TYPE,
    "int256",
    "uint256",
    "uint256",
    "bool",
]
TRADE_FIELDS = (
    "user",
    "index",
    "pairIndex",
    "leverage",
    "long",
    "isOpen",
    "collateralIndex",
    "tradeType",
    "collateralAmount",
    "openPrice",
    "tp",
    "sl",
    "isCounterTrade",
    "positionSizeToken",
    "__placeholder",
)


class GTradeOnchainEventStream:
    """Direct Arbitrum soft-final callback stream for Gains executions."""

    def __init__(self, url: str, diamond_address: str, on_event: Callable[[dict[str, Any]], None]) -> None:
        self._url = url
        self._diamond_address = diamond_address
        self._on_event = on_event
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._last_message_at = 0.0
        self._last_error: str | None = None

    def start(self) -> None:
        if not self._url or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gtrade-onchain", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def health(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._url),
            "running": bool(self._thread and self._thread.is_alive()),
            "connected": self._connected,
            "lastMessageAt": self._last_message_at or None,
            "lastError": self._last_error,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with connect(
                    self._url,
                    open_timeout=10,
                    close_timeout=2,
                    max_size=MAX_ONCHAIN_FRAME_BYTES,
                ) as websocket:
                    websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": 1,
                                "method": "eth_subscribe",
                                "params": [
                                    "logs",
                                    {
                                        "address": self._diamond_address,
                                        "topics": [[MARKET_EXECUTED_TOPIC, LIMIT_EXECUTED_TOPIC]],
                                    },
                                ],
                            }
                        )
                    )
                    subscription = json.loads(websocket.recv(timeout=10))
                    if subscription.get("error") or not subscription.get("result"):
                        raise RuntimeError(f"eth_subscribe failed: {subscription.get('error')}")
                    self._connected = True
                    self._last_error = None
                    last_ping_at = time.monotonic()
                    while not self._stop.is_set():
                        try:
                            raw = websocket.recv(timeout=1)
                        except TimeoutError:
                            if time.monotonic() - last_ping_at >= 20:
                                websocket.ping()
                                last_ping_at = time.monotonic()
                            continue
                        self._handle_raw(raw)
            except Exception as exc:
                self._connected = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                LOGGER.warning("Arbitrum callback stream disconnected: %s", exc)
                self._stop.wait(0.75)
        self._connected = False

    def _handle_raw(self, raw: str | bytes) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("method") != "eth_subscription":
            return
        log = ((payload.get("params") or {}).get("result") or {})
        if log.get("removed"):
            return
        event = decode_execution_log(log)
        if event is None:
            return
        self._last_message_at = time.time()
        event["receivedAt"] = self._last_message_at
        self._on_event(event)


def decode_execution_log(log: dict[str, Any]) -> dict[str, Any] | None:
    topics = [str(value).lower() for value in log.get("topics") or []]
    if len(topics) < 3:
        return None
    topic = topics[0]
    try:
        raw_data = bytes.fromhex(str(log.get("data") or "0x").removeprefix("0x"))
        if topic == MARKET_EXECUTED_TOPIC:
            values = decode(MARKET_EXECUTED_DATA_TYPES, raw_data)
            trade = _trade_dict(values[1])
            present = bool(values[2])
            details = {
                "oraclePrice": str(values[3]),
                "marketPrice": str(values[4]),
                "liquidationPrice": str(values[5]),
                "percentProfit": str(values[7]),
                "amountSentToTrader": str(values[8]),
                "collateralPriceUsd": str(values[9]),
            }
            name = "MarketExecuted"
        elif topic == LIMIT_EXECUTED_TOPIC:
            values = decode(LIMIT_EXECUTED_DATA_TYPES, raw_data)
            trade = _trade_dict(values[1])
            order_type = int(values[3])
            present = order_type in {2, 3}
            details = {
                "orderType": order_type,
                "oraclePrice": str(values[4]),
                "marketPrice": str(values[5]),
                "liquidationPrice": str(values[6]),
                "percentProfit": str(values[8]),
                "amountSentToTrader": str(values[9]),
                "collateralPriceUsd": str(values[10]),
            }
            name = "LimitExecuted"
        else:
            return None
    except Exception as exc:
        LOGGER.warning("Could not decode Gains execution log: %s", exc)
        return None
    return {
        "name": name,
        "source": "gtrade_onchain_ws",
        "present": present,
        "position": {"trade": trade},
        "transactionHash": str(log.get("transactionHash") or ""),
        "blockNumber": _hex_int(log.get("blockNumber")),
        "logIndex": _hex_int(log.get("logIndex")),
        "details": details,
    }


def _trade_dict(values: tuple[Any, ...]) -> dict[str, Any]:
    return {name: value for name, value in zip(TRADE_FIELDS, values, strict=True)}


def _hex_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(str(value), 16) if str(value).startswith("0x") else int(value)
