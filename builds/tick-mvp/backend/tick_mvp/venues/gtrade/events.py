from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Any, Callable

from websockets.sync.client import connect

from tick_mvp.venues.gtrade.onchain_events import GTradeOnchainEventStream


LOGGER = logging.getLogger("tick.gtrade.events")
POSITION_EVENT_NAMES = {"registerTrade", "unregisterTrade"}
MAX_EVENT_BYTES = 32 * 1024 * 1024


class GTradeEventStream:
    """Process-wide cache of normalized Gains position events."""

    def __init__(
        self,
        backend_url: str,
        *,
        arb_wss_url: str = "",
        diamond_address: str = "",
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._backend_url = backend_url
        self._events: deque[dict[str, Any]] = deque(maxlen=2048)
        self._tracked_owners: set[str] = set()
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._backend_thread: threading.Thread | None = None
        self._backend_connected = False
        self._backend_last_message_at = 0.0
        self._backend_last_error: str | None = None
        self._on_event = on_event
        self._onchain = GTradeOnchainEventStream(
            arb_wss_url,
            diamond_address,
            self._store_event,
        )

    def start(self) -> None:
        self._stop.clear()
        if not self._backend_thread or not self._backend_thread.is_alive():
            self._backend_thread = threading.Thread(target=self._run_backend, name="gtrade-events", daemon=True)
            self._backend_thread.start()
        self._onchain.start()

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._backend_thread:
            self._backend_thread.join(timeout=2)
        self._onchain.stop()

    def health(self) -> dict[str, Any]:
        return {
            "running": bool(self._backend_thread and self._backend_thread.is_alive()),
            "backend": {
                "connected": self._backend_connected,
                "lastMessageAt": self._backend_last_message_at or None,
                "lastError": self._backend_last_error,
            },
            "onchain": self._onchain.health(),
            "cachedEvents": len(self._events),
            "trackedOwners": len(self._tracked_owners),
        }

    def track_owner(self, owner: str) -> None:
        with self._condition:
            self._tracked_owners.add(owner.lower())

    def wait_for_position_event(
        self,
        *,
        owner: str,
        pair_index: int,
        present: bool,
        since: float,
        timeout_seconds: float,
        position_index: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        deadline = time.monotonic() + timeout_seconds
        owner = owner.lower()
        self.track_owner(owner)
        with self._condition:
            while not self._stop.is_set():
                event = self._find(
                    present=present,
                    owner=owner,
                    pair_index=pair_index,
                    position_index=position_index,
                    since=since,
                )
                if event is not None:
                    return {
                        "source": event["source"],
                        "position": event["position"] if present else None,
                        "event": event,
                        "elapsedMs": _elapsed_ms(started),
                        "targetPresent": present,
                        "observedPresent": present,
                        "timedOut": False,
                    }
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=min(0.25, remaining))
        return {
            "source": "gtrade_event_stream",
            "position": None,
            "event": None,
            "elapsedMs": _elapsed_ms(started),
            "targetPresent": present,
            "observedPresent": None,
            "timedOut": True,
        }

    def _find(
        self,
        *,
        present: bool,
        owner: str,
        pair_index: int,
        position_index: int | None,
        since: float,
    ) -> dict[str, Any] | None:
        for event in reversed(self._events):
            if event["receivedAt"] < since or bool(event["present"]) != present:
                continue
            trade = event["position"]["trade"]
            if str(trade.get("user", "")).lower() != owner:
                continue
            raw_pair = _int_or_none(trade.get("pairIndex"))
            raw_index = _int_or_none(trade.get("index"))
            if raw_pair == pair_index or (position_index is not None and raw_index == position_index):
                return event
        return None

    def _run_backend(self) -> None:
        while not self._stop.is_set():
            try:
                with connect(
                    self._backend_url,
                    open_timeout=10,
                    close_timeout=2,
                    max_size=MAX_EVENT_BYTES,
                ) as websocket:
                    self._backend_connected = True
                    self._backend_last_error = None
                    while not self._stop.is_set():
                        try:
                            raw = websocket.recv(timeout=1)
                        except TimeoutError:
                            continue
                        self._handle_raw(raw)
            except Exception as exc:
                self._backend_connected = False
                self._backend_last_error = f"{type(exc).__name__}: {exc}"
                LOGGER.warning("Gains event stream disconnected: %s", exc)
                self._stop.wait(0.75)
        self._backend_connected = False

    def _handle_raw(self, raw: str | bytes) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return
        self._backend_last_message_at = time.time()
        name = str(payload.get("name") or "")
        if name not in POSITION_EVENT_NAMES:
            return
        position = _find_trade_container(payload.get("value"))
        if position is None:
            return
        owner = str(position["trade"].get("user") or "").lower()
        with self._condition:
            if owner not in self._tracked_owners:
                return
        self._store_event(
            {
                "name": name,
                "source": "gains_backend_ws",
                "present": name == "registerTrade",
                "receivedAt": self._backend_last_message_at,
                "position": position,
            }
        )

    def _store_event(self, event: dict[str, Any]) -> None:
        position = event.get("position") or {}
        trade = position.get("trade") or {}
        owner = str(trade.get("user") or "").lower()
        with self._condition:
            if owner not in self._tracked_owners:
                return
            self._events.append(event)
            self._condition.notify_all()
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:
                LOGGER.exception("gTrade event subscriber failed")


def _find_trade_container(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        trade = value.get("trade")
        if isinstance(trade, dict) and trade.get("user") is not None:
            return value
        if value.get("user") is not None and value.get("index") is not None:
            return {"trade": value}
        for nested in value.values():
            found = _find_trade_container(nested)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_trade_container(item)
            if found is not None:
                return found
    return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
