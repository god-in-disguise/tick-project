from __future__ import annotations

import json
import logging
import threading
import time
from decimal import Decimal
from typing import Any

from websockets.sync.client import connect


LOGGER = logging.getLogger("tick.gtrade.prices")
MAX_PRICE_FRAME_BYTES = 8 * 1024 * 1024


class GTradePriceStream:
    """One live gTrade price connection shared by every user in this process."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._latest: dict[int, tuple[Decimal, float]] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._last_message_at = 0.0
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="gtrade-prices", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def price(self, pair_index: int, *, max_age_seconds: float = 2.5) -> dict[str, Any] | None:
        with self._lock:
            value = self._latest.get(pair_index)
        if value is None:
            return None
        mid, received_at = value
        age = time.time() - received_at
        if age > max_age_seconds:
            return None
        return {
            "mid": mid,
            "receivedAt": received_at,
            "ageMs": round(age * 1000, 1),
            "source": "gtrade_pricing_ws",
        }

    def health(self) -> dict[str, Any]:
        with self._lock:
            market_count = len(self._latest)
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "connected": self._connected,
            "lastMessageAt": self._last_message_at or None,
            "lastError": self._last_error,
            "marketCount": market_count,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with connect(
                    self._url,
                    open_timeout=10,
                    close_timeout=2,
                    ping_interval=None,
                    max_size=MAX_PRICE_FRAME_BYTES,
                ) as websocket:
                    self._connected = True
                    self._last_error = None
                    while not self._stop.is_set():
                        try:
                            raw = websocket.recv(timeout=1)
                        except TimeoutError:
                            continue
                        self._handle_raw(raw)
            except Exception as exc:
                self._connected = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                LOGGER.warning("gTrade price stream disconnected: %s", exc)
                self._stop.wait(0.75)
        self._connected = False

    def _handle_raw(self, raw: str | bytes) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, list) or len(payload) < 2:
            return
        received_at = time.time()
        updates: dict[int, tuple[Decimal, float]] = {}
        for offset in range(0, len(payload) - 1, 2):
            try:
                updates[int(payload[offset])] = (Decimal(str(payload[offset + 1])), received_at)
            except (TypeError, ValueError):
                continue
        if not updates:
            return
        with self._lock:
            self._latest.update(updates)
            self._last_message_at = received_at
