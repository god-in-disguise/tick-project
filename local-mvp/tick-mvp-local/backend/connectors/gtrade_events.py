from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any

from websockets.sync.client import connect

from .gtrade_constants import ARBITRUM_BACKEND_WS
from .gtrade_latency import write_latency_event


LOGGER = logging.getLogger("tick.gtrade.events")


class GTradeEventStream:
    """Small in-process cache over the gTrade backend event stream."""

    def __init__(self, owner: str) -> None:
        self.owner = owner.lower()
        self._events: deque[dict[str, Any]] = deque(maxlen=512)
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_block: int | None = None
        self._last_message_at = 0.0
        self._last_error: str | None = None
        self._last_message_name: str | None = None
        self._max_raw_bytes = 0
        self._message_count = 0
        self._matched_event_count = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gtrade-event-stream", daemon=True)
        self._thread.start()

    def health(self) -> dict[str, Any]:
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "lastMessageAt": self._last_message_at or None,
            "currentBlock": self._current_block,
            "cachedEvents": len(self._events),
            "error": self._last_error,
            "lastMessageName": self._last_message_name,
            "messageCount": self._message_count,
            "matchedEventCount": self._matched_event_count,
            "maxRawBytes": self._max_raw_bytes,
        }

    def wait_for_position_event(
        self,
        pair_index: int,
        *,
        present: bool,
        since: float,
        timeout_seconds: float,
        position_index: int | None = None,
    ) -> dict[str, Any]:
        event_name = "registerTrade" if present else "unregisterTrade"
        started = time.perf_counter()
        started_at = time.time()
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while True:
                event = self._find_event(event_name, pair_index, since, position_index=position_index)
                if event:
                    return {
                        "source": "backend_ws",
                        "event": event,
                        "position": event.get("position") if present else None,
                        "startedAt": started_at,
                        "finishedAt": time.time(),
                        "elapsedMs": _elapsed_ms(started),
                        "targetPresent": present,
                        "observedPresent": present,
                        "timedOut": False,
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {
                        "source": "backend_ws",
                        "event": None,
                        "position": None,
                        "startedAt": started_at,
                        "finishedAt": time.time(),
                        "elapsedMs": _elapsed_ms(started),
                        "targetPresent": present,
                        "observedPresent": None,
                    "timedOut": True,
                }
                self._condition.wait(timeout=min(0.5, remaining))

    def latest_position_event(
        self,
        pair_index: int,
        *,
        present: bool,
        since: float,
        position_index: int | None = None,
    ) -> dict[str, Any] | None:
        event_name = "registerTrade" if present else "unregisterTrade"
        with self._condition:
            return self._find_event(event_name, pair_index, since, position_index=position_index)

    def _find_event(
        self,
        event_name: str,
        pair_index: int,
        since: float,
        *,
        position_index: int | None = None,
    ) -> dict[str, Any] | None:
        for event in reversed(self._events):
            if event["receivedAt"] < since:
                continue
            if event["name"] != event_name:
                continue
            position = event.get("position") or {}
            trade = position.get("trade") or {}
            if str(trade.get("user", "")).lower() != self.owner:
                continue
            raw_pair_index = trade.get("pairIndex")
            raw_position_index = trade.get("index")
            pair_matches = raw_pair_index is not None and int(raw_pair_index) == pair_index
            index_matches = (
                position_index is not None
                and raw_position_index is not None
                and int(raw_position_index) == position_index
            )
            if not pair_matches and not index_matches:
                continue
            return event
        return None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with connect(
                    ARBITRUM_BACKEND_WS,
                    open_timeout=10,
                    close_timeout=2,
                    ping_interval=None,
                    max_size=None,
                ) as websocket:
                    self._last_error = None
                    while not self._stop.is_set():
                        try:
                            raw = websocket.recv(timeout=1)
                        except TimeoutError:
                            continue
                        self._handle_raw(raw)
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                LOGGER.warning("gTrade backend event stream failed: %s", exc)
                self._stop.wait(0.75)

    def _handle_raw(self, raw: str | bytes) -> None:
        received_at = time.time()
        self._max_raw_bytes = max(self._max_raw_bytes, len(raw))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return
        name = str(payload.get("name") or "")
        value = payload.get("value")
        self._last_message_at = received_at
        self._last_message_name = name
        self._message_count += 1
        if name == "currentBlock":
            try:
                self._current_block = int(value)
            except Exception:
                pass
            return
        if name not in {"registerTrade", "unregisterTrade", "updateTrade", "updatePositionSize", "updateLeverage"}:
            return
        position = _find_trade_container(value)
        if not position:
            return
        trade = position.get("trade") or {}
        if str(trade.get("user", "")).lower() != self.owner:
            return
        event = {
            "name": name,
            "receivedAt": received_at,
            "currentBlock": self._current_block,
            "position": position,
            "raw": payload,
        }
        write_latency_event(
            "gains_backend_ws_event_seen",
            {
                "name": name,
                "owner": self.owner,
                "pairIndex": _safe_int(trade.get("pairIndex")),
                "tradeIndex": _safe_int(trade.get("index")),
                "currentBlock": self._current_block,
                "rawBytes": len(raw),
                "receivedAt": received_at,
            },
        )
        with self._condition:
            self._events.append(event)
            self._matched_event_count += 1
            self._condition.notify_all()


def _find_trade_container(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        direct = _direct_trade(value)
        if direct:
            return direct
        trade = value.get("trade")
        if isinstance(trade, dict) and "user" in trade and "pairIndex" in trade:
            return value
        for key in ("value", "data", "args", "payload", "tradeContainer"):
            found = _find_trade_container(value.get(key))
            if found:
                return found
        for nested in value.values():
            found = _find_trade_container(nested)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_trade_container(item)
            if found:
                return found
    return None


def _direct_trade(value: dict[str, Any]) -> dict[str, Any] | None:
    user = _first_present(value, ("user", "trader", "owner"))
    pair_index = _first_present(value, ("pairIndex", "pair_index"))
    position_index = _first_present(value, ("index", "tradeIndex", "trade_index"))
    if user is None or (pair_index is None and position_index is None):
        return None
    trade = dict(value)
    trade["user"] = user
    if pair_index is not None:
        trade["pairIndex"] = pair_index
    if position_index is not None:
        trade["index"] = position_index
    return {"trade": trade, "raw": value}


def _first_present(value: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
