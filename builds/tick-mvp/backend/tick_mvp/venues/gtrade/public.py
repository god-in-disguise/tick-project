from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from threading import RLock
from typing import Any

import requests

from tick_mvp.core.config import Settings
from tick_mvp.venues.base import VenueError
from tick_mvp.venues.gtrade.constants import (
    COMMODITY_SYMBOLS,
    DISPLAY_NAMES,
    FX_PAIR_PREFIXES,
    WATCHLIST_INDEXES,
)
from tick_mvp.venues.gtrade.price_stream import GTradePriceStream


LOGGER = logging.getLogger("tick.gtrade.public")


class GTradeError(VenueError):
    pass


@dataclass(frozen=True, slots=True)
class GTradePair:
    pair_index: int
    pair: str
    raw_symbol: str
    symbol: str
    name: str
    group: str
    asset_class: str
    max_leverage: Decimal
    open_fee_pct: Decimal
    min_position_usd: Decimal
    min_collateral_usd: Decimal
    spread_pct: Decimal
    liquidation_fee_pct: Decimal = Decimal(0)


class GTradePublicClient:
    def __init__(self, settings: Settings, market_history: Any | None = None) -> None:
        self._settings = settings
        self._market_history = market_history
        self._session = requests.Session()
        self._metadata_session = requests.Session()
        self._pairs_lock = RLock()
        self._pairs_refresh_lock = RLock()
        self._pairs_by_name: dict[str, GTradePair] = {}
        self._pairs_by_index: dict[int, GTradePair] = {}
        self._pairs_expires_at = 0.0
        self._metadata_stop = threading.Event()
        self._metadata_thread: threading.Thread | None = None
        self._charts_payload: dict[str, Any] | None = None
        self._charts_expires_at = 0.0
        self._prices = GTradePriceStream(
            settings.gtrade_pricing_ws_url,
            on_observations=(
                self._record_market_history
                if self._market_history is not None
                else None
            ),
        )

    def start(self) -> None:
        history_start = getattr(self._market_history, "start", None)
        if history_start is not None:
            history_start()
        try:
            self._refresh_pairs()
        except Exception as exc:
            LOGGER.warning("Could not warm gTrade market metadata: %s", exc)
        self._prices.start()
        if not self._metadata_thread or not self._metadata_thread.is_alive():
            self._metadata_stop.clear()
            self._metadata_thread = threading.Thread(
                target=self._run_metadata_warmer,
                name="gtrade-market-metadata",
                daemon=True,
            )
            self._metadata_thread.start()

    def stop(self) -> None:
        self._metadata_stop.set()
        if self._metadata_thread:
            self._metadata_thread.join(timeout=2)
        self._prices.stop()
        history_stop = getattr(self._market_history, "stop", None)
        if history_stop is not None:
            history_stop()
        self._metadata_session.close()
        self._session.close()

    def health(self) -> dict[str, Any]:
        return {"prices": self._prices.health()}

    def pair(self, pair_name: str) -> GTradePair:
        normalized = normalize_pair(pair_name)
        self._ensure_pairs()
        with self._pairs_lock:
            pair = self._pairs_by_name.get(normalized)
        if pair is None:
            raise GTradeError(f"gTrade pair not found: {pair_name}")
        return pair

    def pairs(self) -> dict[str, GTradePair]:
        self._ensure_pairs()
        with self._pairs_lock:
            return dict(self._pairs_by_name)

    def price(self, pair_name: str) -> dict[str, Any]:
        row = self.pair(pair_name)
        live = self._prices.price(row.pair_index)
        if live is not None:
            return {
                **self._price_from_mid(row, live["mid"], live["receivedAt"] * 1000),
                "source": live["source"],
                "ageMs": live["ageMs"],
            }
        charts = self._charts()
        closes = charts.get("closes") or []
        if row.pair_index >= len(closes) or closes[row.pair_index] is None:
            raise GTradeError(f"price not found: {row.pair}")
        mid = Decimal(str(closes[row.pair_index]))
        return {
            **self._price_from_mid(row, mid, charts.get("time")),
            "source": "gtrade_pricing_rest",
        }

    def markets(self, *, limit: int = 10) -> dict[str, Any]:
        self._ensure_pairs()
        with self._pairs_lock:
            by_index = {row.pair_index: row for row in self._pairs_by_name.values()}
        summaries: list[dict[str, Any]] = []
        for pair_index in WATCHLIST_INDEXES:
            row = by_index.get(pair_index)
            if row is None:
                continue
            live = self._prices.price(pair_index)
            if live is None:
                continue
            recent = self._prices.recent(pair_index, seconds=60)
            prices = [Decimal(str(item["price"])) for item in recent]
            current = Decimal(str(live["mid"]))
            first = prices[0] if prices else current
            move_pct = ((current - first) / first) * Decimal(100) if first else Decimal(0)
            active_pct = _active_tape_pct(prices, current)
            fee_hurdle_pct = row.open_fee_pct * Decimal(2)
            surplus_pct = active_pct - fee_hurdle_pct
            score = max(Decimal(0), active_pct * Decimal(1000) + surplus_pct * Decimal(500))
            summaries.append(
                {
                    "market": row.pair,
                    "symbol": row.symbol,
                    "name": row.name,
                    "assetClass": row.asset_class,
                    "price": current,
                    "movePct": move_pct,
                    "activeTapePct": active_pct,
                    "feeHurdlePct": fee_hurdle_pct,
                    "activitySurplusPct": surplus_pct,
                    "minPositionSizeUsd": row.min_position_usd,
                    "minLeverage": _minimum_execution_leverage(row),
                    "maxLeverage": row.max_leverage,
                    "suggestedLeverage": _suggested_leverage(row.max_leverage),
                    "openingAllowed": bool(live.get("isMarketOpen", True)),
                    "feedStatus": _feed_status(live.get("ageMs")),
                    "lastMarketTickAgeMs": live.get("ageMs"),
                    "score": score,
                }
            )
        summaries.sort(key=lambda item: Decimal(str(item["score"])), reverse=True)
        return {
            "venue": "gtrade",
            "generatedAt": time.time(),
            "markets": summaries[:limit],
        }

    def chart(self, pair_name: str, *, window_seconds: int = 90) -> dict[str, Any]:
        row = self.pair(pair_name)
        ticks = self._prices.recent(row.pair_index, seconds=window_seconds)
        latest = ticks[-1] if ticks else self._prices.snapshot(row.pair_index).get("latest")
        now = time.time()
        bars = (
            self._market_history.bars(
                venue="gtrade",
                market=row.pair,
                window_seconds=window_seconds,
            )
            if self._market_history is not None and window_seconds > 300
            else []
        )
        return {
            "venue": "gtrade",
            "market": row.pair,
            "requestedWindowSeconds": window_seconds,
            "actualWindowSeconds": (
                max(0.0, float(ticks[-1]["receivedAt"]) - float(ticks[0]["receivedAt"]))
                if len(ticks) > 1
                else 0.0
            ),
            "serverNow": now,
            "partial": len(ticks) < 2 or float(ticks[0]["receivedAt"]) > now - window_seconds + 1,
            "lastSeq": int(latest["sequence"]) if latest else 0,
            "feedStatus": _feed_status(
                (now - float(latest["receivedAt"])) * 1000 if latest else None
            ),
            "observations": [_observation(item) for item in ticks],
            "bars": bars,
        }

    def tape(self, pair_name: str, *, since: int) -> dict[str, Any]:
        row = self.pair(pair_name)
        snapshot = self._prices.snapshot(row.pair_index, since=since)
        ticks = snapshot["ticks"]
        latest = snapshot["latest"]
        now = time.time()
        age_ms = (now - float(latest["receivedAt"])) * 1000 if latest else None
        return {
            "venue": "gtrade",
            "market": row.pair,
            "sequence": snapshot["sequence"],
            "serverNow": now,
            "feedStatus": _feed_status(age_ms),
            "lastMarketTickAgeMs": age_ms,
            "resyncRequired": len(ticks) > 240,
            "observations": [_observation(item) for item in ticks[-240:]],
        }

    def _ensure_pairs(self) -> None:
        # A stale metadata snapshot is safer than adding a network request to a
        # user's execution gesture. The background warmer refreshes it.
        with self._pairs_lock:
            if self._pairs_by_name:
                return
        self._refresh_pairs()

    def _refresh_pairs(self) -> None:
        with self._pairs_refresh_lock:
            payload = _get_json(
                self._metadata_session,
                f"{self._settings.gtrade_backend_url}/trading-variables",
            )
            rows = _build_pairs(payload)
            by_name = {row.pair: row for row in rows}
            by_index = {row.pair_index: row for row in rows}
            for index in WATCHLIST_INDEXES:
                if index in by_index:
                    by_name.setdefault(by_index[index].pair, by_index[index])
            with self._pairs_lock:
                self._pairs_by_name = by_name
                self._pairs_by_index = by_index
                self._pairs_expires_at = time.time() + self._settings.gtrade_pairs_ttl_seconds

    def _record_market_history(self, observations: list[dict[str, Any]]) -> None:
        with self._pairs_lock:
            by_index = dict(self._pairs_by_index)
        rows = [
            {
                **observation,
                "venue": "gtrade",
                "market": by_index[int(observation["pairIndex"])].pair,
                "source": "gtrade_pricing_ws",
            }
            for observation in observations
            if int(observation["pairIndex"]) in by_index
        ]
        if rows:
            self._market_history.record(rows)

    def _run_metadata_warmer(self) -> None:
        while not self._metadata_stop.is_set():
            with self._pairs_lock:
                expires_at = self._pairs_expires_at
            refresh_ahead = min(30.0, max(5.0, self._settings.gtrade_pairs_ttl_seconds * 0.1))
            delay = max(1.0, expires_at - time.time() - refresh_ahead)
            if self._metadata_stop.wait(delay):
                return
            try:
                self._refresh_pairs()
            except Exception as exc:
                LOGGER.warning("Could not refresh gTrade market metadata: %s", exc)
                self._metadata_stop.wait(5.0)

    def _charts(self) -> dict[str, Any]:
        now = time.time()
        if self._charts_payload is not None and self._charts_expires_at > now:
            return self._charts_payload
        payload = _get_json(self._session, f"{self._settings.gtrade_pricing_url}/charts")
        if not isinstance(payload, dict):
            raise GTradeError("gTrade charts returned non-object JSON")
        self._charts_payload = payload
        self._charts_expires_at = now + self._settings.gtrade_charts_ttl_seconds
        return payload

    @staticmethod
    def _price_from_mid(row: GTradePair, mid: Decimal, timestamp_ms: Any) -> dict[str, Any]:
        half_spread = row.spread_pct / Decimal(200)
        return {
            "mid": mid,
            "bid": mid * (Decimal(1) - half_spread),
            "ask": mid * (Decimal(1) + half_spread),
            "timestampSeconds": Decimal(str(timestamp_ms or time.time() * 1000)) / Decimal(1000),
            "isMarketOpen": True,
        }


