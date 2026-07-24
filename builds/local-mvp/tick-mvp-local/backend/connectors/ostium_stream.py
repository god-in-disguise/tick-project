from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterable, Iterator
from typing import Any

from websockets.sync.client import connect


LOGGER = logging.getLogger("tick.ostium.stream")
PRICE_STREAM_URL = "wss://builder.ostium.io/v1/prices/stream"


def stream_prices(
    pairs: Iterable[str],
    stop_event: threading.Event,
) -> Iterator[dict[str, dict[str, Any]]]:
    subscriptions = tuple(dict.fromkeys(pair.upper().replace("/", "-") for pair in pairs))
    backoff = 0.5

    while not stop_event.is_set():
        try:
            with connect(
                PRICE_STREAM_URL,
                open_timeout=10,
                close_timeout=2,
                ping_interval=15,
                ping_timeout=10,
            ) as socket:
                socket.send(json.dumps({"type": "subscribe", "pairs": list(subscriptions)}))
                backoff = 0.5
                while not stop_event.is_set():
                    try:
                        raw = socket.recv(timeout=1)
                    except TimeoutError:
                        continue
                    update = _parse_message(raw, subscriptions)
                    if update:
                        yield update
        except Exception as exc:
            if stop_event.is_set():
                return
            LOGGER.warning("price stream disconnected: %s", exc)
            stop_event.wait(backoff)
            backoff = min(backoff * 2, 8.0)


def _parse_message(raw: str | bytes, subscriptions: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    payload = json.loads(raw)
    message_type = payload.get("type")
    data = payload.get("data")
    values = data if message_type == "snapshot" and isinstance(data, list) else [data]
    allowed = set(subscriptions)
    parsed: dict[str, dict[str, Any]] = {}
    for item in values:
        if not isinstance(item, dict):
            continue
        pair = str(item.get("pair") or "").upper().replace("/", "-")
        if pair not in allowed:
            continue
        if not all(item.get(field) is not None for field in ("mid", "bid", "ask")):
            continue
        parsed[pair] = item
    return parsed
