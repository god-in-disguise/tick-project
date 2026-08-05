from __future__ import annotations

import base64
import struct
import time
from decimal import Decimal
from typing import Any, Callable

import requests
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.message import Message
from solders.pubkey import Pubkey
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from solders.token import ID as TOKEN_PROGRAM_ID
from solders.token.associated import get_associated_token_address
from solders.transaction import Transaction

from tick_mvp.core.config import Settings
from tick_mvp.venues.flash.client import FlashClient
from tick_mvp.venues.flash.constants import USDC_MINT, USD_DECIMALS
from tick_mvp.venues.flash.signing import (
    PreparedFlashTransaction,
    keypair_from_secret,
    sign_built_transaction_multi,
)
from tick_mvp.wallets.arbitrum import (
    WalletTransferResult,
    WithdrawalRejected,
    WithdrawalRetryable,
)
from tick_mvp.wallets.repository import WithdrawalContext


ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)
LAMPORTS_PER_SOL = Decimal(1_000_000_000)
USDC_SCALE = 10**USD_DECIMALS

PreparedHandler = Callable[[str, int | None, str], None]
BroadcastHandler = Callable[[str, dict[str, Any]], None]
VenuePreparedHandler = Callable[[str, str], None]
VenueBroadcastHandler = Callable[[str, dict[str, Any]], None]


