from __future__ import annotations

from decimal import Decimal
from typing import Any

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.base import VenueError, VenueQuote


class VenueRouter:
    """Routes normalized market and quote requests without leaking venues into product code."""

    def __init__(self, venues: dict[str, Any], *, default_venue: str) -> None:
        if default_venue not in venues:
            raise ValueError(f"default venue is not enabled: {default_venue}")
        self._venues = venues
        self._default_venue = default_venue

    def start(self) -> None:
        for venue in self._venues.values():
            start = getattr(venue, "start", None)
            if start is not None:
                start()

    def stop(self) -> None:
        for venue in reversed(list(self._venues.values())):
            stop = getattr(venue, "stop", None)
            if stop is not None:
                stop()

    def quote_open(
        self,
        *,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        max_loss_usd: Decimal | None,
        take_profit_usd: Decimal | None,
    ) -> VenueQuote:
        venue = self._venue_for_market(market)
        return venue.quote_open(
            market=market,
            side=side,
            ticket_usd=ticket_usd,
            leverage=leverage,
            max_loss_usd=max_loss_usd,
            take_profit_usd=take_profit_usd,
        )

    def markets(self, *, limit: int = 10) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for venue in self._venues.values():
            method = getattr(venue, "markets", None)
            if method is None:
                continue
            payload = method(limit=limit)
            rows.extend(payload.get("markets") or [])
        rows.sort(key=lambda row: float(row.get("score") or 0), reverse=True)
        return {
            "venue": "tick-router",
            "markets": rows,
        }

    def chart(self, market: str, *, window_seconds: int = 90) -> dict[str, Any]:
        return self._venue_for_market(market).chart(market, window_seconds=window_seconds)

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        return self._venue_for_market(market).tape(market, since=since)

    def _venue_for_market(self, market: str):
        for venue in self._venues.values():
            supports = getattr(venue, "supports_market", None)
            if supports is not None and supports(market):
                return venue
        if market.upper().startswith("AARK-") and "aark" not in self._venues:
            raise VenueError("Aark route is not enabled")
        return self._venues[self._default_venue]
