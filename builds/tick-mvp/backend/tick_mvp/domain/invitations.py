from __future__ import annotations

import hashlib
import hmac
import secrets


class InviteAuthError(Exception):
    pass


def hash_invite_code(code: str, *, secret: str) -> str:
    normalized = code.strip()
    if not normalized:
        raise InviteAuthError("invite code is required")
    return hmac.new(secret.encode(), normalized.encode(), hashlib.sha256).hexdigest()


def generate_invite_code() -> str:
    return f"tick_{secrets.token_urlsafe(18)}"
