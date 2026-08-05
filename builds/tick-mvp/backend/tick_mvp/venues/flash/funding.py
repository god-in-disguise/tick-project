from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests
from solders.hash import Hash
from solders.message import Message
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction

from tick_mvp.venues.flash.constants import USDC_MINT, USD_DECIMALS
from tick_mvp.venues.flash.deposit_ledger import deposit_ledger_address, deposit_ledger_usdc
from tick_mvp.venues.flash.signing import keypair_from_secret


LAMPORTS_PER_SOL = Decimal(1_000_000_000)


class FlashSetupFundingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SolanaWalletState:
    sol: Decimal
    usdc: Decimal
    deposited_usdc: Decimal = Decimal(0)


class FlashSetupFunder:
    """Funds only the SOL needed to initialize a funded user's Flash account."""

    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        *,
        setup_target_sol: Decimal,
        session: requests.Session | None = None,
    ) -> None:
        self._rpc_url = rpc_url
        self._keypair = keypair_from_secret(private_key) if private_key else None
        self._setup_target_sol = setup_target_sol
        self._session = session or requests.Session()
        self._session.headers.update({"user-agent": "tick-mvp-flash-funder/0.1"})
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return self._keypair is not None and bool(self._rpc_url)

    @property
    def address(self) -> str | None:
        return str(self._keypair.pubkey()) if self._keypair is not None else None

    @property
    def setup_target_sol(self) -> Decimal:
        return self._setup_target_sol

    def close(self) -> None:
        self._session.close()

    def wallet_state(self, owner: str) -> SolanaWalletState:
        result = self._rpc(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [owner, {"commitment": "confirmed"}],
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "getTokenAccountsByOwner",
                    "params": [
                        owner,
                        {"mint": USDC_MINT},
                        {"encoding": "jsonParsed", "commitment": "confirmed"},
                    ],
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "getAccountInfo",
                    "params": [
                        deposit_ledger_address(owner),
                        {"encoding": "base64", "commitment": "confirmed"},
                    ],
                },
            ]
        )
        if not isinstance(result, list):
            raise FlashSetupFundingError("Solana balance RPC returned a non-list response")
        by_id = {int(item["id"]): item for item in result if isinstance(item, dict)}
        for request_id in (1, 2, 3):
            item = by_id.get(request_id)
            if item is None or item.get("error"):
                raise FlashSetupFundingError(f"Solana balance RPC failed: {item}")
        lamports = int(by_id[1]["result"]["value"])
        token_units = 0
        for row in by_id[2]["result"].get("value") or []:
            amount = row["account"]["data"]["parsed"]["info"]["tokenAmount"]
            token_units += int(amount["amount"])
        return SolanaWalletState(
            sol=Decimal(lamports) / LAMPORTS_PER_SOL,
            usdc=Decimal(token_units).scaleb(-USD_DECIMALS),
            deposited_usdc=deposit_ledger_usdc(by_id[3]["result"].get("value")),
        )

    def ensure_funded(
        self,
        owner: str,
        *,
        target_sol: Decimal | None = None,
    ) -> dict[str, Any]:
        if not self.configured or self._keypair is None:
            raise FlashSetupFundingError("FLASH_SETUP_WALLET_PRIVATE_KEY is not configured")
        target = target_sol if target_sol is not None else self._setup_target_sol
        target_lamports = int(target * LAMPORTS_PER_SOL)
        if target_lamports <= 0:
            raise FlashSetupFundingError("Flash setup SOL target must be positive")

        with self._lock:
            before = self.wallet_state(owner)
            before_lamports = int(before.sol * LAMPORTS_PER_SOL)
            shortfall = max(0, target_lamports - before_lamports)
            if shortfall == 0:
                return {
                    "funded": False,
                    "wallet": owner,
                    "platformWallet": self.address,
                    "solBefore": str(before.sol),
                    "solAfter": str(before.sol),
                    "amountSol": "0",
                    "signature": None,
                }

            blockhash = Hash.from_string(
                self._rpc_call(
                    "getLatestBlockhash",
                    [{"commitment": "confirmed"}],
                )["value"]["blockhash"]
            )
            instruction = transfer(
                TransferParams(
                    from_pubkey=self._keypair.pubkey(),
                    to_pubkey=Pubkey.from_string(owner),
                    lamports=shortfall,
                )
            )
            transaction = Transaction(
                [self._keypair],
                Message([instruction], self._keypair.pubkey()),
                blockhash,
            )
            encoded = base64.b64encode(bytes(transaction)).decode("ascii")
            signature = str(transaction.signatures[0])
            send_error: str | None = None
            try:
                remote = self._rpc_call(
                    "sendTransaction",
                    [
                        encoded,
                        {
                            "encoding": "base64",
                            "skipPreflight": False,
                            "preflightCommitment": "confirmed",
                            "maxRetries": 3,
                        },
                    ],
                )
                if remote != signature:
                    raise FlashSetupFundingError(
                        f"Solana funding signature mismatch: local={signature} remote={remote}"
                    )
            except requests.RequestException as exc:
                # The signed signature is deterministic. Resolve an ambiguous send
                # from chain state instead of constructing another transfer.
                send_error = f"{type(exc).__name__}: {exc}"

            confirmed = self._wait_for_signature(signature, owner, target_lamports)
            after = self.wallet_state(owner)
            return {
                "funded": True,
                "wallet": owner,
                "platformWallet": self.address,
                "solBefore": str(before.sol),
                "solAfter": str(after.sol),
                "amountSol": str(Decimal(shortfall) / LAMPORTS_PER_SOL),
                "signature": signature,
                "confirmation": confirmed,
                "sendError": send_error,
            }

    def _wait_for_signature(
        self,
        signature: str,
        owner: str,
        target_lamports: int,
        *,
        timeout_seconds: float = 30,
    ) -> dict[str, Any]:
        started = time.monotonic()
        latest: dict[str, Any] | None = None
        while time.monotonic() - started < timeout_seconds:
            result = self._rpc_call(
                "getSignatureStatuses",
                [[signature], {"searchTransactionHistory": True}],
            )
            values = result.get("value") or []
            latest = values[0] if values else None
            if latest is not None:
                if latest.get("err") is not None:
                    raise FlashSetupFundingError(
                        f"Flash setup funding reverted: {latest['err']}"
                    )
                if latest.get("confirmationStatus") in {"confirmed", "finalized"}:
                    return latest
            time.sleep(0.2)

        balance = self.wallet_state(owner)
        if int(balance.sol * LAMPORTS_PER_SOL) >= target_lamports:
            return {"confirmationStatus": "resolved_by_balance", "lastStatus": latest}
        raise FlashSetupFundingError(
            f"Flash setup funding remained ambiguous: {signature} last={latest}"
        )

    def _rpc_call(self, method: str, params: list[Any]) -> Any:
        payload = self._rpc(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        )
        if not isinstance(payload, dict) or payload.get("error"):
            raise FlashSetupFundingError(f"Solana RPC {method} failed: {payload}")
        return payload["result"]

    def _rpc(self, payload: object) -> Any:
        response = self._session.post(self._rpc_url, json=payload, timeout=12)
        response.raise_for_status()
        return response.json()
