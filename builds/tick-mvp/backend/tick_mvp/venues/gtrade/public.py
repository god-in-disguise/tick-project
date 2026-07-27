from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal
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


class GTradePublicClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()
        self._pairs_by_name: dict[str, GTradePair] = {}
        self._pairs_expires_at = 0.0
        self._charts_payload: dict[str, Any] | None = None
        self._charts_expires_at = 0.0
        self._prices = GTradePriceStream(settings.gtrade_pricing_ws_url)

    def start(self) -> None:
        self._prices.start()
        try:
            self._ensure_pairs()
        except Exception as exc:
            LOGGER.warning("Could not warm gTrade market metadata: %s", exc)

    def stop(self) -> None:
        self._prices.stop()
        self._session.close()

    def health(self) -> dict[str, Any]:
        return {"prices": self._prices.health()}

    def pair(self, pair_name: str) -> GTradePair:
        normalized = normalize_pair(pair_name)
        self._ensure_pairs()
        pair = self._pairs_by_name.get(normalized)
        if pair is None:
            raise GTradeError(f"gTrade pair not found: {pair_name}")
        return pair

    def pairs(self) -> dict[str, GTradePair]:
        self._ensure_pairs()
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

    def _ensure_pairs(self) -> None:
        now = time.time()
        if self._pairs_by_name and self._pairs_expires_at > now:
            return
        payload = _get_json(self._session, f"{self._settings.gtrade_backend_url}/trading-variables")
        rows = _build_pairs(payload)
        by_name = {row.pair: row for row in rows}
        by_index = {row.pair_index: row for row in rows}
        for index in WATCHLIST_INDEXES:
            if index in by_index:
                by_name.setdefault(by_index[index].pair, by_index[index])
        self._pairs_by_name = by_name
        self._pairs_expires_at = now + self._settings.gtrade_pairs_ttl_seconds

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
    if pair.raw_symbol.endswith("DEGEN") and pair.max_leverage >= Decimal("500"):
        return Decimal("500")
    return min(requested, pair.max_leverage)


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