def normalize_pair(pair_name: str) -> str:
    return pair_name.upper().replace("/", "-")


def gtrade_execution_leverage(pair: GTradePair, requested: Decimal) -> Decimal:
    minimum = _minimum_execution_leverage(pair)
    if requested < minimum or requested > pair.max_leverage:
        if minimum == pair.max_leverage:
            raise GTradeError(f"{pair.pair} only supports {minimum}x")
        raise GTradeError(
            f"{pair.pair} supports leverage from {minimum}x to {pair.max_leverage}x"
        )
    return requested


def _minimum_execution_leverage(pair: GTradePair) -> Decimal:
    if pair.raw_symbol.endswith("DEGEN") and pair.max_leverage >= Decimal("500"):
        return Decimal("500")
    return Decimal("1")


def _build_pairs(payload: dict[str, Any]) -> list[GTradePair]:
    pairs = payload["pairs"]
    groups = payload["groups"]
    fees = payload["fees"]
    max_leverages = payload["pairInfos"]["maxLeverages"]
    rows: list[GTradePair] = []
    for pair_index, pair in enumerate(pairs):
        group_index = int(pair["groupIndex"])
        fee_index = int(pair["feeIndex"])
        group = groups[group_index]
        fee = fees[fee_index]
        override = int(max_leverages[pair_index]) if pair_index < len(max_leverages) else 0
        max_leverage_raw = override if override else int(group["maxLeverage"])
        max_leverage = Decimal(max_leverage_raw) / Decimal(1000)
        min_position = Decimal(str(fee["minPositionSizeUsd"])) / Decimal(100)
        raw_symbol = str(pair["from"]).upper()
        display_symbol, display_name = DISPLAY_NAMES.get(raw_symbol, (raw_symbol, raw_symbol.title()))
        rows.append(
            GTradePair(
                pair_index=pair_index,
                pair=f"{pair['from']}-{pair['to']}".upper(),
                raw_symbol=raw_symbol,
                symbol=display_symbol,
                name=display_name,
                group=str(group["name"]),
                asset_class=_asset_class(raw_symbol, str(group["name"])),
                max_leverage=max_leverage,
                open_fee_pct=_pct_from_p(fee["totalPositionSizeFeeP"]),
                min_position_usd=min_position,
                min_collateral_usd=min_position / max_leverage if max_leverage else Decimal(0),
                spread_pct=_pct_from_p(pair["spreadP"]),
                liquidation_fee_pct=_pct_from_p(
                    fee.get("totalLiqCollateralFeeP", 0)
                ),
            )
        )
    return rows


