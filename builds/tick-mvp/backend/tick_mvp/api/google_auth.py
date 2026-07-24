from __future__ import annotations

import hashlib
from dataclasses import dataclass

from tick_mvp.core.config import Settings
from tick_mvp.domain.schemas import GoogleSessionRequest


class GoogleAuthError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GoogleIdentity:
    subject: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


def verify_google_identity(body: GoogleSessionRequest, settings: Settings) -> GoogleIdentity:
    if settings.tick_google_auth_dev and body.devEmail:
        subject = hashlib.sha256(f"google-dev:{body.devEmail.lower()}".encode()).hexdigest()
        return GoogleIdentity(subject=subject, email=body.devEmail, display_name=body.devName, avatar_url=None)

    if not settings.google_client_id:
        raise GoogleAuthError("GOOGLE_CLIENT_ID is not configured")

    # Official Google verifier; imported only on the real auth path.
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        payload = id_token.verify_oauth2_token(body.idToken, google_requests.Request(), settings.google_client_id)
    except ValueError as exc:
        raise GoogleAuthError("invalid Google ID token") from exc

    subject = str(payload.get("sub") or "")
    email = str(payload.get("email") or "")
    if not subject or not email:
        raise GoogleAuthError("Google token missing subject or email")

    return GoogleIdentity(
        subject=subject,
        email=email,
        display_name=payload.get("name"),
        avatar_url=payload.get("picture"),
    )
