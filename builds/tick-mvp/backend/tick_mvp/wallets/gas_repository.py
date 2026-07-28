from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import GasTopupStatus
from tick_mvp.infrastructure.custody import SecretCipher
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.memory_store import StoreNotFound
from tick_mvp.infrastructure.models import GasTopup, WalletAccount


ACTIVE_STATUSES = {
    GasTopupStatus.CREATED.value,
    GasTopupStatus.SIGNED.value,
    GasTopupStatus.BROADCAST.value,
    GasTopupStatus.UNKNOWN.value,
}


@dataclass(frozen=True, slots=True)
class GasTopupContext:
    topup_id: str
    user_id: str
    wallet_id: str
    wallet_address: str
    amount_native: Decimal
    status: GasTopupStatus
    tx_hash: str | None
    nonce: int | None
    signed_raw_transaction: str | None


class GasTopupRepository:
    def __init__(self, settings: Settings | None = None, session_factory=None) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory or create_session_factory()

    def create_or_load(
        self,
        *,
        user_id: str,
        wallet_id: str,
        wallet_address: str,
        amount_native: Decimal,
    ) -> GasTopupContext:
        now = _now()
        with session_scope(self._session_factory) as session:
            wallet = (
                session.query(WalletAccount)
                .filter(WalletAccount.id == wallet_id)
                .with_for_update()
                .one_or_none()
            )
            if wallet is None or wallet.user_id != user_id:
                raise StoreNotFound("gas top-up wallet not found")
            if wallet.address.lower() != wallet_address.lower():
                raise GasTopupConflict("gas top-up wallet address changed")
            topup = (
                session.query(GasTopup)
                .filter(
                    GasTopup.wallet_id == wallet_id,
                    GasTopup.status.in_(ACTIVE_STATUSES),
                )
                .order_by(GasTopup.created_at.asc())
                .first()
            )
            if topup is None:
                topup = GasTopup(
                    id=f"gas_topup_{uuid.uuid4().hex}",
                    user_id=user_id,
                    wallet_id=wallet_id,
                    amount_native=amount_native,
                    status=GasTopupStatus.CREATED.value,
                    payload={},
                    created_at=now,
                    updated_at=now,
                )
                session.add(topup)
                session.flush()
            return self._context(topup, wallet.address)

    def mark_signed(
        self,
        topup_id: str,
        *,
        tx_hash: str,
        nonce: int,
        signed_raw_transaction: str,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            topup = _topup_for_update(session, topup_id)
            _require_tx_hash(topup, tx_hash, allow_empty=True)
            topup.status = GasTopupStatus.SIGNED.value
            topup.tx_hash = tx_hash
            topup.nonce = nonce
            topup.payload = {
                **(topup.payload or {}),
                "signedRawTransactionCiphertext": self._cipher().encrypt(
                    signed_raw_transaction
                ).decode(),
                "signedAt": now.isoformat(),
            }
            topup.updated_at = now

    def mark_broadcast(self, topup_id: str, *, tx_hash: str, payload: dict) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            topup = _topup_for_update(session, topup_id)
            _require_tx_hash(topup, tx_hash)
            topup.status = GasTopupStatus.BROADCAST.value
            topup.payload = {
                **(topup.payload or {}),
                "broadcast": payload,
                "broadcastAt": now.isoformat(),
            }
            topup.updated_at = now

    def mark_confirmed(
        self,
        topup_id: str,
        *,
        tx_hash: str,
        gas_cost_native: Decimal,
        payload: dict,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            topup = _topup_for_update(session, topup_id)
            _require_tx_hash(topup, tx_hash)
            topup.status = GasTopupStatus.CONFIRMED.value
            topup.gas_cost_native = gas_cost_native
            topup.error = None
            topup.payload = {
                **(topup.payload or {}),
                "confirmation": payload,
                "confirmedAt": now.isoformat(),
            }
            topup.updated_at = now

    def mark_reverted(self, topup_id: str, *, tx_hash: str, payload: dict) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            topup = _topup_for_update(session, topup_id)
            _require_tx_hash(topup, tx_hash)
            topup.status = GasTopupStatus.FAILED.value
            topup.error = "platform gas top-up transaction reverted"
            topup.payload = {
                **(topup.payload or {}),
                "confirmation": payload,
                "failedAt": now.isoformat(),
            }
            topup.updated_at = now

    def mark_retryable_error(self, topup_id: str, error: str) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            topup = _topup_for_update(session, topup_id)
            topup.status = (
                GasTopupStatus.UNKNOWN.value
                if topup.tx_hash
                else GasTopupStatus.CREATED.value
            )
            topup.error = error[:500]
            topup.payload = {
                **(topup.payload or {}),
                "lastRetryableErrorAt": now.isoformat(),
            }
            topup.updated_at = now

    def _context(self, topup: GasTopup, wallet_address: str) -> GasTopupContext:
        encrypted_raw = (topup.payload or {}).get("signedRawTransactionCiphertext")
        signed_raw = (
            self._cipher().decrypt(str(encrypted_raw).encode())
            if encrypted_raw
            else None
        )
        return GasTopupContext(
            topup_id=topup.id,
            user_id=topup.user_id,
            wallet_id=topup.wallet_id,
            wallet_address=wallet_address,
            amount_native=Decimal(topup.amount_native),
            status=GasTopupStatus(topup.status),
            tx_hash=topup.tx_hash,
            nonce=topup.nonce,
            signed_raw_transaction=signed_raw,
        )

    def _cipher(self) -> SecretCipher:
        return SecretCipher(self._settings.custody_private_key_encryption_key)


class GasTopupConflict(RuntimeError):
    pass


def _topup_for_update(session, topup_id: str) -> GasTopup:
    topup = (
        session.query(GasTopup)
        .filter(GasTopup.id == topup_id)
        .with_for_update()
        .one_or_none()
    )
    if topup is None:
        raise StoreNotFound("gas top-up not found")
    return topup


def _require_tx_hash(
    topup: GasTopup,
    tx_hash: str,
    *,
    allow_empty: bool = False,
) -> None:
    if allow_empty and not topup.tx_hash:
        return
    if not topup.tx_hash or topup.tx_hash.lower() != tx_hash.lower():
        raise GasTopupConflict("gas top-up transaction hash changed")


def _now() -> datetime:
    return datetime.now(UTC)
