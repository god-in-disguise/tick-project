from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
_LOCK = threading.Lock()


def latency_log_path() -> Path:
    load_dotenv(ROOT / ".env")
    configured = os.getenv("GTRADE_LATENCY_LOG")
    if configured:
        return Path(configured).expanduser()
    return ROOT / "tick-mvp-local" / ".local" / "gtrade-latency.jsonl"


def latency_log_enabled() -> bool:
    load_dotenv(ROOT / ".env")
    return os.getenv("GTRADE_LATENCY_LOG_ENABLED", "1") == "1"


def write_latency_event(event: str, payload: dict[str, Any] | None = None) -> None:
    if not latency_log_enabled():
        return
    path = latency_log_path()
    record = {
        "event": event,
        "wallTime": time.time(),
        "perfCounter": time.perf_counter(),
        **(payload or {}),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    except Exception:
        # Latency logging is diagnostic only and must never block execution.
        pass
