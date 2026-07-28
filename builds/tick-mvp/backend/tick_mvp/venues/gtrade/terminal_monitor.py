from __future__ import annotations

import queue
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterable

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import PositionStatus
from tick_mvp.venues.base import TerminalPositionEvent
from tick_mvp.venues.gtrade.constants import ERC20_ABI
from tick_mvp.venues.gtrade.events import GTradeEventStream
from tick_mvp.venues.gtrade.onchain_events import (
    LIMIT_EXECUTED_TOPIC,
    MARKET_EXECUTED_TOPIC,
    decode_execution_log,
)


TAKE_PROFIT_ORDER_TYPE = 4
STOP_LOSS_ORDER_TYPE = 5
LIQUIDATION_ORDER_TYPE = 6
RECOVERY_BLOCK_CHUNK = 2_000


class GTradeTerminalMonitor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._events: queue.Queue[TerminalPositionEvent] = queue.Queue()
        self._stream = GTradeEventStream(
            settings.gtrade_backend_ws_url,
            arb_wss_url=settings.arb_wss_url,
            diamond_address=settings.gtrade_diamond_address,
            on_event=self._capture,
        )
        self._web3 = None
        self._usdc = None

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def track_owners(self, owners: Iterable[str]) -> None:
        for owner in owners:
            self._stream.track_owner(owner)

    def next_event(self, timeout: float = 0.25) -> TerminalPositionEvent | None:
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty:
            return None

    def collateral_balance_usd(self, owner: str) -> Decimal:
        units = self._usdc_contract().functions.balanceOf(self._checksum(owner)).call()
        return Decimal(units) / Decimal(10**6)

    def latest_block(self) -> int:
        return int(self._rpc().eth.block_number)

    def recover_recent(self, *, from_block: int) -> list[TerminalPositionEvent]:
        web3 = self._rpc()
        latest = int(web3.eth.block_number)
        recovered: list[TerminalPositionEvent] = []
        block_timestamps: dict[int, float] = {}
        for start in range(max(0, from_block), latest + 1, RECOVERY_BLOCK_CHUNK):
            end = min(latest, start + RECOVERY_BLOCK_CHUNK - 1)
            logs = web3.eth.get_logs(
                {
                    "fromBlock": start,
                    "toBlock": end,
                    "address": self._checksum(self._settings.gtrade_diamond_address),
                    "topics": [[MARKET_EXECUTED_TOPIC, LIMIT_EXECUTED_TOPIC]],
                }
            )
            for row in logs:
                block_number = int(row["blockNumber"])
                block_timestamp = block_timestamps.get(block_number)
                if block_timestamp is None:
                    block_timestamp = float(web3.eth.get_block(block_number)["timestamp"])
                    block_timestamps[block_number] = block_timestamp
                event = _terminal_event(
                    _normalize_log(row, received_at=block_timestamp)
                )
                if event is not None:
                    recovered.append(event)
        return recovered

    def _capture(self, raw: dict[str, Any]) -> None:
        event = _terminal_event(raw)
        if event is not None:
            self._events.put(event)

    def _rpc(self):
        if self._web3 is None:
            from web3 import Web3

            self._web3 = Web3(
                Web3.HTTPProvider(
                    self._settings.arb_rpc_url,
                    request_kwargs={"timeout": 20},
                )
            )
        return self._web3

    def _usdc_contract(self):
        if self._usdc is None:
            self._usdc = self._rpc().eth.contract(
                address=self._checksum(self._settings.gtrade_usdc_address),
                abi=ERC20_ABI,
            )
        return self._usdc

    @staticmethod
    def _checksum(address: str) -> str:
        from web3 import Web3

        return Web3.to_checksum_address(address)


def _terminal_event(raw: dict[str, Any]) -> TerminalPositionEvent | None:
    if raw.get("present") is not False:
        return None
    trade = (raw.get("position") or {}).get("trade") or {}
    owner = str(trade.get("user") or "").lower()
    pair_index = _int_or_none(trade.get("pairIndex"))
    position_index = _int_or_none(trade.get("index"))
    if not owner or pair_index is None or position_index is None:
        return None

    details = dict(raw.get("details") or {})
    order_type = _int_or_none(details.get("orderType"))
    reason = {
        TAKE_PROFIT_ORDER_TYPE: "take_profit",
        STOP_LOSS_ORDER_TYPE: "stop_loss",
        LIQUIDATION_ORDER_TYPE: "liquidation",
    }.get(order_type, "manual_close" if raw.get("name") == "MarketExecuted" else "external_close")
    returned = _usdc_from_units(details.get("amountSentToTrader"))
    received_at = float(raw.get("receivedAt") or time.time())
    return TerminalPositionEvent(
        venue="gtrade",
        owner=owner,
        venue_position_id=f"{pair_index}:{position_index}",
        status=PositionStatus.LIQUIDATED if reason == "liquidation" else PositionStatus.CLOSED,
        reason=reason,
        source=str(raw.get("source") or "gtrade_event_stream"),
        observed_at=datetime.fromtimestamp(received_at, UTC),
        transaction_hash=_string_or_none(raw.get("transactionHash")),
        block_number=_int_or_none(raw.get("blockNumber")),
        log_index=_int_or_none(raw.get("logIndex")),
        returned_collateral_usd=returned,
        payload=raw,
    )


def _normalize_log(row: Any, *, received_at: float | None = None) -> dict[str, Any]:
    raw = {
        "topics": [_hex(value) for value in row["topics"]],
        "data": _hex(row["data"]),
        "transactionHash": _hex(row["transactionHash"]),
        "blockNumber": int(row["blockNumber"]),
        "logIndex": int(row["logIndex"]),
    }
    event = decode_execution_log(raw) or {}
    event["receivedAt"] = received_at or time.time()
    return event


def _hex(value: Any) -> str:
    encoded = value.hex() if hasattr(value, "hex") else str(value)
    return encoded if encoded.startswith("0x") else f"0x{encoded}"


def _usdc_from_units(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) / Decimal(10**6)
    except (ValueError, TypeError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value else None
