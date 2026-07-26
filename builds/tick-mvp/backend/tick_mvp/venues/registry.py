from __future__ import annotations

from tick_mvp.core.config import Settings
from tick_mvp.venues.gtrade import GTradeVenue


def create_venue(settings: Settings):
    venue = settings.default_venue.strip().lower()
    if venue == "gtrade":
        return GTradeVenue(settings)
    raise ValueError(f"unsupported venue: {settings.default_venue}")


def create_quote_engine(settings: Settings):
    if not settings.tick_real_quotes_enabled:
        return None
    return create_venue(settings)

