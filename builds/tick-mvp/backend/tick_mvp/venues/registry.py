from __future__ import annotations

from tick_mvp.core.config import Settings
from tick_mvp.venues.aark import AarkVenue
from tick_mvp.venues.gtrade import GTradeVenue
from tick_mvp.venues.router import VenueRouter


def create_venue(settings: Settings, venue_name: str | None = None):
    venue = (venue_name or settings.default_venue).strip().lower()
    if venue == "gtrade":
        return GTradeVenue(settings)
    if venue == "aark":
        return AarkVenue(settings)
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


def create_enabled_venues(settings: Settings) -> dict[str, object]:
    return {
        name: create_venue(settings, name)
        for name in enabled_venue_names(settings)
    }


def create_quote_engine(settings: Settings):
    if not settings.tick_real_quotes_enabled:
        return None
    venues = create_enabled_venues(settings)
    return VenueRouter(venues, default_venue=settings.default_venue)
