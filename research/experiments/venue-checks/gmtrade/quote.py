from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

from .keeper import fetch_btc_oracle_price, guarded_prices


@dataclass(frozen=True)
class QuoteSnapshot:
    side: str
    reference: Decimal
    acceptable: Decimal
    stop: Decimal
    oracle_timestamp: int
    oracle_age_seconds: float
    fetched_monotonic: float


def fetch_fresh_quote(
    *,
    side: str,
    acceptable_bps: Decimal,
    stop_loss_bps: Decimal,
    max_age_seconds: float,
) -> QuoteSnapshot:
    oracle = fetch_btc_oracle_price()
    if not oracle.is_open:
        raise RuntimeError("GMTrade reports BTC as closed")
    if oracle.age_seconds > max_age_seconds:
        raise RuntimeError(f"GMTrade BTC price is {oracle.age_seconds:.1f}s old")
    reference, acceptable, stop = guarded_prices(
        oracle,
        side=side,
        acceptable_bps=acceptable_bps,
        stop_loss_bps=stop_loss_bps,
    )
    return QuoteSnapshot(
        side=side,
        reference=reference,
        acceptable=acceptable,
        stop=stop,
        oracle_timestamp=oracle.timestamp,
        oracle_age_seconds=oracle.age_seconds,
        fetched_monotonic=time.perf_counter(),
    )


def fetch_fresh_close_quote(
    *,
    side: str,
    acceptable_bps: Decimal,
    max_age_seconds: float,
) -> QuoteSnapshot:
    oracle = fetch_btc_oracle_price()
    if not oracle.is_open:
        raise RuntimeError("GMTrade reports BTC as closed")
    if oracle.age_seconds > max_age_seconds:
        raise RuntimeError(f"GMTrade BTC price is {oracle.age_seconds:.1f}s old")
    ratio = acceptable_bps / Decimal(10_000)
    if side == "long":
        reference = oracle.minimum
        acceptable = reference * (Decimal(1) - ratio)
    elif side == "short":
        reference = oracle.maximum
        acceptable = reference * (Decimal(1) + ratio)
    else:
        raise ValueError("side must be long or short")
    return QuoteSnapshot(
        side=side,
        reference=reference,
        acceptable=acceptable,
        stop=acceptable,
        oracle_timestamp=oracle.timestamp,
        oracle_age_seconds=oracle.age_seconds,
        fetched_monotonic=time.perf_counter(),
    )


def quote_drift_bps(before: QuoteSnapshot, after: QuoteSnapshot) -> Decimal:
    if before.reference == 0:
        return Decimal(0)
    return abs((after.reference - before.reference) / before.reference) * Decimal(10_000)
