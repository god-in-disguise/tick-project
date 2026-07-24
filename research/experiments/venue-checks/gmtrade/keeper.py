from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

import requests

from .config import (
    BTC_INDEX_TOKEN,
    BTC_USDC_MARKET,
    DEFAULT_STORE,
    KEEPER_GRAPHQL_URL,
)


BTC_PRICE_SCALE = Decimal(10) ** 12
MARKET_QUERY = """
query KeeperMarketData(
  $store: StringPubkey!
  $marketTokens: [StringPubkey!]
  $pubkeys: [StringPubkey!]
) {
  markets(store: $store, marketTokens: $marketTokens) {
    marketToken
    meta { indexToken { pubkey } }
  }
  tokens(pubkeys: $pubkeys) {
    pubkey
    price { min max ts isOpen }
  }
}
"""


@dataclass(frozen=True)
class OraclePrice:
    minimum: Decimal
    maximum: Decimal
    timestamp: int
    is_open: bool

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.timestamp)


def fetch_btc_oracle_price(timeout_seconds: float = 15) -> OraclePrice:
    response = requests.post(
        KEEPER_GRAPHQL_URL,
        json={
            "query": MARKET_QUERY,
            "variables": {
                "store": DEFAULT_STORE,
                "marketTokens": [BTC_USDC_MARKET],
                "pubkeys": [BTC_INDEX_TOKEN],
            },
        },
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"GMTrade keeper query failed: {payload['errors']}")

    data = payload.get("data") or {}
    markets = data.get("markets") or []
    tokens = data.get("tokens") or []
    if not markets or markets[0].get("marketToken") != BTC_USDC_MARKET:
        raise RuntimeError("GMTrade keeper did not return the configured BTC market")
    token = next(
        (item for item in tokens if item.get("pubkey") == BTC_INDEX_TOKEN),
        None,
    )
    if not token or not token.get("price"):
        raise RuntimeError("GMTrade keeper did not return a BTC oracle price")

    price = token["price"]
    return OraclePrice(
        minimum=Decimal(str(price["min"])) / BTC_PRICE_SCALE,
        maximum=Decimal(str(price["max"])) / BTC_PRICE_SCALE,
        timestamp=int(price["ts"]),
        is_open=bool(price["isOpen"]),
    )


def guarded_prices(
    oracle: OraclePrice,
    *,
    side: str,
    acceptable_bps: Decimal,
    stop_loss_bps: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    ratio = acceptable_bps / Decimal(10_000)
    stop_ratio = stop_loss_bps / Decimal(10_000)
    if side == "long":
        reference = oracle.maximum
        acceptable = reference * (Decimal(1) + ratio)
        stop = reference * (Decimal(1) - stop_ratio)
    elif side == "short":
        reference = oracle.minimum
        acceptable = reference * (Decimal(1) - ratio)
        stop = reference * (Decimal(1) + stop_ratio)
    else:
        raise ValueError("side must be long or short")
    return reference, acceptable, stop
