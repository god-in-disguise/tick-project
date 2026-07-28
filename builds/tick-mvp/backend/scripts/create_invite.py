from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from tick_mvp.core.config import get_settings
from tick_mvp.domain.invitations import generate_invite_code, hash_invite_code
from tick_mvp.infrastructure.sqlalchemy_store import SQLAlchemyStore


def main() -> None:
    args = parse_args()
    settings = get_settings()
    code = generate_invite_code()
    expires_at = (
        datetime.now(UTC) + timedelta(days=args.expires_days)
        if args.expires_days is not None
        else None
    )
    store = SQLAlchemyStore(default_venue=settings.default_venue)
    invite_id = store.create_invite_code(
        code_hash=hash_invite_code(code, secret=settings.tick_invite_code_secret),
        display_name=args.name,
        expires_at=expires_at,
    )
    print(
        json.dumps(
            {
                "inviteId": invite_id,
                "accessCode": code,
                "displayName": args.name,
                "expiresAt": expires_at.isoformat() if expires_at else None,
            },
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create one TICK invitation.",
    )
    parser.add_argument("--name", help="Optional profile name attached to this invitation.")
    parser.add_argument("--expires-days", type=int, default=30)
    return parser.parse_args()


if __name__ == "__main__":
    main()
