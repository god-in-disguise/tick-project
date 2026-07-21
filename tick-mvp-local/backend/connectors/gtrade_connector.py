from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Iterator
from decimal import Decimal
from typing import Any

from .gtrade_pricing import estimate_close as estimate_gtrade_close
from .gtrade_pricing import estimate_open as estimate_gtrade_open
from .gtrade_public import GTradeError, GTradePublicClient, gtrade_execution_leverage, normalize_pair
from .gtrade_wallet import GTradeWallet


class GTradeConnector:
    """TICK adapter over gTrade/Gains on Arbitrum."""

    name = "gtrade"

    def __init__(self) -> None:
        self.public = GTradePublicClient()
        self.wallet = GTradeWallet()
        self._latest_lock = threading.RLock()
        self._latest_prices: dict[str, dict[str, Any]] = {}
        self._latest_prices_at = 0.0

    def start(self) -> None:
        self.wallet.start()

    def stop(self) -> None:
        self.wallet.stop()

    @property
    def feed_pairs(self) -> tuple[str, ...]:
        return self.public.feed_pairs

    def wallet_address(self) -> str:
        return self.wallet.address()

    def account(self) -> dict[str, Any]:
        pairs_by_index = {row.pair_index: row.pair for row in self.public.pairs().values()}
        return self.wallet.account(pairs_by_index, self.prices())

    def usdc_balance(self) -> float:
        return self.wallet.usdc_balance()

    def positions(self) -> dict[str, Any]:
        return self.account()

    def markets(self, limit: int = 10) -> dict[str, Any]:
        return self.public.markets(limit=limit)

    def price(self, pair: str) -> dict[str, Any]:
        return self.public.price(pair)

    def prices(self) -> dict[str, dict[str, Any]]:
        return self.public.prices(self.feed_pairs)

    def stream_prices(
        self,
        pairs: Iterable[str],
        stop_event: threading.Event,
    ) -> Iterator[dict[str, dict[str, Any]]]:
        for prices in self.public.stream_prices(pairs, stop_event):
            with self._latest_lock:
                self._latest_prices.update(prices)
                self._latest_prices_at = time.monotonic()
            yield prices

    def chart(self, pair: str, minutes: int = 20) -> dict[str, Any]:
        return self.public.chart(pair, minutes=minutes)

    def estimate_open(self, pair: str, side: str, ticket_usd: Decimal, leverage: Decimal) -> dict[str, Any]:
        row = self.public.pair(pair)
        execution_leverage = gtrade_execution_leverage(row, leverage)
        live = self._fresh_price(row.pair) or self.public.prices((row.pair,)).get(row.pair)
        if not live:
            raise GTradeError(f"price not found: {row.pair}")
        quote = estimate_gtrade_open(row, live, side, ticket_usd, execution_leverage)
        quote["requestedLeverage"] = float(leverage)
        quote["leverageNormalized"] = execution_leverage != leverage
        return quote

    def open_position(
        self,
        pair: str,
        side: str,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self.public.pair(pair)
        execution_leverage = gtrade_execution_leverage(row, leverage)
        price = Decimal(str((quote or {}).get("price") or self.public.price(row.pair)["price"]["mid"]))
        return self.wallet.open_position(
            row,
            side,
            ticket_usd,
            execution_leverage,
            price,
            slippage_bps=int((quote or {}).get("slippageBps") or 100),
            stop_loss_price=(
                Decimal(str((quote or {}).get("stopLossPrice")))
                if (quote or {}).get("stopLossPrice") is not None
                else None
            ),
        )

    def estimate_close(self, pair: str) -> dict[str, Any]:
        row = self.public.pair(pair)
        account = self.account()
        position = next((item for item in account["positions"] if item["pair"] == row.pair), None)
        if position is None:
            raise GTradeError(f"no open position for {row.pair}")
        live = self._fresh_price(row.pair) or self.public.prices((row.pair,)).get(row.pair)
        if not live:
            raise GTradeError(f"price not found: {row.pair}")
        return estimate_gtrade_close(row, position, live)

    def close_position(self, pair: str, position: dict[str, Any] | None = None) -> dict[str, Any]:
        row = self.public.pair(pair)
        live = self._fresh_price(row.pair) or self.public.prices((row.pair,)).get(row.pair)
        if not live:
            raise GTradeError(f"price not found: {row.pair}")
        price = Decimal(str(live["bid"] if (position or {}).get("side") == "long" else live["ask"]))
        return self.wallet.close_position(row, position or {}, price)

    def latest_position_event(
        self,
        pair: str,
        *,
        present: bool,
        since: float,
        position_index: int | None = None,
    ) -> dict[str, Any] | None:
        row = self.public.pair(pair)
        return self.wallet.latest_position_event(
            row.pair_index,
            present=present,
            since=since,
            position_index=position_index,
        )

    def approve(self, amount: Decimal | None = None) -> dict[str, Any]:
        return self.wallet.approve(amount)

    def execution_health(self) -> dict[str, Any]:
        return self.wallet.execution_health()

    def _fresh_price(self, pair: str) -> dict[str, Any] | None:
        pair = normalize_pair(pair)
        with self._latest_lock:
            value = self._latest_prices.get(pair)
            if not value:
                return None
            received_at = float(value.get("_receivedAt") or 0)
            if received_at and time.time() - received_at <= 2.5:
                return dict(value)
            if not received_at and time.monotonic() - self._latest_prices_at <= 2.5:
                return dict(value)
            return None
