from __future__ import annotations

from tick_mvp.core.config import Settings
from tick_mvp.venues.aark import AarkVenue
from tick_mvp.venues.avantis import AvantisVenue
from tick_mvp.venues.flash import FlashVenue
from tick_mvp.venues.gtrade import GTradeVenue
from tick_mvp.venues.router import VenueRouter


def create_venue(
    settings: Settings,
    venue_name: str | None = None,
    *,
    market_history=None,
):
    venue = (venue_name or settings.default_venue).strip().lower()
    if venue == "gtrade":
        return GTradeVenue(settings, market_history=market_history)
    if venue == "aark":
        return AarkVenue(settings)
    if venue == "flash":
        return FlashVenue(settings, market_history=market_history)
    if venue == "avantis":
        return AvantisVenue(settings, market_history=market_history)
    raise ValueError(f"unsupported venue: {venue}")


def enabled_venue_names(settings: Settings) -> list[str]:
    names = [
        name.strip().lower()
        for name in settings.enabled_venues.split(",")
        if name.strip()
    ]
    if settings.default_venue not in names:
        names.insert(0, settings.default_venue)
    return list(dict.fromkeys(names))


def create_enabled_venues(settings: Settings, *, market_history=None) -> dict[str, object]:
    return {
        name: create_venue(settings, name, market_history=market_history)
        for name in enabled_venue_names(settings)
    }


def create_quote_engine(settings: Settings):
    if not settings.tick_real_quotes_enabled:
        return None
    market_history = None
    if settings.tick_store_backend == "postgres":
        from tick_mvp.infrastructure.market_history import PostgresMarketHistory

        market_history = PostgresMarketHistory(settings)
    venues = create_enabled_venues(settings, market_history=market_history)
    return VenueRouter(venues, default_venue=settings.default_venue)
