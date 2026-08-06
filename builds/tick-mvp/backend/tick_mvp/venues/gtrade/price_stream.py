from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from decimal import Decimal
from typing import Any, Callable, Iterable

from websockets.sync.client import connect

from tick_mvp.venues.gtrade.constants import WATCHLIST_INDEXES


LOGGER = logging.getLogger("tick.gtrade.prices")
MAX_PRICE_FRAME_BYTES = 8 * 1024 * 1024
PRICE_HISTORY_SECONDS = 65 * 60
MAX_TICKS_PER_MARKET = 30_000


class GTradePriceStream:
    """One live gTrade price connection shared by every user in this process."""

    def __init__(
        self,
        url: str,
        watched_indexes: Iterable[int] = WATCHLIST_INDEXES,
        on_observations: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> None:
        self._url = url
        self._watched_indexes = frozenset(watched_indexes)
        self._on_observations = on_observations
        self._latest: dict[int, tuple[Decimal, float]] = {}
        self._ticks: dict[int, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=MAX_TICKS_PER_MARKET)
        )
        self._sequence = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._last_message_at = 0.0
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gtrade-prices", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def price(self, pair_index: int, *, max_age_seconds: float = 2.5) -> dict[str, Any] | None:
        with self._lock:
            value = self._latest.get(pair_index)
        if value is None:
            return None
        mid, received_at = value
        age = time.time() - received_at
        if age > max_age_seconds:
            return None
        return {
            "mid": mid,
            "receivedAt": received_at,
            "ageMs": round(age * 1000, 1),
            "source": "gtrade_pricing_ws",
        }

    def health(self) -> dict[str, Any]:
        with self._lock:
            market_count = len(self._latest)
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "connected": self._connected,
            "lastMessageAt": self._last_message_at or None,
            "lastError": self._last_error,
            "marketCount": market_count,
        }

    def snapshot(self, pair_index: int, *, since: int = 0) -> dict[str, Any]:
        with self._lock:
            items = [
                dict(item)
                for item in self._ticks.get(pair_index, ())
                if int(item["sequence"]) > since
            ]
            latest = dict(self._ticks[pair_index][-1]) if self._ticks.get(pair_index) else None
        return {
            "sequence": int(latest["sequence"]) if latest else since,
            "ticks": items,
            "latest": latest,
        }

    def recent(self, pair_index: int, *, seconds: float) -> list[dict[str, Any]]:
        cutoff = time.time() - seconds
        with self._lock:
            return [
                dict(item)
                for item in self._ticks.get(pair_index, ())
                if float(item["receivedAt"]) >= cutoff
            ]

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with connect(
                    self._url,
                    open_timeout=10,
                    close_timeout=2,
                    max_size=MAX_PRICE_FRAME_BYTES,
                ) as websocket:
                    self._connected = True
                    self._last_error = None
                    while not self._stop.is_set():
                        try:
                            raw = websocket.recv(timeout=1)
                        except TimeoutError:
                            continue
                        self._handle_raw(raw)
            except Exception as exc:
                self._connected = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                LOGGER.warning("gTrade price stream disconnected: %s", exc)
                self._stop.wait(0.75)
        self._connected = False

    def _handle_raw(self, raw: str | bytes) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, list) or len(payload) < 2:
            return
        received_at = time.time()
        updates: dict[int, tuple[Decimal, float]] = {}
        for offset in range(0, len(payload) - 1, 2):
            try:
                updates[int(payload[offset])] = (Decimal(str(payload[offset + 1])), received_at)
            except (TypeError, ValueError):
                continue
        if not updates:
            return
        observations: list[dict[str, Any]] = []
        with self._lock:
            self._latest.update(updates)
            for pair_index, (mid, observed_at) in updates.items():
                if pair_index not in self._watched_indexes:
                    continue
                ticks = self._ticks[pair_index]
                previous = ticks[-1] if ticks else None
                self._sequence += 1
                observation = {
                    "pairIndex": pair_index,
                    "sequence": self._sequence,
                    "receivedAt": observed_at,
                    "price": mid,
                    "unchanged": bool(previous and previous["price"] == mid),
                }
                ticks.append(observation)
                observations.append(dict(observation))
                cutoff = observed_at - PRICE_HISTORY_SECONDS
                while ticks and float(ticks[0]["receivedAt"]) < cutoff:
                    ticks.popleft()
            self._last_message_at = received_at
        if observations and self._on_observations is not None:
            try:
                self._on_observations(observations)
            except Exception:
                LOGGER.exception("gTrade market-history observer failed")
