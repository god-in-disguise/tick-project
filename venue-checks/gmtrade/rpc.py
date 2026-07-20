from __future__ import annotations

import base64
import time
from decimal import Decimal
from typing import Any

import requests
from solders.hash import Hash
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction


class SolanaRpc:
    def __init__(self, url: str, timeout_seconds: float = 30) -> None:
        self._url = url
        self._timeout_seconds = timeout_seconds
        self._request_id = 0

    def _call(self, method: str, params: list[Any]) -> Any:
        self._request_id += 1
        response = requests.post(
            self._url,
            json={
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(f"RPC {method} failed: {payload['error']}")
        return payload["result"]

    def latest_blockhash(self) -> Hash:
        result = self._call(
            "getLatestBlockhash", [{"commitment": "confirmed"}]
        )
        return Hash.from_string(result["value"]["blockhash"])

    def balance_lamports(self, address: Pubkey) -> int:
        result = self._call(
            "getBalance", [str(address), {"commitment": "confirmed"}]
        )
        return int(result["value"])

    def token_balance(self, owner: Pubkey, mint: Pubkey) -> Decimal:
        result = self._call(
            "getTokenAccountsByOwner",
            [
                str(owner),
                {"mint": str(mint)},
                {"commitment": "confirmed", "encoding": "jsonParsed"},
            ],
        )
        balance = Decimal(0)
        for account in result["value"]:
            token_amount = account["account"]["data"]["parsed"]["info"][
                "tokenAmount"
            ]
            balance += Decimal(token_amount["amount"]).scaleb(
                -int(token_amount["decimals"])
            )
        return balance

    def simulate(self, transaction: VersionedTransaction) -> dict[str, Any]:
        encoded = base64.b64encode(bytes(transaction)).decode("ascii")
        result = self._call(
            "simulateTransaction",
            [
                encoded,
                {
                    "encoding": "base64",
                    "commitment": "confirmed",
                    "sigVerify": True,
                    "replaceRecentBlockhash": False,
                    "innerInstructions": True,
                },
            ],
        )
        return result["value"]

    def send_transaction(
        self,
        transaction: VersionedTransaction,
        *,
        skip_preflight: bool = False,
        max_retries: int = 3,
    ) -> Signature:
        encoded = base64.b64encode(bytes(transaction)).decode("ascii")
        result = self._call(
            "sendTransaction",
            [
                encoded,
                {
                    "encoding": "base64",
                    "skipPreflight": skip_preflight,
                    "preflightCommitment": "confirmed",
                    "maxRetries": max_retries,
                },
            ],
        )
        return Signature.from_string(result)

    def signature_status(self, signature: Signature) -> dict[str, Any] | None:
        result = self._call(
            "getSignatureStatuses",
            [[str(signature)], {"searchTransactionHistory": True}],
        )
        value = result["value"]
        if not value:
            return None
        return value[0]

    def wait_for_signature(
        self,
        signature: Signature,
        *,
        timeout_seconds: float = 45,
    ) -> tuple[float, dict[str, Any]]:
        started = time.perf_counter()
        last: dict[str, Any] | None = None
        while time.perf_counter() - started < timeout_seconds:
            status = self.signature_status(signature)
            if status is not None:
                last = status
                if status.get("err") is not None:
                    raise RuntimeError(f"Transaction failed: {status['err']}")
                confirmation = status.get("confirmationStatus")
                if confirmation in {"confirmed", "finalized"}:
                    return (time.perf_counter() - started) * 1000, status
            time.sleep(0.2)
        raise TimeoutError(f"Transaction was not confirmed: {signature} last={last}")
