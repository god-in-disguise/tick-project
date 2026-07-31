from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import GasSweepStatus, GasTopupStatus
from tick_mvp.infrastructure.custody import SecretCipher
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.memory_store import StoreNotFound
from tick_mvp.infrastructure.models import (
    GasSweep,
    GasTopup,
    LedgerEvent,
    WalletAccount,
)


ACTIVE_STATUSES = {
    GasSweepStatus.CREATED.value,
    GasSweepStatus.SIGNED.value,
    GasSweepStatus.BROADCAST.value,
    GasSweepStatus.UNKNOWN.value,
}
LEGACY_USER_WALLET_OPERATIONS = {"approve", "set_delegate", "withdrawal"}


@dataclass(frozen=True, slots=True)
class GasSweepContext:
    sweep_id: str
    user_id: str
    wallet_id: str
    wallet_address: str
    amount_native: Decimal
    status: GasSweepStatus
    tx_hash: str | None
    nonce: int | None
    signed_raw_transaction: str | None


class GasSweepRepository:
    def __init__(self, settings: Settings | None = None, session_factory=None) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory or create_session_factory()

    def load_active(
        self,
        *,
        user_id: str,
        wallet_id: str,
        wallet_address: str,
    ) -> GasSweepContext | None:
        with session_scope(self._session_factory) as session:
            sweep = (
                session.query(GasSweep)
                .filter(
                    GasSweep.user_id == user_id,
                    GasSweep.wallet_id == wallet_id,
                    GasSweep.status.in_(ACTIVE_STATUSES),
                )
                .order_by(GasSweep.created_at.asc())
                .first()
            )
            return self._context(sweep, wallet_address) if sweep is not None else None

    def recoverable_native(
        self,
        *,
        user_id: str,
        wallet_id: str,
        wallet_address: str,
    ) -> Decimal:
        with session_scope(self._session_factory) as session:
            funded = _sum_amounts(
                session.query(GasTopup.amount_native).filter(
                    GasTopup.user_id == user_id,
                    GasTopup.wallet_id == wallet_id,
                    GasTopup.status == GasTopupStatus.CONFIRMED.value,
                )
            )
            returned = _sum_amounts(
                session.query(GasSweep.amount_native, GasSweep.gas_cost_native).filter(
                    GasSweep.user_id == user_id,
                    GasSweep.wallet_id == wallet_id,
                    GasSweep.status == GasSweepStatus.CONFIRMED.value,
                )
            )
            consumed = Decimal(0)
            gas_events = session.query(LedgerEvent.payload).filter(
                LedgerEvent.user_id == user_id,
                LedgerEvent.event_type == "gas_charge",
            )
            for (payload,) in gas_events:
                data = payload or {}
                payer = str(data.get("gasPayerAddress") or "").lower()
                operation = str(data.get("operation") or "")
                if payer == wallet_address.lower() or (
                    not payer and operation in LEGACY_USER_WALLET_OPERATIONS
                ):
                    consumed += Decimal(str(data.get("nativeGasCost") or 0))
            return max(Decimal(0), funded - returned - consumed)

    def create_or_load(
        self,
        *,
        user_id: str,
        wallet_id: str,
        wallet_address: str,
        amount_native: Decimal,
    ) -> GasSweepContext:
        now = _now()
        with session_scope(self._session_factory) as session:
            wallet = session.get(WalletAccount, wallet_id, with_for_update=True)
            if wallet is None or wallet.user_id != user_id:
                raise StoreNotFound("gas sweep wallet not found")
            if wallet.address.lower() != wallet_address.lower():
                raise GasSweepConflict("gas sweep wallet address changed")
            sweep = (
                session.query(GasSweep)
                .filter(
                    GasSweep.wallet_id == wallet_id,
                    GasSweep.status.in_(ACTIVE_STATUSES),
                )
                .order_by(GasSweep.created_at.asc())
                .first()
            )
            if sweep is None:
                sweep = GasSweep(
                    id=f"gas_sweep_{uuid.uuid4().hex}",
                    user_id=user_id,
                    wallet_id=wallet_id,
                    amount_native=amount_native,
                    status=GasSweepStatus.CREATED.value,
                    payload={"destination": "platform_gas_wallet"},
                    created_at=now,
                    updated_at=now,
                )
                session.add(sweep)
                session.flush()
            return self._context(sweep, wallet.address)

    def mark_signed(
        self,
        sweep_id: str,
        *,
        tx_hash: str,
        nonce: int,
        signed_raw_transaction: str,
        amount_native: Decimal,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            sweep = _sweep_for_update(session, sweep_id)
            _require_tx_hash(sweep, tx_hash, allow_empty=True)
            sweep.status = GasSweepStatus.SIGNED.value
            sweep.amount_native = amount_native
            sweep.tx_hash = tx_hash
            sweep.nonce = nonce
            sweep.payload = {
                **(sweep.payload or {}),
                "signedRawTransactionCiphertext": self._cipher().encrypt(
                    signed_raw_transaction
                ).decode(),
                "signedAt": now.isoformat(),
            }
            sweep.updated_at = now

    def mark_broadcast(self, sweep_id: str, *, tx_hash: str, payload: dict) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            sweep = _sweep_for_update(session, sweep_id)
            _require_tx_hash(sweep, tx_hash)
            sweep.status = GasSweepStatus.BROADCAST.value
            sweep.payload = {
                **(sweep.payload or {}),
                "broadcast": payload,
                "broadcastAt": now.isoformat(),
            }
            sweep.updated_at = now

    def mark_confirmed(
        self,
        sweep_id: str,
        *,
        tx_hash: str,
        gas_cost_native: Decimal,
        payload: dict,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            sweep = _sweep_for_update(session, sweep_id)
            _require_tx_hash(sweep, tx_hash)
            sweep.status = GasSweepStatus.CONFIRMED.value
            sweep.gas_cost_native = gas_cost_native
            sweep.error = None
            sweep.payload = {
                **(sweep.payload or {}),
                "confirmation": payload,
                "confirmedAt": now.isoformat(),
            }
            sweep.updated_at = now

    def mark_reverted(self, sweep_id: str, *, tx_hash: str, payload: dict) -> None:
        self._mark_failed(
            sweep_id,
            error="platform gas sweep transaction reverted",
            tx_hash=tx_hash,
            payload=payload,
        )

    def mark_retryable_error(self, sweep_id: str, error: str) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            sweep = _sweep_for_update(session, sweep_id)
            sweep.status = (
                GasSweepStatus.UNKNOWN.value
                if sweep.tx_hash
                else GasSweepStatus.CREATED.value
            )
            sweep.error = error[:500]
            sweep.payload = {
                **(sweep.payload or {}),
                "lastRetryableErrorAt": now.isoformat(),
            }
            sweep.updated_at = now

    def mark_superseded(self, sweep_id: str, *, tx_hash: str, nonce: int) -> None:
        self._mark_failed(
            sweep_id,
            error=f"gas sweep nonce {nonce} was consumed by another transaction",
            tx_hash=tx_hash,
            payload={"nonce": nonce},
        )

    def _mark_failed(
        self,
        sweep_id: str,
        *,
        error: str,
        tx_hash: str,
        payload: dict,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            sweep = _sweep_for_update(session, sweep_id)
            _require_tx_hash(sweep, tx_hash)
            sweep.status = GasSweepStatus.FAILED.value
            sweep.error = error
            sweep.payload = {
                **(sweep.payload or {}),
                "failure": payload,
                "failedAt": now.isoformat(),
            }
            sweep.updated_at = now

    def _context(self, sweep: GasSweep, wallet_address: str) -> GasSweepContext:
        encrypted_raw = (sweep.payload or {}).get("signedRawTransactionCiphertext")
        signed_raw = (
            self._cipher().decrypt(str(encrypted_raw).encode())
            if encrypted_raw
            else None
        )
        return GasSweepContext(
            sweep_id=sweep.id,
            user_id=sweep.user_id,
            wallet_id=sweep.wallet_id,
            wallet_address=wallet_address,
            amount_native=Decimal(sweep.amount_native),
            status=GasSweepStatus(sweep.status),
            tx_hash=sweep.tx_hash,
            nonce=sweep.nonce,
            signed_raw_transaction=signed_raw,
        )

    def _cipher(self) -> SecretCipher:
        return SecretCipher(self._settings.custody_private_key_encryption_key)


class GasSweepConflict(RuntimeError):
    pass


def _sum_amounts(query) -> Decimal:
    total = Decimal(0)
    for row in query:
        for value in row:
            total += Decimal(value or 0)
    return total


def _sweep_for_update(session, sweep_id: str) -> GasSweep:
    sweep = session.get(GasSweep, sweep_id, with_for_update=True)
    if sweep is None:
        raise StoreNotFound("gas sweep not found")
    return sweep


def _require_tx_hash(
    sweep: GasSweep,
    tx_hash: str,
    *,
    allow_empty: bool = False,
) -> None:
    if allow_empty and not sweep.tx_hash:
        return
    if not sweep.tx_hash or sweep.tx_hash.lower() != tx_hash.lower():
        raise GasSweepConflict("gas sweep transaction hash changed")


def _now() -> datetime:
    return datetime.now(UTC)
