from __future__ import annotations

import threading
from collections.abc import Iterable, Iterator
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


class ConnectorError(Exception):
    """Normalized venue failure safe to return through the local API."""


@runtime_checkable
class VenueConnector(Protocol):
    """Execution and market-data boundary implemented by every venue."""

    name: str
    feed_pairs: tuple[str, ...]

    def wallet_address(self) -> str: ...

    def account(self) -> dict[str, Any]: ...

    def positions(self) -> dict[str, Any]: ...

    def markets(self, limit: int = 10) -> dict[str, Any]: ...

    def price(self, pair: str) -> dict[str, Any]: ...

    def prices(self) -> dict[str, dict[str, Any]]: ...

    def stream_prices(
        self,
        pairs: Iterable[str],
        stop_event: threading.Event,
    ) -> Iterator[dict[str, dict[str, Any]]]: ...

    def chart(self, pair: str, minutes: int = 120) -> dict[str, Any]: ...

    def estimate_open(
        self,
        pair: str,
        side: str,
        ticket_usd: Decimal,
        leverage: Decimal,
    ) -> dict[str, Any]: ...

    def open_position(
        self,
        pair: str,
        side: str,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def estimate_close(self, pair: str) -> dict[str, Any]: ...

    def close_position(self, pair: str, position: dict[str, Any] | None = None) -> dict[str, Any]: ...

    def approve(self, amount: Decimal | None = None) -> dict[str, Any]: ...

    def execution_health(self) -> dict[str, Any]: ...
