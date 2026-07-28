from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal
from threading import RLock
from typing import Any

import requests

from tick_mvp.core.config import Settings
from tick_mvp.venues.base import VenueError
from tick_mvp.venues.aark.constants import AARK_MARKET_PREFIX, DISPLAY_NAMES


LOGGER = logging.getLogger("tick.aark.public")
MAX_OBSERVATIONS_PER_MARKET = 1_600


class AarkError(VenueError):
    pass


@dataclass(frozen=True, slots=True)
class AarkMarket:
    market_id: int
    market: str
    symbol: str
    name: str
    asset_class: str
    index_price: Decimal
    market_price: Decimal
    base_fee_pct: Decimal
    mmr_pct: Decimal
    min_leverage: Decimal
    max_leverage: Decimal
    leverage_steps: tuple[Decimal, ...]
    margin_steps: tuple[Decimal, ...]
    take_profit_cap_pct: Decimal
    initial_margin_cap_usd: Decimal
    opening_allowed: bool
    payload: dict[str, Any]


class AarkPublicClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._lock = RLock()
        self._markets: dict[str, AarkMarket] = {}
        self._markets_by_id: dict[int, AarkMarket] = {}
        self._observations: dict[int, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=MAX_OBSERVATIONS_PER_MARKET)
        )
        self._sequence = 0
        self._last_refresh_at = 0.0
        self._execution_fee = Decimal("0.6")
        self._execution_fee_expires_at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._refresh()
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="aark-market-feed",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._session.close()

    def supports_market(self, market: str) -> bool:
        return normalize_market(market).startswith(AARK_MARKET_PREFIX)

    def market(self, market: str) -> AarkMarket:
        normalized = normalize_market(market)
        self._ensure_markets()
        with self._lock:
            row = self._markets.get(normalized)
        if row is None:
            raise AarkError(f"Aark market not found: {market}")
        return row

    def execution_fee_usd(self) -> Decimal:
        now = time.time()
        with self._lock:
            if self._execution_fee_expires_at > now:
                return self._execution_fee
        payload = self._get_json(
            "/web3/moon-execution-fee",
            params={"chainId": self._settings.arb_chain_id, "mode": self._settings.aark_mode},
        )
        fee = Decimal(str(payload))
        with self._lock:
            self._execution_fee = fee
            self._execution_fee_expires_at = now + self._settings.aark_execution_fee_ttl_seconds
        return fee

    def account_balance_usd(self, address: str) -> Decimal:
        payload = self._get_json(
            f"/futures/account/balance/{address}",
            params={"mode": self._settings.aark_mode},
        )
        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("balance", 0))
        return Decimal(str(payload or 0))

    def positions(self, address: str) -> list[dict[str, Any]]:
        payload = self._get_json(
            "/moon/positions",
            params={
                "user": address,
                "chainId": self._settings.arb_chain_id,
                "mode": self._settings.aark_mode,
            },
        )
        if isinstance(payload, dict):
            payload = payload.get("data", [])
        return [dict(row) for row in payload or [] if isinstance(row, dict)]

    def position(self, moon_index: str | int) -> dict[str, Any] | None:
        payload = self._get_json(
            "/moon/position",
            params={"moonIndex": moon_index, "mode": self._settings.aark_mode},
        )
        if isinstance(payload, dict) and "data" in payload:
            payload = payload["data"]
        return dict(payload) if isinstance(payload, dict) and payload else None

    def trade_history(self, address: str, *, page: int = 1) -> list[dict[str, Any]]:
        payload = self._get_json(
            "/moon/trade-history",
            params={
                "user": address,
                "chainId": self._settings.arb_chain_id,
                "page": page,
                "mode": self._settings.aark_mode,
            },
        )
        if isinstance(payload, dict):
            payload = payload.get("data", payload.get("rows", []))
        return [dict(row) for row in payload or [] if isinstance(row, dict)]

    def markets(self, *, limit: int = 10) -> dict[str, Any]:
        self._ensure_markets()
        now = time.time()
        with self._lock:
            rows = list(self._markets.values())
            observations = {
                row.market_id: list(self._observations[row.market_id])
                for row in rows
            }
        summaries = [
            self._market_summary(row, observations[row.market_id], now)
            for row in rows
        ]
        summaries.sort(key=lambda item: Decimal(str(item["score"])), reverse=True)
        return {
            "venue": "aark",
            "generatedAt": now,
            "markets": summaries[:limit],
        }

    def chart(self, market: str, *, window_seconds: int = 90) -> dict[str, Any]:
        row = self.market(market)
        now = time.time()
        ticks = self._recent(row.market_id, seconds=window_seconds)
        latest = ticks[-1] if ticks else None
        return {
            "venue": "aark",
            "market": row.market,
            "requestedWindowSeconds": window_seconds,
            "actualWindowSeconds": (
                max(0.0, float(ticks[-1]["receivedAt"]) - float(ticks[0]["receivedAt"]))
                if len(ticks) > 1
                else 0.0
            ),
            "serverNow": now,
            "partial": len(ticks) < 2 or float(ticks[0]["receivedAt"]) > now - window_seconds + 1,
            "lastSeq": int(latest["sequence"]) if latest else 0,
            "feedStatus": _feed_status(_age_ms(latest, now)),
            "observations": [_observation(item) for item in ticks],
        }

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        row = self.market(market)
        now = time.time()
        ticks = [
            item
            for item in self._recent(row.market_id, seconds=300)
            if int(item["sequence"]) > since
        ]
        latest = self._recent(row.market_id, seconds=300)
        last = latest[-1] if latest else None
        return {
            "venue": "aark",
            "market": row.market,
            "sequence": int(last["sequence"]) if last else 0,
            "serverNow": now,
            "feedStatus": _feed_status(_age_ms(last, now)),
            "lastMarketTickAgeMs": _age_ms(last, now),
            "resyncRequired": len(ticks) > 240,
            "observations": [_observation(item) for item in ticks[-240:]],
        }

    def _run(self) -> None:
        while not self._stop.wait(self._settings.aark_market_poll_seconds):
            try:
                self._refresh()
            except Exception as exc:
                LOGGER.warning("Aark market refresh failed: %s", exc)
                self._stop.wait(0.75)

    def _ensure_markets(self) -> None:
        with self._lock:
            has_markets = bool(self._markets)
            stale = time.time() - self._last_refresh_at > self._settings.aark_metadata_ttl_seconds
        if not has_markets or stale:
            self._refresh()

    def _refresh(self) -> None:
        payload = self._get_json(
            "/moon/markets",
            params={"chainId": self._settings.arb_chain_id, "mode": self._settings.aark_mode},
        )
        if not isinstance(payload, list):
            raise AarkError("Aark markets returned non-list JSON")
        received_at = time.time()
        parsed = [_parse_market(row) for row in payload if isinstance(row, dict)]
        with self._lock:
            for row in parsed:
                previous = self._observations[row.market_id][-1] if self._observations[row.market_id] else None
                self._sequence += 1
                self._observations[row.market_id].append(
                    {
                        "sequence": self._sequence,
                        "receivedAt": received_at,
                        "price": row.index_price,
                        "unchanged": previous is not None and previous["price"] == row.index_price,
                    }
                )
            self._markets = {row.market: row for row in parsed}
            self._markets_by_id = {row.market_id: row for row in parsed}
            self._last_refresh_at = received_at

    def _recent(self, market_id: int, *, seconds: int) -> list[dict[str, Any]]:
        threshold = time.time() - seconds
        with self._lock:
            return [
                dict(item)
                for item in self._observations[market_id]
                if float(item["receivedAt"]) >= threshold
            ]

    def _market_summary(
        self,
        row: AarkMarket,
        ticks: list[dict[str, Any]],
        now: float,
    ) -> dict[str, Any]:
        recent = [item for item in ticks if float(item["receivedAt"]) >= now - 60]
        prices = [Decimal(str(item["price"])) for item in recent]
        current = row.index_price
        first = prices[0] if prices else current
        move_pct = ((current - first) / first) * Decimal(100) if first else Decimal(0)
        active_pct = _active_tape_pct(prices, current)
        notional_for_hurdle = Decimal("10") * row.min_leverage
        execution_hurdle = (
            self.execution_fee_usd() / notional_for_hurdle * Decimal(100)
            if notional_for_hurdle
            else Decimal(0)
        )
        fee_hurdle = row.base_fee_pct + execution_hurdle
        surplus = active_pct - fee_hurdle
        score = max(Decimal(0), active_pct * Decimal(1000) + surplus * Decimal(500))
        latest = recent[-1] if recent else None
        return {
            "market": row.market,
            "symbol": row.symbol,
            "name": row.name,
            "assetClass": row.asset_class,
            "price": current,
            "movePct": move_pct,
            "activeTapePct": active_pct,
            "feeHurdlePct": fee_hurdle,
            "activitySurplusPct": surplus,
            "minLeverage": row.min_leverage,
            "maxLeverage": row.max_leverage,
            "suggestedLeverage": row.min_leverage,
            "openingAllowed": row.opening_allowed and self._settings.aark_real_execution_enabled,
            "feedStatus": _feed_status(_age_ms(latest, now)),
            "lastMarketTickAgeMs": _age_ms(latest, now),
            "score": score,
        }

    def _get_json(self, path: str, *, params: dict[str, Any]) -> Any:
        url = f"{self._settings.aark_api_url.rstrip('/')}{path}"
        last: Exception | None = None
        for attempt in range(3):
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=12,
                    headers={"user-agent": "tick-mvp/0.2"},
                )
                if response.status_code not in {429, 502, 503, 504}:
                    response.raise_for_status()
                    return response.json()
                last = requests.HTTPError(
                    f"{response.status_code} retryable response",
                    response=response,
                )
            except (requests.RequestException, ValueError) as exc:
                last = exc
            time.sleep(0.25 * (attempt + 1))
        raise AarkError(f"GET {url} failed: {last}") from last


