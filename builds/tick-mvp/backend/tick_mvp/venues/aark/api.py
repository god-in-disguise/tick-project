from __future__ import annotations

import time
from typing import Any

import requests

from tick_mvp.core.config import Settings
from tick_mvp.venues.aark.public import AarkError


class AarkApiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session = requests.Session()

    def close(self) -> None:
        self._session.close()

    def post(
        self,
        path: str,
        *,
        body: dict[str, Any],
        headers: dict[str, str],
        include_frontend_version: bool = True,
    ) -> dict[str, Any]:
        url = f"{self._settings.aark_api_url.rstrip('/')}{path}"
        request_headers = {
            "content-type": "application/json",
            "user-agent": "tick-mvp/0.2",
            **headers,
        }
        if include_frontend_version:
            request_headers["version"] = self._settings.aark_frontend_version
        response = self._session.post(
            url,
            json=body,
            headers=request_headers,
            timeout=15,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AarkError(f"Aark POST {path} returned invalid JSON") from exc
        if not response.ok:
            raise AarkError(f"Aark POST {path} failed ({response.status_code}): {payload}")
        if isinstance(payload, dict) and int(payload.get("statusCode") or 0) >= 400:
            raise AarkError(f"Aark POST {path} failed: {payload}")
        if isinstance(payload, dict) and payload.get("code") not in {None, 200, "200"}:
            raise AarkError(f"Aark POST {path} rejected: {payload}")
        return dict(payload) if isinstance(payload, dict) else {"data": payload}

    @staticmethod
    def request_id(payload: dict[str, Any]) -> str | None:
        data = payload.get("data")
        candidates = [
            payload.get("id"),
            payload.get("requestId"),
            data.get("id") if isinstance(data, dict) else None,
            data.get("requestId") if isinstance(data, dict) else None,
        ]
        return next((str(value) for value in candidates if value is not None), None)

    @staticmethod
    def transaction_hash(payload: dict[str, Any]) -> str | None:
        data = payload.get("data")
        candidates = [
            payload.get("txHash"),
            payload.get("transactionHash"),
            data.get("txHash") if isinstance(data, dict) else None,
            data.get("transactionHash") if isinstance(data, dict) else None,
        ]
        return next((str(value) for value in candidates if value), None)

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
