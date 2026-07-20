from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Iterator
from decimal import Decimal
from typing import Any

from . import ostium_client as raw
from . import ostium_trading as trading
from .ostium_pricing import estimate_close, estimate_open
from .ostium_stream import stream_prices as receive_prices


class OstiumConnector:
    """Stable TICK adapter over Ostium-specific contract and API code."""

    name = "ostium"
    feed_pairs = tuple(raw.FEED_CANDIDATES)

    def __init__(self) -> None:
        self._price_lock = threading.RLock()
        self._latest_prices: dict[str, dict[str, Any]] = {}
        self._latest_prices_at = 0.0

    def wallet_address(self) -> str:
        return raw._load()[1]

    def account(self) -> dict[str, Any]:
        return raw.positions()

    def positions(self) -> dict[str, Any]:
        return raw.positions()

    def markets(self, limit: int = 10) -> dict[str, Any]:
        return raw.markets(limit=limit)

    def price(self, pair: str) -> dict[str, Any]:
        return raw.pair_price(pair)

    def prices(self) -> dict[str, dict[str, Any]]:
        return raw._prices(fresh=True)

    def stream_prices(
        self,
        pairs: Iterable[str],
        stop_event: threading.Event,
    ) -> Iterator[dict[str, dict[str, Any]]]:
        for prices in receive_prices(pairs, stop_event):
            with self._price_lock:
                self._latest_prices.update(prices)
                self._latest_prices_at = time.monotonic()
            yield prices

    def chart(self, pair: str, minutes: int = 120) -> dict[str, Any]:
        return raw.chart(pair, minutes)

    def estimate_open(self, pair: str, side: str, ticket_usd: Decimal, leverage: Decimal) -> dict[str, Any]:
        live = self._fresh_stream_price(pair)
        return estimate_open(pair, side, ticket_usd, leverage, live=live)

    def open_position(
        self,
        pair: str,
        side: str,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        execution_price = Decimal(str(quote["price"])) if quote and quote.get("price") is not None else None
        return trading.open_trade(
            side,
            float(leverage),
            pair,
            collateral_value=ticket_usd,
            execution_price=execution_price,
            preflighted=quote is not None,
            wait=False,
        )

    def estimate_close(self, pair: str) -> dict[str, Any]:
        return estimate_close(pair)

    def close_position(self, pair: str, position: dict[str, Any] | None = None) -> dict[str, Any]:
        live = self._fresh_stream_price(pair)
        execution_price = None
        if live and position:
            field = "bid" if position.get("side") == "long" else "ask"
            execution_price = Decimal(str(live[field]))
        return trading.close_trade(
            pair,
            position=position,
            execution_price=execution_price,
            preflighted=position is not None and execution_price is not None,
            wait=False,
        )

    def approve(self, amount: Decimal | None = None) -> dict[str, Any]:
        return raw.approve(amount)

    def _fresh_stream_price(self, pair: str) -> dict[str, Any] | None:
        normalized = pair.upper().replace("/", "-")
        with self._price_lock:
            fresh = time.monotonic() - self._latest_prices_at <= 2.5
            return dict(self._latest_prices[normalized]) if fresh and normalized in self._latest_prices else None