def normalize_market(value: str) -> str:
    normalized = value.upper().replace("/", "-")
    if normalized.startswith(AARK_MARKET_PREFIX):
        return normalized
    symbol = normalized.removesuffix("-USD")
    return f"{AARK_MARKET_PREFIX}{symbol}-USD"


def _parse_market(row: dict[str, Any]) -> AarkMarket:
    symbol = str(row["symbol"]).upper()
    market_type = str(row.get("type") or "").lower()
    asset_class = (
        "STOCK"
        if market_type == "stock"
        else "INDEX"
        if market_type == "index"
        else "COMMODITY"
        if symbol in {"PAXG", "XAU", "XAG"}
        else "CRYPTO"
    )
    return AarkMarket(
        market_id=int(row["marketId"]),
        market=f"{AARK_MARKET_PREFIX}{symbol}-USD",
        symbol=symbol,
        name=DISPLAY_NAMES.get(symbol, symbol.title()),
        asset_class=asset_class,
        index_price=Decimal(str(row["indexPrice"])),
        market_price=Decimal(str(row.get("marketPrice", row["indexPrice"]))),
        base_fee_pct=Decimal(str(row.get("baseFeeRate", "0.01"))),
        mmr_pct=Decimal(str(row.get("mmr", 0))) * Decimal(100),
        min_leverage=Decimal(str(row.get("minLeverage", 500))),
        max_leverage=Decimal(str(row.get("maxLeverage", 1000))),
        leverage_steps=tuple(Decimal(str(value)) for value in row.get("leverageStep") or []),
        margin_steps=tuple(Decimal(str(value)) for value in row.get("marginStep") or []),
        take_profit_cap_pct=Decimal(str(row.get("takeProfitCap", 400))),
        initial_margin_cap_usd=Decimal(str(row.get("initialMarginCap", 0))),
        opening_allowed=bool(row.get("activate", True))
        and bool(row.get("allowance", True))
        and not bool(row.get("isBlocked", False))
        and not bool(row.get("isCircuit", False)),
        payload=dict(row),
    )


def _observation(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "seq": int(item["sequence"]),
        "receivedTs": float(item["receivedAt"]),
        "price": str(item["price"]),
        "unchanged": bool(item.get("unchanged", False)),
    }


def _active_tape_pct(prices: list[Decimal], current: Decimal) -> Decimal:
    if not prices or current <= 0:
        return Decimal(0)
    return ((max(prices) - min(prices)) / current) * Decimal(100)


def _age_ms(item: dict[str, Any] | None, now: float) -> float | None:
    return (now - float(item["receivedAt"])) * 1000 if item else None


def _feed_status(age_ms: float | None) -> str:
    if age_ms is None:
        return "resyncing"
    if age_ms <= 1200:
        return "live"
    if age_ms <= 2500:
        return "delayed"
    if age_ms <= 8000:
        return "stale"
    return "disconnected"

