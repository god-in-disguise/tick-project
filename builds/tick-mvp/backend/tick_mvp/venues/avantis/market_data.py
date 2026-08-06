from __future__ import annotations

import threading
import time
from collections import deque
from decimal import Decimal
from typing import Any

from tick_mvp.venues.avantis.catalog import AvantisPair, market_pair
from tick_mvp.venues.avantis.runtime import AvantisRuntime, PriceObservation


class AvantisMarketData:
    def __init__(
        self,
        runtime: AvantisRuntime,
        *,
        market_history: Any | None = None,
        poll_seconds: float = 0.2,
        max_observations: int = 18_000,
    ) -> None:
        self._runtime = runtime
        self._market_history = market_history
        self._poll_seconds = poll_seconds
        self._max_observations = max_observations
        self._ticks: dict[str, deque[dict[str, Any]]] = {}
        self._last_source_timestamp: dict[str, int] = {}
        self._sequence = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success_at: float | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._runtime.start()
        self._stop.clear()
        self._refresh_once()
        self._thread = threading.Thread(
            target=self._run,
            name="avantis-market-data",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def health(self) -> dict[str, Any]:
        with self._lock:
            last_success_at = self._last_success_at
            last_error = self._last_error
            markets = sum(bool(rows) for rows in self._ticks.values())
        age_ms = (
            (time.time() - last_success_at) * 1000
            if last_success_at is not None
            else None
        )
        return {
            "status": _feed_status(age_ms),
            "lastSuccessAgeMs": round(age_ms, 1) if age_ms is not None else None,
            "lastError": last_error,
            "markets": markets,
        }

    def supports_market(self, market: str) -> bool:
        return market.strip().upper() in self._runtime.catalog()

    def markets(self, *, execution_enabled: bool, limit: int) -> dict[str, Any]:
        catalog = self._runtime.catalog()
        rows = []
        for pair in catalog.values():
            recent = self._recent(pair.market, seconds=30)
            latest = recent[-1] if recent else None
            prices = [Decimal(item["price"]) for item in recent]
            tape_range = _range_pct(prices)
            hurdle = pair.pnl_spread_pct
            surplus = tape_range - hurdle
            rows.append(
                {
                    "venue": "avantis",
                    "market": pair.market,
                    "symbol": pair.symbol,
                    "name": pair.name,
                    "assetClass": pair.asset_class,
                    "price": Decimal(latest["price"]) if latest else None,
                    "movePct": _directional_move_pct(prices),
                    "activeTapePct": tape_range,
                    "feeHurdlePct": hurdle,
                    "activitySurplusPct": surplus,
                    "minPositionSizeUsd": pair.min_notional_usd,
                    "minCollateralUsd": pair.min_collateral_usd,
                    "minLeverage": pair.min_leverage,
                    "maxLeverage": pair.max_leverage,
                    "suggestedLeverage": pair.max_leverage,
                    "openingAllowed": (
                        execution_enabled and pair.market_open and pair.feed_stable
                    ),
                    "feedStatus": _feed_status(_age_ms(latest)),
                    "lastMarketTickAgeMs": _age_ms(latest),
                    "score": max(
                        Decimal(0),
                        tape_range * Decimal(1000) + surplus * Decimal(500),
                    ),
                }
            )
        rows.sort(key=lambda row: Decimal(str(row["score"])), reverse=True)
        return {"venue": "avantis", "generatedAt": time.time(), "markets": rows[:limit]}

    def chart(self, market: str, *, window_seconds: int) -> dict[str, Any]:
        market_pair(self._runtime.catalog(), market)
        ticks = self._recent(market, seconds=window_seconds)
        latest = ticks[-1] if ticks else None
        now = time.time()
        return {
            "venue": "avantis",
            "market": market,
            "requestedWindowSeconds": window_seconds,
            "actualWindowSeconds": (
                max(0.0, ticks[-1]["receivedAt"] - ticks[0]["receivedAt"])
                if len(ticks) > 1
                else 0.0
            ),
            "serverNow": now,
            "partial": len(ticks) < 2 or ticks[0]["receivedAt"] > now - window_seconds + 1,
            "lastSeq": int(latest["sequence"]) if latest else 0,
            "feedStatus": _feed_status(_age_ms(latest)),
            "observations": [_observation(item) for item in ticks],
            "bars": [],
        }

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        market_pair(self._runtime.catalog(), market)
        with self._lock:
            all_ticks = list(self._ticks.get(market, ()))
        latest = all_ticks[-1] if all_ticks else None
        ticks = [item for item in all_ticks if int(item["sequence"]) > since]
        return {
            "venue": "avantis",
            "market": market,
            "sequence": int(latest["sequence"]) if latest else 0,
            "serverNow": time.time(),
            "feedStatus": _feed_status(_age_ms(latest)),
            "lastMarketTickAgeMs": _age_ms(latest),
            "resyncRequired": len(ticks) > 240,
            "observations": [_observation(item) for item in ticks[-240:]],
        }

    def _run(self) -> None:
        while not self._stop.wait(self._poll_seconds):
            self._refresh_once()

    def _refresh_once(self) -> None:
        try:
            catalog = self._runtime.catalog()
            prices = self._runtime.prices()
            observations = []
            with self._lock:
                for pair in catalog.values():
                    price = prices.get(pair.lazer_feed_id)
                    if price is None:
                        continue
                    if price.source_timestamp_ms <= self._last_source_timestamp.get(pair.market, 0):
                        continue
                    self._sequence += 1
                    observation = _tick(pair, price, self._sequence)
                    self._ticks.setdefault(
                        pair.market,
                        deque(maxlen=self._max_observations),
                    ).append(observation)
                    self._last_source_timestamp[pair.market] = price.source_timestamp_ms
                    observations.append(observation)
                self._last_success_at = time.time()
                self._last_error = None
            if self._market_history is not None and observations:
                self._market_history.record(observations)
        except Exception as exc:
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"

    def _recent(self, market: str, *, seconds: int) -> list[dict[str, Any]]:
        cutoff = time.time() - seconds
        with self._lock:
            return [
                item
                for item in self._ticks.get(market, ())
                if item["receivedAt"] >= cutoff
            ]


def _tick(pair: AvantisPair, price: PriceObservation, sequence: int) -> dict[str, Any]:
    return {
        "venue": "avantis",
        "market": pair.market,
        "sequence": sequence,
        "venueTs": price.source_timestamp_ms / 1000,
        "receivedAt": price.received_at,
        "price": str(price.price),
        "source": "avantis_pyth_lazer",
    }


def _observation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": int(item["sequence"]),
        "venueTs": float(item["venueTs"]),
        "receivedTs": float(item["receivedAt"]),
        "price": Decimal(item["price"]),
        "source": item["source"],
    }


def _age_ms(latest: dict[str, Any] | None) -> float | None:
    if latest is None:
        return None
    return max(0.0, (time.time() - float(latest["receivedAt"])) * 1000)


def _feed_status(age_ms: float | None) -> str:
    if age_ms is None:
        return "connecting"
    if age_ms <= 1_500:
        return "live"
    if age_ms <= 5_000:
        return "delayed"
    return "stale"


def _range_pct(prices: list[Decimal]) -> Decimal:
    if not prices or prices[0] == 0:
        return Decimal(0)
    return (max(prices) - min(prices)) / prices[0] * Decimal(100)


def _directional_move_pct(prices: list[Decimal]) -> Decimal:
    if len(prices) < 2 or prices[0] == 0:
        return Decimal(0)
    return (prices[-1] - prices[0]) / prices[0] * Decimal(100)