def _asset_class(symbol: str, group: str) -> str:
    group_lower = group.lower()
    if "forex" in group_lower or (symbol in FX_PAIR_PREFIXES and symbol not in {"BTC", "ETH", "SOL"}):
        return "FX"
    if symbol in COMMODITY_SYMBOLS or "commodit" in group_lower:
        return "COMMODITY"
    if "indices" in group_lower or "index" in group_lower:
        return "INDEX"
    return "CRYPTO"


def _pct_from_p(value: Any) -> Decimal:
    return (Decimal(str(value)) / Decimal(10**12)) * Decimal(100)


def _get_json(session: requests.Session, url: str) -> Any:
    last: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=25, headers={"user-agent": "tick-mvp/0.1"})
            if response.status_code not in {429, 502, 503, 504}:
                response.raise_for_status()
                return response.json()
            last = requests.HTTPError(f"{response.status_code} retryable response", response=response)
        except requests.RequestException as exc:
            last = exc
        time.sleep(0.5 * (attempt + 1))
    raise GTradeError(f"GET {url} failed: {last}") from last


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
    low = min(prices)
    high = max(prices)
    return ((high - low) / current) * Decimal(100)


def _suggested_leverage(max_leverage: Decimal) -> Decimal:
    for value in (Decimal("500"), Decimal("100"), Decimal("50"), Decimal("25")):
        if max_leverage >= value:
            return value
    return max_leverage


def _feed_status(age_ms: Any) -> str:
    if age_ms is None:
        return "resyncing"
    age = float(age_ms)
    if age <= 1200:
        return "live"
    if age <= 2500:
        return "delayed"
    if age <= 8000:
        return "stale"
    return "disconnected"
