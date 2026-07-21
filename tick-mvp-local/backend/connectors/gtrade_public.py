from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Iterator

import requests
from websockets.sync.client import connect

from .base import ConnectorError
from .gtrade_constants import (
    ARBITRUM_BACKEND,
    COMMODITY_SYMBOLS,
    DEFAULT_PAIR,
    DISPLAY_NAMES,
    FX_PAIR_PREFIXES,
    PRICING_REST,
    PRICING_WS,
    WATCHLIST_INDEXES,
)


LOGGER = logging.getLogger("tick.gtrade.public")


class GTradeError(ConnectorError):
    pass


@dataclass(frozen=True)
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


class GTradePublicClient:
    def __init__(self) -> None:
        self.feed_pairs = tuple(_normalize_known(pair) for pair in _fallback_feed_pairs())
        self._lock = threading.RLock()
        self._pairs_by_name: dict[str, GTradePair] = {}
        self._pairs_by_index: dict[int, GTradePair] = {}
        self._pairs_expires_at = 0.0
        self._latest: dict[str, dict[str, Any]] = {}
        self._history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=1800))
        self._charts_cache: dict[str, Any] = {"expires": 0.0, "data": None}

    def pair(self, pair_name: str) -> GTradePair:
        normalized = normalize_pair(pair_name)
        self._ensure_pairs()
        pair = self._pairs_by_name.get(normalized)
        if not pair:
            raise GTradeError(f"gTrade pair not found: {pair_name}")
        return pair

    def pairs(self) -> dict[str, GTradePair]:
        self._ensure_pairs()
        return dict(self._pairs_by_name)

    def prices(self, pairs: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
        selected = tuple(normalize_pair(pair) for pair in (pairs or self.feed_pairs))
        now = time.time()
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            for pair in selected:
                value = self._latest.get(pair)
                if value and now - float(value.get("_receivedAt", 0)) < 2.5:
                    out[pair] = _clean_price(value)
            if len(out) == len(selected):
                return out

        charts = self._charts()
        rows = self.pairs()
        closes = charts.get("closes") or []
        for pair_name in selected:
            if pair_name in out:
                continue
            row = rows.get(pair_name)
            if not row or row.pair_index >= len(closes) or closes[row.pair_index] is None:
                continue
            out[pair_name] = self._price_from_mid(row, Decimal(str(closes[row.pair_index])), charts.get("time"))
        return out

    def price(self, pair_name: str) -> dict[str, Any]:
        pair_name = normalize_pair(pair_name)
        prices = self.prices((pair_name,))
        price = prices.get(pair_name)
        if not price:
            raise GTradeError(f"price not found: {pair_name}")
        return {
            "pair": pair_name,
            "timestamp": int(time.time()),
            "price": {
                "mid": price["mid"],
                "bid": price["bid"],
                "ask": price["ask"],
                "open": price["isMarketOpen"],
            },
        }

    def markets(self, limit: int = 10) -> dict[str, Any]:
        pairs = self.pairs()
        charts = self._charts()
        prices = self.prices(self.feed_pairs)
        summaries: list[dict[str, Any]] = []
        for pair_name in self.feed_pairs:
            row = pairs.get(pair_name)
            live = prices.get(pair_name)
            if not row or not live or not live.get("isMarketOpen", True):
                continue
            summary = self._market_summary(row, charts, live)
            if summary:
                summaries.append(summary)
        summaries.sort(key=lambda item: float(item["score"]), reverse=True)
        return {
            "timestamp": int(time.time()),
            "universe": list(self.feed_pairs),
            "markets": summaries[:limit],
        }

    def chart(self, pair_name: str = DEFAULT_PAIR, minutes: int = 20) -> dict[str, Any]:
        pair_name = normalize_pair(pair_name)
        row = self.pair(pair_name)
        charts = self._charts()
        points = self._chart_points(row, charts)
        return {
            "pair": pair_name,
            "resolution": "live",
            "candles": [],
            "points": points[-420:],
        }

    def stream_prices(
        self,
        pairs: Iterable[str],
        stop_event: threading.Event,
    ) -> Iterator[dict[str, dict[str, Any]]]:
        selected = {normalize_pair(pair) for pair in pairs}
        self._ensure_pairs()
        seed = self.prices(selected)
        if seed:
            self._record(seed)
            yield seed

        index_to_pair = {
            row.pair_index: row
            for row in self.pairs().values()
            if row.pair in selected
        }
        while not stop_event.is_set():
            try:
                with connect(PRICING_WS, open_timeout=10, close_timeout=2, ping_interval=None) as websocket:
                    while not stop_event.is_set():
                        try:
                            raw = websocket.recv(timeout=1)
                        except TimeoutError:
                            continue
                        payload = json.loads(raw)
                        if not isinstance(payload, list) or len(payload) < 2:
                            continue
                        out: dict[str, dict[str, Any]] = {}
                        for index in range(0, len(payload) - 1, 2):
                            pair_index = int(payload[index])
                            row = index_to_pair.get(pair_index)
                            if not row:
                                continue
                            out[row.pair] = self._price_from_mid(row, Decimal(str(payload[index + 1])), time.time() * 1000)
                        if out:
                            self._record(out)
                            yield out
            except Exception as exc:
                LOGGER.warning("gTrade price websocket failed: %s", exc)
                stop_event.wait(0.75)

    def _market_summary(self, row: GTradePair, charts: dict[str, Any], live: dict[str, Any]) -> dict[str, Any] | None:
        opens = charts.get("opens") or []
        highs = charts.get("highs") or []
        lows = charts.get("lows") or []
        closes = charts.get("closes") or []
        index = row.pair_index
        if index >= len(closes) or closes[index] is None:
            return None
        open_value = float(opens[index] if index < len(opens) and opens[index] is not None else closes[index])
        high = float(highs[index] if index < len(highs) and highs[index] is not None else closes[index])
        low = float(lows[index] if index < len(lows) and lows[index] is not None else closes[index])
        mid = float(live["mid"])
        move_pct = _pct_change(mid, open_value)
        range_pct = ((high - low) / mid) * 100 if mid else 0.0
        with self._lock:
            recent = list(self._history.get(row.pair, ()))[-180:]
        step_pct = _avg_step_pct(recent)
        active_tape_pct = max(abs(move_pct), range_pct, step_pct * 10)
        leverage_for_cost = min(float(row.max_leverage), 500.0)
        fee_hurdle_pct = float((row.open_fee_pct * Decimal("2")) / Decimal(100))
        activity_surplus_pct = active_tape_pct - fee_hurdle_pct
        fee_coverage = active_tape_pct / fee_hurdle_pct if fee_hurdle_pct > 0 else 0.0
        tradability = max(0.0, min(100.0, active_tape_pct * 90.0 + (fee_coverage - 0.7) * 32.0 + step_pct * 150.0))
        score = active_tape_pct * 120.0 + tradability * 5.0 + min(leverage_for_cost, 500.0) * 0.08
        cooling = active_tape_pct < max(0.01, fee_hurdle_pct * 0.35)
        return {
            "pair": row.pair,
            "symbol": row.symbol,
            "name": row.name,
            "assetClass": row.asset_class,
            "feedLabel": "Hot tape" if activity_surplus_pct > fee_hurdle_pct else "Cost covered" if activity_surplus_pct > 0 else "Live tape",
            "price": mid,
            "move": move_pct,
            "sessionMove": move_pct,
            "spanPct": range_pct,
            "range3Pct": range_pct,
            "range5Pct": range_pct,
            "latestRangePct": range_pct,
            "activeTapePct": active_tape_pct,
            "avgStepPct": step_pct,
            "feeHurdlePct": fee_hurdle_pct,
            "activitySurplusPct": activity_surplus_pct,
            "feeCoverage": fee_coverage,
            "tradability": tradability,
            "score": score * (0.55 if cooling else 1.0),
            "cooling": cooling,
            "maxLeverage": float(row.max_leverage),
            "suggestedLeverage": _suggested_leverage(row, active_tape_pct),
            "open": bool(live.get("isMarketOpen", True)),
            "points": self._chart_points(row, charts),
        }

    def _chart_points(self, row: GTradePair, charts: dict[str, Any]) -> list[float]:
        with self._lock:
            live = _compact_repeats(list(self._history.get(row.pair, ())))
        if len(live) >= 8:
            return live[-420:]

        opens = charts.get("opens") or []
        closes = charts.get("closes") or []
        index = row.pair_index
        close = float(closes[index]) if index < len(closes) and closes[index] is not None else 1.0
        open_value = float(opens[index]) if index < len(opens) and opens[index] is not None else close
        seed = [open_value, close]
        return [*seed, *live][-420:] if live else seed

    def _price_from_mid(self, row: GTradePair, mid: Decimal, timestamp_ms: Any) -> dict[str, Any]:
        half_spread = row.spread_pct / Decimal(200)
        return {
            "mid": float(mid),
            "bid": float(mid * (Decimal(1) - half_spread)),
            "ask": float(mid * (Decimal(1) + half_spread)),
            "timestampSeconds": float(Decimal(str(timestamp_ms or time.time() * 1000)) / Decimal(1000)),
            "isMarketOpen": True,
            "_receivedAt": time.time(),
        }

    def _record(self, prices: dict[str, dict[str, Any]]) -> None:
        with self._lock:
            for pair, price in prices.items():
                clean = _clean_price(price)
                self._latest[pair] = {**clean, "_receivedAt": time.time()}
                mid = float(clean["mid"])
                history = self._history[pair]
                if not history or abs(history[-1] - mid) > max(abs(mid) * 0.00000001, 0.00000001):
                    history.append(mid)

    def _ensure_pairs(self) -> None:
        now = time.time()
        with self._lock:
            if self._pairs_by_name and self._pairs_expires_at > now:
                return
        payload = _get_json(f"{ARBITRUM_BACKEND}/trading-variables")
        pairs = _build_pairs(payload)
        by_name = {row.pair: row for row in pairs}
        by_index = {row.pair_index: row for row in pairs}
        feed = tuple(by_index[index].pair for index in WATCHLIST_INDEXES if index in by_index)
        with self._lock:
            self._pairs_by_name = by_name
            self._pairs_by_index = by_index
            self.feed_pairs = feed or self.feed_pairs
            self._pairs_expires_at = now + 300

    def _charts(self) -> dict[str, Any]:
        now = time.time()
        cached = self._charts_cache.get("data")
        if cached is not None and float(self._charts_cache.get("expires", 0)) > now:
            return cached
        payload = _get_json(f"{PRICING_REST}/charts")
        if not isinstance(payload, dict):
            raise GTradeError("gTrade charts returned non-object JSON")
        self._charts_cache["data"] = payload
        self._charts_cache["expires"] = now + 0.25
        return payload


def normalize_pair(pair_name: str) -> str:
    return pair_name.upper().replace("/", "-")


def _normalize_known(pair: str) -> str:
    return pair.upper().replace("/", "-")


def _fallback_feed_pairs() -> tuple[str, ...]:
    return (
        "BTCDEGEN-USD",
        "ETHDEGEN-USD",
        "SOLDEGEN-USD",
        "BNBDEGEN-USD",
        "HYPEDEGEN-USD",
        "ZECDEGEN-USD",
        "BTC-USD",
        "ETH-USD",
        "SOL-USD",
        "XAU-USD",
    )


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


def _pct_change(current: float, previous: float) -> float:
    return ((current - previous) / previous) * 100 if previous else 0.0


def _avg_step_pct(values: list[float]) -> float:
    steps = [abs(values[i] - values[i - 1]) / values[i - 1] * 100 for i in range(1, len(values)) if values[i - 1]]
    return sum(steps) / len(steps) if steps else 0.0


def _compact_repeats(values: list[float]) -> list[float]:
    out: list[float] = []
    for value in values:
        if not value:
            continue
        minimum_move = max(abs(value) * 0.00000001, 0.00000001)
        if not out or abs(out[-1] - value) > minimum_move:
            out.append(value)
    return out


def gtrade_execution_leverage(pair: GTradePair, requested: Decimal) -> Decimal:
    if _is_degen_pair(pair):
        return Decimal("500")
    return min(requested, pair.max_leverage)


def _is_degen_pair(pair: GTradePair) -> bool:
    return pair.raw_symbol.endswith("DEGEN") and pair.max_leverage >= Decimal("500")


def _suggested_leverage(pair: GTradePair, active_tape_pct: float) -> float:
    max_leverage = pair.max_leverage
    if _is_degen_pair(pair):
        return 500.0
    if max_leverage >= Decimal(500) and active_tape_pct < 0.08:
        return 500.0
    if max_leverage >= Decimal(250):
        return 250.0
    if max_leverage >= Decimal(100):
        return 100.0
    if max_leverage >= Decimal(50):
        return 50.0
    return 25.0


def _clean_price(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "mid": float(value["mid"]),
        "bid": float(value["bid"]),
        "ask": float(value["ask"]),
        "timestampSeconds": float(value.get("timestampSeconds") or time.time()),
        "isMarketOpen": bool(value.get("isMarketOpen", True)),
    }


def _get_json(url: str) -> Any:
    last: Exception | None = None
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=25, headers={"user-agent": "tick-gtrade-mvp/0.1"})
            if response.status_code not in {429, 502, 503, 504}:
                response.raise_for_status()
                return response.json()
            last = requests.HTTPError(f"{response.status_code} retryable response", response=response)
        except requests.RequestException as exc:
            last = exc
        time.sleep(0.5 * (attempt + 1))
    raise GTradeError(f"GET {url} failed: {last}") from last