class SolanaUSDCWithdrawalExecutor:
    """Moves USDC out of Flash custody, then to the requested Solana wallet."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._rpc_url = settings.solana_rpc_url
        self._session = requests.Session()
        self._session.headers.update({"user-agent": "tick-mvp-flash-withdrawal/0.1"})
        self._flash = FlashClient(settings.flash_api_url)
        self._fee_payer = (
            keypair_from_secret(settings.flash_setup_wallet_private_key)
            if settings.flash_setup_wallet_private_key
            else None
        )

    def close(self) -> None:
        self._session.close()
        self._flash.close()

    def transfer(
        self,
        context: WithdrawalContext,
        *,
        on_venue_prepared: VenuePreparedHandler,
        on_venue_broadcast: VenueBroadcastHandler,
        on_prepared: PreparedHandler,
        on_broadcast: BroadcastHandler,
    ) -> WalletTransferResult:
        if context.asset.upper() != "USDC":
            raise WithdrawalRejected(f"unsupported withdrawal asset: {context.asset}")
        if not self._rpc_url:
            raise WithdrawalRetryable("SOLANA_RPC_URL is required for Flash withdrawals")
        if self._fee_payer is None:
            raise WithdrawalRetryable(
                "FLASH_SETUP_WALLET_PRIVATE_KEY is required for Flash withdrawals"
            )

        owner = keypair_from_secret(context.private_key_hex)
        if str(owner.pubkey()) != context.wallet_address:
            raise WithdrawalRejected("custody key does not match withdrawal wallet")
        try:
            destination_owner = Pubkey.from_string(context.destination_address)
        except ValueError as exc:
            raise WithdrawalRejected("destination is not a valid Solana address") from exc
        if destination_owner == owner.pubkey():
            raise WithdrawalRejected("destination must be an external Solana wallet")

        amount_units = _amount_units(context.amount)
        mint = Pubkey.from_string(USDC_MINT)
        source_ata = get_associated_token_address(owner.pubkey(), mint)
        wallet_units = self._token_balance_units(source_ata)
        venue_signature = context.venue_stage_tx_hash

        if wallet_units < amount_units:
            prepared = self._prepare_venue_withdrawal(
                context,
                owner,
                amount_units - wallet_units,
            )
            venue_signature = prepared.signature
            if context.venue_stage_signed_transaction is None:
                on_venue_prepared(
                    prepared.signature,
                    prepared.signed_transaction_base64,
                )
            # Flash's public simulator has returned false negatives for this
            # transaction. The deterministic signature is persisted first and
            # authoritative Solana confirmation still gates the next stage.
            submission = self._flash.submit_exact(prepared, skip_preflight=True)
            on_venue_broadcast(prepared.signature, submission)
            self._wait_for_signature(prepared.signature)
            wallet_units = self._wait_for_token_balance(source_ata, amount_units)

        if wallet_units < amount_units:
            raise WithdrawalRetryable("Flash withdrawal has not released enough USDC yet")

        started = time.perf_counter()
        if context.signed_raw_transaction:
            prepared_transfer = _prepared_from_stored(
                context.tx_hash,
                context.signed_raw_transaction,
            )
        else:
            prepared_transfer = self._prepare_token_transfer(
                owner=owner,
                destination_owner=destination_owner,
                amount_units=amount_units,
            )
            on_prepared(
                prepared_transfer.signature,
                None,
                prepared_transfer.signed_transaction_base64,
            )

        submission = self._send_exact(prepared_transfer)
        on_broadcast(prepared_transfer.signature, submission)
        confirmation = self._wait_for_signature(prepared_transfer.signature)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        fee_lamports = int(confirmation.get("feeLamports") or 0)
        return WalletTransferResult(
            status="confirmed",
            tx_hash=prepared_transfer.signature,
            nonce=0,
            block_number=int(confirmation.get("slot") or 0),
            gas_used=0,
            effective_gas_price=0,
            gas_cost_native=Decimal(fee_lamports) / LAMPORTS_PER_SOL,
            payload={
                "network": "solana",
                "venue": "flash",
                "venueWithdrawalSignature": venue_signature,
                "destinationOwner": str(destination_owner),
                "destinationTokenAccount": str(
                    get_associated_token_address(destination_owner, mint)
                ),
                "feePayer": str(self._fee_payer.pubkey()),
                "feeLamports": fee_lamports,
                "confirmation": confirmation,
                "submission": submission,
                "timingMs": {"total": elapsed_ms},
            },
        )

    def _prepare_venue_withdrawal(
        self,
        context: WithdrawalContext,
        owner,
        release_units: int,
    ) -> PreparedFlashTransaction:
        if context.venue_stage_signed_transaction:
            return _prepared_from_stored(
                context.venue_stage_tx_hash,
                context.venue_stage_signed_transaction,
            )
        built = self._flash.post(
            "/transaction-builder/withdraw",
            {
                "owner": str(owner.pubkey()),
                "tokenSymbol": "USDC",
                "amount": format(
                    Decimal(release_units) / Decimal(USDC_SCALE),
                    "f",
                ),
                "feePayer": str(self._fee_payer.pubkey()),
                "feePayerTopUpLamports": 0,
            },
        )
        if built.get("custodySettlementRequired"):
            raise WithdrawalRetryable("Flash custody settlement is still pending")
        encoded = built.get("transactionBase64")
        if not encoded:
            raise WithdrawalRetryable("Flash withdrawal builder returned no transaction")
        return sign_built_transaction_multi(encoded, [owner, self._fee_payer])

    def _prepare_token_transfer(
        self,
        *,
        owner,
        destination_owner: Pubkey,
        amount_units: int,
    ) -> PreparedFlashTransaction:
        mint = Pubkey.from_string(USDC_MINT)
        source_ata = get_associated_token_address(owner.pubkey(), mint)
        destination_ata = get_associated_token_address(destination_owner, mint)
        create_destination = Instruction(
            ASSOCIATED_TOKEN_PROGRAM_ID,
            bytes([1]),
            [
                AccountMeta(self._fee_payer.pubkey(), True, True),
                AccountMeta(destination_ata, False, True),
                AccountMeta(destination_owner, False, False),
                AccountMeta(mint, False, False),
                AccountMeta(SYSTEM_PROGRAM_ID, False, False),
                AccountMeta(TOKEN_PROGRAM_ID, False, False),
            ],
        )
        transfer_checked = Instruction(
            TOKEN_PROGRAM_ID,
            bytes([12]) + struct.pack("<Q", amount_units) + bytes([USD_DECIMALS]),
            [
                AccountMeta(source_ata, False, True),
                AccountMeta(mint, False, False),
                AccountMeta(destination_ata, False, True),
                AccountMeta(owner.pubkey(), True, False),
            ],
        )
        blockhash = Hash.from_string(
            self._rpc_call(
                "getLatestBlockhash",
                [{"commitment": "confirmed"}],
            )["value"]["blockhash"]
        )
        transaction = Transaction(
            [self._fee_payer, owner],
            Message([create_destination, transfer_checked], self._fee_payer.pubkey()),
            blockhash,
        )
        return PreparedFlashTransaction(
            signature=str(transaction.signatures[0]),
            signed_transaction_base64=base64.b64encode(bytes(transaction)).decode("ascii"),
            quote={},
        )

    def _send_exact(self, prepared: PreparedFlashTransaction) -> dict[str, Any]:
        try:
            remote = self._rpc_call(
                "sendTransaction",
                [
                    prepared.signed_transaction_base64,
                    {
                        "encoding": "base64",
                        "skipPreflight": False,
                        "preflightCommitment": "confirmed",
                        "maxRetries": 3,
                    },
                ],
            )
        except requests.RequestException as exc:
            return {
                "signature": prepared.signature,
                "transportAmbiguous": True,
                "error": f"{type(exc).__name__}: {exc}",
            }
        if remote != prepared.signature:
            raise WithdrawalRetryable(
                f"Solana signature mismatch: local={prepared.signature} remote={remote}"
            )
        return {"signature": remote}

    def _wait_for_signature(
        self,
        signature: str,
        *,
        timeout_seconds: float = 45,
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
                    raise WithdrawalRejected(
                        f"Solana withdrawal transaction failed: {latest['err']}"
                    )
                if latest.get("confirmationStatus") in {"confirmed", "finalized"}:
                    transaction = self._rpc_call(
                        "getTransaction",
                        [
                            signature,
                            {
                                "commitment": "confirmed",
                                "encoding": "json",
                                "maxSupportedTransactionVersion": 0,
                            },
                        ],
                    )
                    return {
                        **latest,
                        "slot": (transaction or {}).get("slot"),
                        "feeLamports": ((transaction or {}).get("meta") or {}).get("fee"),
                    }
            time.sleep(0.2)
        raise WithdrawalRetryable(
            f"Solana withdrawal remained ambiguous: {signature} last={latest}"
        )

    def _wait_for_token_balance(
        self,
        token_account: Pubkey,
        minimum_units: int,
        *,
        timeout_seconds: float = 30,
    ) -> int:
        started = time.monotonic()
        latest = 0
        while time.monotonic() - started < timeout_seconds:
            latest = self._token_balance_units(token_account)
            if latest >= minimum_units:
                return latest
            time.sleep(0.2)
        return latest

    def _token_balance_units(self, token_account: Pubkey) -> int:
        try:
            result = self._rpc_call(
                "getTokenAccountBalance",
                [str(token_account), {"commitment": "confirmed"}],
            )
        except WithdrawalRetryable as exc:
            if "Invalid param" in str(exc) or "could not find account" in str(exc):
                return 0
            raise
        return int(result["value"]["amount"])

    def _rpc_call(self, method: str, params: list[Any]) -> Any:
        try:
            response = self._session.post(
                self._rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=12,
            )
            response.raise_for_status()
        except requests.RequestException:
            raise
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("error"):
            raise WithdrawalRetryable(f"Solana RPC {method} failed: {payload}")
        return payload["result"]


def _amount_units(amount: Decimal) -> int:
    scaled = amount * Decimal(USDC_SCALE)
    if scaled != scaled.to_integral_value():
        raise WithdrawalRejected("USDC amount supports at most 6 decimal places")
    units = int(scaled)
    if units <= 0:
        raise WithdrawalRejected("withdrawal amount must be positive")
    return units


def _prepared_from_stored(
    signature: str | None,
    signed_transaction: str,
) -> PreparedFlashTransaction:
    if not signature:
        raise WithdrawalRetryable("stored Solana transaction is missing its signature")
    return PreparedFlashTransaction(
        signature=signature,
        signed_transaction_base64=signed_transaction,
        quote={},
    )
