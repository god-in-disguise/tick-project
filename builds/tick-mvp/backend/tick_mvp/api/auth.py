from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


class AuthError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UserSession:
    user_id: str
    wallet_address: str | None = None
    issuer: str = "tick"


def create_session_token(
    *,
    user_id: str,
    secret: str,
    ttl_seconds: int,
    wallet_address: str | None = None,
    issuer: str = "tick",
) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "iss": issuer,
        "sub": user_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    if wallet_address:
        payload["wallet"] = wallet_address
    encoded_header = _b64_json(header)
    encoded_payload = _b64_json(payload)
    signature = _sign(f"{encoded_header}.{encoded_payload}", secret)
    return f"{encoded_header}.{encoded_payload}.{signature}"


def verify_session_token(token: str, *, secret: str, issuer: str = "tick") -> UserSession:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("invalid token format")
    encoded_header, encoded_payload, signature = parts
    expected = _sign(f"{encoded_header}.{encoded_payload}", secret)
    if not hmac.compare_digest(signature, expected):
        raise AuthError("invalid token signature")
    payload = _decode_json(encoded_payload)
    if payload.get("iss") != issuer:
        raise AuthError("invalid token issuer")
    if int(payload.get("exp") or 0) <= int(time.time()):
        raise AuthError("token expired")
    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise AuthError("missing user subject")
    wallet = payload.get("wallet")
    return UserSession(user_id=user_id, wallet_address=str(wallet) if wallet else None, issuer=issuer)


def _b64_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return _b64(encoded)


def _decode_json(value: str) -> dict[str, Any]:
    try:
        return json.loads(_unb64(value))
    except Exception as exc:
        raise AuthError("invalid token payload") from exc


def _sign(value: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), value.encode(), hashlib.sha256).digest()
    return _b64(digest)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)

