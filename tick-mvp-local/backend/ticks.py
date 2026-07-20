from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Iterable

from .connectors.base import VenueConnector


LOGGER = logging.getLogger("tick.ticks")


class TickService:
    """Samples one venue-wide price response and serves every phone chart from memory."""

    def __init__(
        self,
        connector: VenueConnector,
        pairs: Iterable[str],
        *,
        interval_seconds: float = 0.4,
        max_points: int = 1800,
    ):
        self.connector = connector
        self.pairs = tuple(dict.fromkeys(pair.upper() for pair in pairs))
        self.interval_seconds = interval_seconds
        self._ticks: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=max_points))
        self._latest: dict[str, dict[str, Any]] = {}
        self._sequence = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success_at = 0.0
        self._last_error: str | None = None
        self._source = "starting"
        self._message_count = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tick-price-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(self, pair: str, since: int = 0) -> dict[str, Any]:
        pair = pair.upper().replace("/", "-")
        with self._lock:
            points = [dict(item) for item in self._ticks.get(pair, ()) if int(item["sequence"]) > since]
            latest = dict(self._latest[pair]) if pair in self._latest else None
            sequence = int(latest["sequence"]) if latest else since
            last_success_at = self._last_success_at
            error = self._last_error
        now = time.time()
        return {
            "venue": self.connector.name,
            "pair": pair,
            "sequence": sequence,
            "timestamp": now,
            "ticks": points,
            "latest": latest,
            "stale": not last_success_at or now - last_success_at > 2.5,
            "lastSuccessAt": last_success_at or None,
            "error": error,
        }

    def recent(self, pair: str, seconds: float = 60) -> list[dict[str, Any]]:
        cutoff = time.time() - seconds
        pair = pair.upper().replace("/", "-")
        with self._lock:
            return [dict(item) for item in self._ticks.get(pair, ()) if float(item["time"]) >= cutoff]

    def health(self) -> dict[str, Any]:
        with self._lock:
            last_success_at = self._last_success_at
            error = self._last_error
            pair_count = len(self._latest)
            source = self._source
            message_count = self._message_count
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "lastSuccessAt": last_success_at or None,
            "stale": not last_success_at or time.time() - last_success_at > 2.5,
            "pairCount": pair_count,
            "source": source,
            "messageCount": message_count,
            "error": error,
        }

    def _run(self) -> None:
        stream = getattr(self.connector, "stream_prices", None)
        if callable(stream):
            try:
                with self._lock:
                    self._source = "websocket"
                for prices in stream(self.pairs, self._stop):
                    if self._stop.is_set():
                        return
                    self._record(prices)
                return
            except Exception as exc:
                LOGGER.warning("price stream failed, falling back to polling: %s", exc)
                with self._lock:
                    self._last_error = f"{type(exc).__name__}: {exc}"
                    self._source = "polling-fallback"

        self._run_polling()

    def _run_polling(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._record(self.connector.prices())
            except Exception as exc:
                LOGGER.warning("price sampler failed: %s", exc)
                with self._lock:
                    self._last_error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.05, self.interval_seconds - elapsed))

    def _record(self, prices: dict[str, dict[str, Any]]) -> None:
        sampled_at = time.time()
        with self._lock:
            for pair in self.pairs:
                raw = prices.get(pair)
                if not raw:
                    continue
                self._sequence += 1
                tick = {
                    "sequence": self._sequence,
                    "time": sampled_at,
                    "sourceTime": float(raw.get("timestampSeconds") or sampled_at),
                    "mid": float(raw["mid"]),
                    "bid": float(raw["bid"]),
                    "ask": float(raw["ask"]),
                    "open": bool(raw.get("isMarketOpen", True)),
                }
                previous = self._latest.get(pair)
                if previous:
                    previous_mid = float(previous["mid"])
                    minimum_move = max(abs(tick["mid"]) * 0.00000001, 0.00000001)
                    tick["unchanged"] = abs(previous_mid - tick["mid"]) <= minimum_move
                self._ticks[pair].append(tick)
                self._latest[pair] = tick
            self._last_success_at = sampled_at
            self._last_error = None
            self._message_count += 1
