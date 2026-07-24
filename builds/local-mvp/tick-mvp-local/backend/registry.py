from __future__ import annotations

import os

from .connectors import GTradeConnector, OstiumConnector, VenueConnector


def build_connector() -> VenueConnector:
    venue = os.getenv("TICK_VENUE", "ostium").strip().lower()
    if venue == "ostium":
        return OstiumConnector()
    if venue in {"gtrade", "gains"}:
        return GTradeConnector()
    raise RuntimeError(f"unsupported TICK_VENUE: {venue}")
