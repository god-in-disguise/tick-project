from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .connectors.base import VenueConnector
from .ticks import TickService


LOGGER = logging.getLogger("tick.markets")


class MarketService:
    """Caches product ranking away from API request latency."""

    def __init__(self, connector: VenueConnector, ticks: TickService, *, refresh_seconds: float = 8.0):
        self.connector = connector
        self.ticks = ticks
        self.refresh_seconds = refresh_seconds
        self._data: dict[str, Any] | None = None
        self._updated_at = 0.0
        self._error: str | None = None
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tick-market-scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            data = self._data
            updated_at = self._updated_at
            error = self._error
        if data is None:
            data = self._refresh()
            with self._lock:
                self._data = data
                self._updated_at = time.time()
                self._error = None
                updated_at = self._updated_at
                error = None
        return {
            **data,
            "cachedAt": updated_at,
            "stale": not updated_at or time.time() - updated_at > self.refresh_seconds * 3,
            "error": error,
        }

    def find(self, pair: str) -> dict[str, Any] | None:
        normalized = pair.upper().replace("/", "-")
        return next((item for item in self.snapshot().get("markets", []) if item["pair"] == normalized), None)

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                data = self._refresh()
                with self._lock:
                    self._data = data
                    self._updated_at = time.time()
                    self._error = None
            except Exception as exc:
                LOGGER.warning("market scanner failed: %s", exc)
                with self._lock:
                    self._error = f"{type(exc).__name__}: {exc}"
            elapsed = time.monotonic() - started
            self._stop.wait(max(0.1, self.refresh_seconds - elapsed))

    def _refresh(self) -> dict[str, Any]:
        response = self.connector.markets(limit=10)
        markets = [self._with_live_tape(item) for item in response.get("markets", [])]
        markets.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return {**response, "markets": markets}

    def _with_live_tape(self, market: dict[str, Any]) -> dict[str, Any]:
        recent = self.ticks.recent(market["pair"], seconds=60)
        values = [float(item["mid"]) for item in recent if float(item.get("mid") or 0) > 0]
        if len(values) < 3:
            return market

        latest = values[-1]
        recent_30 = values[len(values) // 2 :]
        active_range = ((max(recent_30) - min(recent_30)) / latest) * 100 if latest else 0.0
        active_move = abs((latest - recent_30[0]) / recent_30[0] * 100) if recent_30[0] else 0.0
        active_tape = max(active_range, active_move)
        hurdle = float(market.get("feeHurdlePct") or 0)
        surplus = active_tape - hurdle
        coverage = active_tape / hurdle if hurdle > 0 else 0.0
        tradability = max(0.0, min(100.0, (coverage - 0.7) * 42.0 + active_tape * 80.0))
        cooling = bool(market.get("cooling")) and active_tape < hurdle * 0.5
        score = float(market.get("score") or 0) * 0.35 + tradability * 5.0
        label = "Hot tape" if surplus > hurdle * 0.75 else "Cost covered" if surplus > 0 else "Live tape"
        return {
            **market,
            "price": latest,
            "points": _thin_values(values, 120),
            "activeTapePct": active_tape,
            "activitySurplusPct": surplus,
            "feeCoverage": coverage,
            "tradability": tradability,
            "score": score,
            "cooling": cooling,
            "feedLabel": "Cooling" if cooling else label,
        }


def _thin_values(values: list[float], max_points: int) -> list[float]:
    if len(values) <= max_points:
        return values
    if max_points <= 1:
        return values[-1:]
    step = (len(values) - 1) / (max_points - 1)
    return [values[round(index * step)] for index in range(max_points)]
