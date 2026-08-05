from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import PositionStatus, WalletStatus, WithdrawalStatus
from tick_mvp.infrastructure.custody import PrivateKeyCipher, SecretCipher
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.memory_store import StoreNotFound
from tick_mvp.infrastructure.models import LedgerEvent, Position, WalletAccount, Withdrawal
from tick_mvp.venues.flash.constants import SOLANA_MAINNET_CHAIN_ID


@dataclass(frozen=True, slots=True)
class WithdrawalContext:
    withdrawal_id: str
    user_id: str
    wallet_id: str
    chain_id: int
    wallet_address: str
    private_key_hex: str
    asset: str
    amount: Decimal
    destination_address: str
    status: WithdrawalStatus
    tx_hash: str | None
    nonce: int | None
    signed_raw_transaction: str | None
    venue_stage_tx_hash: str | None = None
    venue_stage_signed_transaction: str | None = None
    reserved_gas_charges_usdc: Decimal = Decimal(0)


class WithdrawalRepository:
    def __init__(self, settings: Settings | None = None, session_factory=None) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory or create_session_factory()

    def load(self, withdrawal_id: str) -> WithdrawalContext:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = (
                session.query(Withdrawal)
                .filter(Withdrawal.id == withdrawal_id)
                .with_for_update()
                .one_or_none()
            )
            if withdrawal is None:
                raise StoreNotFound("withdrawal not found")
            wallet = session.get(WalletAccount, withdrawal.wallet_id)
            if wallet is None or wallet.status != WalletStatus.ACTIVE.value:
                raise StoreNotFound("active wallet not found")
            if not wallet.encrypted_private_key:
                raise StoreNotFound("wallet has no encrypted private key")

            status = WithdrawalStatus(withdrawal.status)
            if status == WithdrawalStatus.REQUESTED:
                if _active_position_exists(session, withdrawal.user_id):
                    raise WithdrawalBlocked("withdrawal cannot execute while a position is active")
                withdrawal.status = WithdrawalStatus.VALIDATED.value
                withdrawal.updated_at = now
                status = WithdrawalStatus.VALIDATED

            payload = dict(withdrawal.payload or {})
            encrypted_raw = payload.get("signedRawTransactionCiphertext")
            signed_raw = (
                self._cipher().decrypt(str(encrypted_raw).encode())
                if encrypted_raw
                else None
            )
            encrypted_venue_raw = payload.get("venueStageSignedTransactionCiphertext")
            venue_signed_raw = (
                self._cipher().decrypt(str(encrypted_venue_raw).encode())
                if encrypted_venue_raw
                else None
            )
            private_key = PrivateKeyCipher(
                self._settings.custody_private_key_encryption_key
            ).decrypt(wallet.encrypted_private_key)
            return WithdrawalContext(
                withdrawal_id=withdrawal.id,
                user_id=withdrawal.user_id,
                wallet_id=wallet.id,
                chain_id=wallet.chain_id,
                wallet_address=wallet.address,
                private_key_hex=private_key,
                asset=withdrawal.asset,
                amount=Decimal(withdrawal.amount),
                destination_address=withdrawal.destination_address,
                status=status,
                tx_hash=withdrawal.tx_hash,
                nonce=withdrawal.nonce,
                signed_raw_transaction=signed_raw,
                venue_stage_tx_hash=payload.get("venueStageTxHash"),
                venue_stage_signed_transaction=venue_signed_raw,
                reserved_gas_charges_usdc=_reserved_gas_charges(
                    session,
                    withdrawal.user_id,
                ),
            )

    def mark_venue_stage_prepared(
        self,
        withdrawal_id: str,
        *,
        tx_hash: str,
        signed_raw_transaction: str,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            payload = dict(withdrawal.payload or {})
            previous = payload.get("venueStageTxHash")
            if previous and previous != tx_hash:
                raise WithdrawalConflict("Flash withdrawal stage transaction hash changed")
            withdrawal.payload = {
                **payload,
                "venueStageTxHash": tx_hash,
                "venueStageSignedTransactionCiphertext": self._cipher().encrypt(
                    signed_raw_transaction
                ).decode(),
                "venueStagePreparedAt": now.isoformat(),
            }
            withdrawal.updated_at = now

    def mark_venue_stage_broadcast(
        self,
        withdrawal_id: str,
        *,
        tx_hash: str,
        payload: dict,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            current = dict(withdrawal.payload or {})
            if current.get("venueStageTxHash") != tx_hash:
                raise WithdrawalConflict("Flash withdrawal stage transaction hash changed")
            withdrawal.payload = {
                **current,
                "venueStageBroadcast": payload,
                "venueStageBroadcastAt": now.isoformat(),
            }
            withdrawal.updated_at = now

    def mark_signed(
        self,
        withdrawal_id: str,
        *,
        tx_hash: str,
        nonce: int | None,
        signed_raw_transaction: str,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            if withdrawal.tx_hash and withdrawal.tx_hash.lower() != tx_hash.lower():
                raise WithdrawalConflict("withdrawal already has a different transaction hash")
            withdrawal.status = WithdrawalStatus.SIGNED.value
            withdrawal.tx_hash = tx_hash
            withdrawal.nonce = nonce
            withdrawal.payload = {
                **(withdrawal.payload or {}),
                "signedRawTransactionCiphertext": self._cipher().encrypt(
                    signed_raw_transaction
                ).decode(),
                "signedAt": now.isoformat(),
            }
            withdrawal.updated_at = now

    def _cipher(self) -> SecretCipher:
        return SecretCipher(self._settings.custody_private_key_encryption_key)

    def mark_broadcast(self, withdrawal_id: str, *, tx_hash: str, payload: dict) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            _require_tx_hash(withdrawal, tx_hash)
            withdrawal.status = WithdrawalStatus.BROADCAST.value
            withdrawal.payload = {
                **(withdrawal.payload or {}),
                "broadcast": payload,
                "broadcastAt": now.isoformat(),
            }
            withdrawal.updated_at = now

    def mark_confirmed(
        self,
        withdrawal_id: str,
        *,
        tx_hash: str,
        gas_cost_native: Decimal,
        payload: dict,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            _require_tx_hash(withdrawal, tx_hash)
            wallet = session.get(WalletAccount, withdrawal.wallet_id)
            if wallet is None:
                raise StoreNotFound("withdrawal wallet not found")
            withdrawal.status = WithdrawalStatus.CONFIRMED.value
            withdrawal.gas_cost_native = gas_cost_native
            withdrawal.error = None
            withdrawal.payload = {
                **(withdrawal.payload or {}),
                "confirmation": payload,
                "confirmedAt": now.isoformat(),
            }
            withdrawal.updated_at = now
            existing_event = (
                session.query(LedgerEvent.id)
                .filter(
                    LedgerEvent.withdrawal_id == withdrawal.id,
                    LedgerEvent.event_type == "withdrawal_confirmed",
                )
                .first()
            )
            if existing_event is None:
                session.add(
                    LedgerEvent(
                        id=f"ledger_{uuid.uuid4().hex}",
                        user_id=withdrawal.user_id,
                        position_id=None,
                        event_type="withdrawal_confirmed",
                        asset=withdrawal.asset,
                        amount=-Decimal(withdrawal.amount),
                        source=(
                            "solana_wallet"
                            if wallet.chain_id == SOLANA_MAINNET_CHAIN_ID
                            else "arbitrum_wallet"
                        ),
                        execution_attempt_id=None,
                        withdrawal_id=withdrawal.id,
                        payload={"txHash": tx_hash},
                        created_at=now,
                    )
                )

    def mark_reverted(self, withdrawal_id: str, *, tx_hash: str, payload: dict) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            _require_tx_hash(withdrawal, tx_hash)
            withdrawal.status = WithdrawalStatus.FAILED.value
            withdrawal.error = "USDC transfer transaction reverted"
            withdrawal.payload = {
                **(withdrawal.payload or {}),
                "confirmation": payload,
                "failedAt": now.isoformat(),
            }
            withdrawal.updated_at = now

    def mark_failed(self, withdrawal_id: str, error: str) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            withdrawal.status = WithdrawalStatus.FAILED.value
            withdrawal.error = error[:500]
            withdrawal.updated_at = now

    def mark_retryable_error(self, withdrawal_id: str, error: str) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            withdrawal = _withdrawal_for_update(session, withdrawal_id)
            withdrawal.status = (
                WithdrawalStatus.UNKNOWN.value
                if withdrawal.tx_hash
                else WithdrawalStatus.VALIDATED.value
            )
            withdrawal.error = error[:500]
            withdrawal.payload = {
                **(withdrawal.payload or {}),
                "lastRetryableErrorAt": now.isoformat(),
            }
            withdrawal.updated_at = now


class WithdrawalBlocked(RuntimeError):
    pass


class WithdrawalConflict(RuntimeError):
    pass


def _withdrawal_for_update(session, withdrawal_id: str) -> Withdrawal:
    withdrawal = (
        session.query(Withdrawal)
        .filter(Withdrawal.id == withdrawal_id)
        .with_for_update()
        .one_or_none()
    )
    if withdrawal is None:
        raise StoreNotFound("withdrawal not found")
    return withdrawal


def _require_tx_hash(withdrawal: Withdrawal, tx_hash: str) -> None:
    if not withdrawal.tx_hash or withdrawal.tx_hash.lower() != tx_hash.lower():
        raise WithdrawalConflict("withdrawal transaction hash changed")


def _active_position_exists(session, user_id: str) -> bool:
    return (
        session.query(Position.id)
        .filter(
            Position.user_id == user_id,
            Position.status.in_(
                [
                    PositionStatus.OPENING.value,
                    PositionStatus.OPEN.value,
                    PositionStatus.CLOSING.value,
                    PositionStatus.UNKNOWN.value,
                ]
            ),
        )
        .first()
        is not None
    )


def _reserved_gas_charges(session, user_id: str) -> Decimal:
    from sqlalchemy import func

    total = (
        session.query(func.coalesce(func.sum(LedgerEvent.amount), 0))
        .filter(
            LedgerEvent.user_id == user_id,
            LedgerEvent.event_type == "gas_charge",
            LedgerEvent.asset == "USDC",
        )
        .scalar()
    )
    return max(Decimal(0), -Decimal(total or 0))


def _now() -> datetime:
    return datetime.now(UTC)
