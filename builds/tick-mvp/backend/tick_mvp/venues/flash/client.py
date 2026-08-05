from __future__ import annotations

import time
from typing import Any, Callable

import requests

from tick_mvp.venues.flash.constants import (
    STATE_HEDGE_SECONDS,
    STATE_POLL_SECONDS,
    STATE_TIMEOUT_SECONDS,
)
from tick_mvp.venues.flash.signing import PreparedFlashTransaction, sign_built_transaction


class FlashError(RuntimeError):
    pass


class FlashAmbiguousExecution(FlashError):
    def __init__(self, signature: str, raw_basket: dict[str, Any]) -> None:
        super().__init__(f"Flash transaction {signature} was acknowledged without a state transition")
        self.signature = signature
        self.raw_basket = raw_basket


class FlashSubmissionRejected(FlashError):
    """The Flash router or program rejected the exact signed transaction."""


_ALREADY_PROCESSED_MARKERS = (
    "already processed",
    "transaction has already been processed",
)
_DETERMINISTIC_REJECTION_MARKERS = (
    "custom program error",
    "instructionerror",
    "invalid transaction",
    "signature verification failed",
    "transaction simulation failed",
)


class FlashClient:
    """Process-lifetime Flash HTTP client. Economic state comes from the raw basket."""

    def __init__(
        self,
        base_url: str,
        session: requests.Session | None = None,
        *,
        hedge_seconds: float = STATE_HEDGE_SECONDS,
        poll_seconds: float = STATE_POLL_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers.update({"user-agent": "tick-mvp-flash/0.1"})
        self.hedge_seconds = hedge_seconds
        self.poll_seconds = poll_seconds

    def close(self) -> None:
        self.session.close()

    def health(self) -> dict[str, Any]:
        return self.get("/health")

    def prices(self) -> dict[str, Any]:
        return self.get("/prices")

    def owner(self, owner: str) -> dict[str, Any]:
        return self.get(f"/owner/{owner}")

    def raw_basket(self, basket_pubkey: str) -> dict[str, Any]:
        return self.get(f"/raw/baskets/{basket_pubkey}")

    def quote_open(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.post("/transaction-builder/open-position", body)

    def prepare(self, path: str, body: dict[str, Any], keypair) -> PreparedFlashTransaction:
        build_started = time.perf_counter()
        built = self.post(path, body)
        build_ms = (time.perf_counter() - build_started) * 1000
        encoded = built.get("transactionBase64")
        if not encoded:
            raise FlashError(f"Flash builder returned no transaction: {built}")
        sign_started = time.perf_counter()
        signed = sign_built_transaction(encoded, keypair)
        sign_ms = (time.perf_counter() - sign_started) * 1000
        return PreparedFlashTransaction(
            signature=signed.signature,
            signed_transaction_base64=signed.signed_transaction_base64,
            quote={key: value for key, value in built.items() if key != "transactionBase64"},
            build_ms=round(build_ms, 3),
            sign_ms=round(sign_ms, 3),
        )

    def submit_and_wait(
        self,
        prepared: PreparedFlashTransaction,
        *,
        basket_pubkey: str,
        predicate: Callable[[dict[str, Any]], bool],
        timeout_seconds: float = STATE_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        submissions = [self._submit_exact(prepared)]
        hedge_sent = False
        latest: dict[str, Any] = {}
        while time.perf_counter() - started < timeout_seconds:
            latest = self.raw_basket(basket_pubkey)
            if predicate(latest):
                return {
                    "signature": prepared.signature,
                    "buildMs": prepared.build_ms,
                    "signMs": prepared.sign_ms,
                    "visibleMs": round((time.perf_counter() - started) * 1000, 3),
                    "hedged": hedge_sent,
                    "submissions": submissions,
                    "rawBasket": latest,
                }
            if not hedge_sent and time.perf_counter() - started >= self.hedge_seconds:
                submissions.append(self._submit_exact(prepared))
                hedge_sent = True
            time.sleep(self.poll_seconds)
        raise FlashAmbiguousExecution(prepared.signature, latest)

    def submit_exact(
        self,
        prepared: PreparedFlashTransaction,
        *,
        skip_preflight: bool = True,
    ) -> dict[str, Any]:
        return self._submit_exact(prepared, skip_preflight=skip_preflight)

    def get(self, path: str) -> Any:
        response = self.session.get(f"{self.base_url}{path}", timeout=12)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, body: dict[str, Any]) -> Any:
        response = self.session.post(f"{self.base_url}{path}", json=body, timeout=20)
        if not response.ok:
            raise FlashError(f"Flash {path} failed ({response.status_code}): {response.text}")
        return response.json()

    def _submit_exact(
        self,
        prepared: PreparedFlashTransaction,
        *,
        skip_preflight: bool = True,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/transaction-builder/submit-transaction"
        started = time.perf_counter()
        try:
            response = self.session.post(
                url,
                json={
                    "transactionBase64": prepared.signed_transaction_base64,
                    "skipPreflight": skip_preflight,
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            # A timeout is ambiguous: the router may have accepted the exact
            # transaction. Keep polling state and let the identical hedge run.
            return {
                "signature": prepared.signature,
                "transportAmbiguous": True,
                "requestMs": round((time.perf_counter() - started) * 1000, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }

        body_text = response.text
        lowered = body_text.lower()
        if not response.ok:
            if any(marker in lowered for marker in _ALREADY_PROCESSED_MARKERS):
                return {
                    "signature": prepared.signature,
                    "alreadyProcessed": True,
                    "statusCode": response.status_code,
                    "requestMs": round((time.perf_counter() - started) * 1000, 3),
                }
            if response.status_code < 500 or any(
                marker in lowered for marker in _DETERMINISTIC_REJECTION_MARKERS
            ):
                raise FlashSubmissionRejected(
                    f"Flash rejected {prepared.signature} "
                    f"({response.status_code}): {body_text}"
                )
            return {
                "signature": prepared.signature,
                "transportAmbiguous": True,
                "statusCode": response.status_code,
                "requestMs": round((time.perf_counter() - started) * 1000, 3),
                "error": body_text,
            }

        try:
            payload = response.json()
        except ValueError as exc:
            raise FlashError("Flash submit returned invalid JSON") from exc
        remote = payload.get("signature") or payload.get("txSignature")
        if remote and remote != prepared.signature:
            raise FlashError(
                f"Flash signature mismatch: local={prepared.signature} remote={remote}"
            )
        return {
            **payload,
            "requestMs": round((time.perf_counter() - started) * 1000, 3),
        }
