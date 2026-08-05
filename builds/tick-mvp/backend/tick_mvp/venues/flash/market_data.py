from __future__ import annotations

import threading
import time
from collections import deque
from decimal import Decimal
from typing import Any

from tick_mvp.venues.flash.client import FlashClient
from tick_mvp.venues.flash.constants import MARKETS


FLASH_ROUND_TRIP_FEE_HURDLE_PCT = Decimal("0.04")


class FlashMarketData:
    """Small live tape built only from Flash's Pyth-backed price observations."""

    def __init__(
        self,
        client: FlashClient,
        *,
        market_history: Any | None = None,
        poll_seconds: float = 0.2,
        max_observations: int = 18_000,
    ) -> None:
        self._client = client
        self._market_history = market_history
        self._poll_seconds = poll_seconds
        self._ticks = {
            market: deque(maxlen=max_observations) for market in MARKETS
        }
        self._last_venue_timestamp: dict[str, int] = {}
        self._sequence = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_success_at: float | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._refresh_once()
        self._thread = threading.Thread(
            target=self._run,
            name="flash-market-data",
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
            market_count = sum(bool(rows) for rows in self._ticks.values())
        age_ms = (
            (time.time() - last_success_at) * 1000
            if last_success_at is not None
            else None
        )
        return {
            "status": _feed_status(age_ms),
            "lastSuccessAgeMs": round(age_ms, 1) if age_ms is not None else None,
            "lastError": last_error,
            "markets": market_count,
        }

    def markets(self, *, execution_enabled: bool, limit: int) -> dict[str, Any]:
        rows = []
        for config in MARKETS.values():
            recent = self._recent(config.market, seconds=30)
            latest = recent[-1] if recent else None
            prices = [Decimal(item["price"]) for item in recent]
            move_pct = _range_pct(prices)
            activity_surplus_pct = move_pct - FLASH_ROUND_TRIP_FEE_HURDLE_PCT
            rows.append(
                {
                    "venue": "flash",
                    "market": config.market,
                    "symbol": config.symbol,
                    "name": config.name,
                    "assetClass": config.asset_class,
                    "price": Decimal(latest["price"]) if latest else None,
                    "movePct": _directional_move_pct(prices),
                    "activeTapePct": move_pct,
                    "feeHurdlePct": FLASH_ROUND_TRIP_FEE_HURDLE_PCT,
                    "activitySurplusPct": activity_surplus_pct,
                    "minPositionSizeUsd": config.min_position_size_usd,
                    "minCollateralUsd": config.min_collateral_usd,
                    "minLeverage": Decimal("100") if config.max_leverage >= 500 else Decimal("1"),
                    "maxLeverage": config.max_leverage,
                    "suggestedLeverage": config.max_leverage,
                    "openingAllowed": execution_enabled and config.execution_certified,
                    "feedStatus": _feed_status(_age_ms(latest)),
                    "lastMarketTickAgeMs": _age_ms(latest),
                    "score": max(
                        Decimal(0),
                        move_pct * Decimal(1000)
                        + activity_surplus_pct * Decimal(500),
                    ),
                }
            )
        rows.sort(key=lambda row: Decimal(str(row["score"])), reverse=True)
        return {"venue": "flash", "generatedAt": time.time(), "markets": rows[:limit]}

    def chart(self, market: str, *, window_seconds: int) -> dict[str, Any]:
        ticks = self._recent(market, seconds=window_seconds)
        latest = ticks[-1] if ticks else None
        now = time.time()
        return {
            "venue": "flash",
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
        with self._lock:
            all_ticks = list(self._ticks[market])
        latest = all_ticks[-1] if all_ticks else None
        ticks = [item for item in all_ticks if int(item["sequence"]) > since]
        return {
            "venue": "flash",
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
            payload = self._client.prices()
            received_at = time.time()
            observations = []
            with self._lock:
                for config in MARKETS.values():
                    row = payload.get(config.symbol)
                    if not isinstance(row, dict):
                        continue
                    venue_timestamp = int(row.get("timestampUs") or 0)
                    if venue_timestamp <= self._last_venue_timestamp.get(config.market, 0):
                        continue
                    price = _price(row)
                    self._sequence += 1
                    observation = {
                        "venue": "flash",
                        "market": config.market,
                        "sequence": self._sequence,
                        "venueTs": venue_timestamp / 1_000_000,
                        "receivedAt": received_at,
                        "price": str(price),
                        "source": "flash_pyth_lazer",
                    }
                    self._ticks[config.market].append(observation)
                    self._last_venue_timestamp[config.market] = venue_timestamp
                    observations.append(observation)
            with self._lock:
                self._last_success_at = received_at
                self._last_error = None
            if self._market_history is not None and observations:
                self._market_history.record(observations)
        except Exception as exc:
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"

    def _recent(self, market: str, *, seconds: int) -> list[dict[str, Any]]:
        if market not in self._ticks:
            raise ValueError(f"unsupported Flash market: {market}")
        cutoff = time.time() - seconds
        with self._lock:
            return [item for item in self._ticks[market] if item["receivedAt"] >= cutoff]


def _price(row: dict[str, Any]) -> Decimal:
    return Decimal(str(row["price"])) * (Decimal(10) ** int(row["exponent"]))


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


def _observation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": int(item["sequence"]),
        "venueTs": float(item["venueTs"]),
        "receivedTs": float(item["receivedAt"]),
        "price": str(item["price"]),
        "unchanged": False,
    }
