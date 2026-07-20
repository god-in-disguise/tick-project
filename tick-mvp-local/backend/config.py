from __future__ import annotations

import os
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = PROJECT_DIR.parent
LOCAL_DIR = PROJECT_DIR / ".local"
DATABASE_PATH = Path(os.getenv("TICK_LOCAL_DB", str(LOCAL_DIR / "tick.sqlite3")))
LOCAL_API_TOKEN = os.getenv("TICK_LOCAL_API_TOKEN", "tick-local-one-wallet")
DEFAULT_TICKET_USD = float(os.getenv("TICK_DEFAULT_TICKET_USD", "20"))
DEFAULT_LEVERAGE = float(os.getenv("TICK_DEFAULT_LEVERAGE", "100"))
