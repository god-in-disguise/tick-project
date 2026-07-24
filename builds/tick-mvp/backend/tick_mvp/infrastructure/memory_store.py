from __future__ import annotations

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from tick_mvp.domain.schemas import (
    AcceptedTradeResponse,
    CloseRequest,
    DepositAddressResponse,
    ExecutionAttemptResponse,
    OpenRequest,
    PositionResponse,
    QuoteRequest,
    QuoteResponse,
    ReconciliationResponse,
    StateResponse,
    TradeIntentResponse,
    UserResponse,
    WalletAccountResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)
from tick_mvp.domain.states import (
    AuthProvider,
    ExecutionAttemptStatus,
    PositionStatus,
    ReconciliationStatus,
    TradeAction,
    TradeIntentStatus,
    UserStatus,
    WalletStatus,
    WalletType,
    WithdrawalStatus,
)


class StoreConflict(Exception):
    pass


class StoreNotFound(Exception):
    pass


@dataclass(slots=True)
class QuoteRecord:
    response: QuoteResponse


@dataclass(slots=True)
class TradeBundle:
    intent: TradeIntentResponse
    execution: ExecutionAttemptResponse
    position: PositionResponse | None = None


@dataclass
class MemoryStore:
    default_venue: str
    quote_ttl_seconds: int = 5
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _quotes: dict[str, QuoteRecord] = field(default_factory=dict)
    _users: dict[str, UserResponse] = field(default_factory=dict)
    _user_by_provider: dict[tuple[AuthProvider, str], str] = field(default_factory=dict)
    _wallets: dict[str, WalletAccountResponse] = field(default_factory=dict)
    _wallet_by_user: dict[str, str] = field(default_factory=dict)
    _intents: dict[str, TradeIntentResponse] = field(default_factory=dict)
    _executions: dict[str, ExecutionAttemptResponse] = field(default_factory=dict)
    _positions: dict[str, PositionResponse] = field(default_factory=dict)
    _reconciliations: dict[str, ReconciliationResponse] = field(default_factory=dict)
    _withdrawals: dict[str, WithdrawalResponse] = field(default_factory=dict)
    _idempotency: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    _withdrawal_idempotency: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)

    def upsert_google_user(
        self,
        *,
        provider_subject: str,
        email: str,
        display_name: str | None,
        avatar_url: str | None,
        chain_id: int,
        custody_provider: str,
    ) -> tuple[UserResponse, WalletAccountResponse]:
        now = _now()
        with self._lock:
            key = (AuthProvider.GOOGLE, provider_subject)
            existing_user_id = self._user_by_provider.get(key)
            if existing_user_id is None:
                user = UserResponse(
                    id=_id("user"),
                    authProvider=AuthProvider.GOOGLE,
                    providerSubject=provider_subject,
                    email=email.lower(),
                    displayName=display_name,
                    avatarUrl=avatar_url,
                    status=UserStatus.ACTIVE,
                    createdAt=now,
                    lastLoginAt=now,
                )
                self._users[user.id] = user
                self._user_by_provider[key] = user.id
            else:
                previous = self._users[existing_user_id]
                user = previous.model_copy(
                    update={
                        "email": email.lower(),
                        "displayName": display_name,
                        "avatarUrl": avatar_url,
                        "lastLoginAt": now,
                    }
                )
                self._users[user.id] = user

            wallet = self._wallet_for_user(user.id, chain_id=chain_id, custody_provider=custody_provider, now=now)
            return user, wallet

    def user(self, user_id: str) -> UserResponse:
        with self._lock:
            user = self._users.get(user_id)
        if user is None:
            raise StoreNotFound("user not found")
        return user

    def wallet_for_user(self, user_id: str) -> WalletAccountResponse:
        with self._lock:
            wallet_id = self._wallet_by_user.get(user_id)
            wallet = self._wallets.get(wallet_id or "")
        if wallet is None:
            raise StoreNotFound("wallet not found")
        return wallet

    def deposit_address(self, user_id: str) -> DepositAddressResponse:
        wallet = self.wallet_for_user(user_id)
        return DepositAddressResponse(chainId=wallet.chainId, walletId=wallet.id, address=wallet.address)

    def request_withdrawal(self, user_id: str, request: WithdrawalRequest) -> WithdrawalResponse:
        payload_hash = _hash_payload(request.model_dump(mode="json"))
        with self._lock:
            existing = self._withdrawal_idempotency.get((user_id, request.idempotencyKey))
            if existing is not None:
                previous_hash, withdrawal_id = existing
                if previous_hash != payload_hash:
                    raise StoreConflict("idempotency key reused with different payload")
                return self._withdrawals[withdrawal_id]

            wallet_id = self._wallet_by_user.get(user_id)
            if wallet_id is None:
                raise StoreNotFound("wallet not found")
            now = _now()
            withdrawal = WithdrawalResponse(
                id=_id("withdrawal"),
                userId=user_id,
                walletId=wallet_id,
                asset=request.asset.upper(),
                amount=request.amount,
                destinationAddress=request.destinationAddress,
                status=WithdrawalStatus.REQUESTED,
                txHash=None,
                createdAt=now,
                updatedAt=now,
            )
            self._withdrawals[withdrawal.id] = withdrawal
            self._withdrawal_idempotency[(user_id, request.idempotencyKey)] = (payload_hash, withdrawal.id)
            return withdrawal

    def create_quote(self, user_id: str, request: QuoteRequest) -> QuoteResponse:
        now = _now()
        quote_id = _id("quote")
        notional = request.ticketUsd * request.leverage
        # Placeholder until venue quote extraction. Keep it explicit and conservative.
        estimated_open = notional * Decimal("0.0002")
        estimated_close = notional * Decimal("0.0002")
        response = QuoteResponse(
            quoteId=quote_id,
            userId=user_id,
            venue=self.default_venue,
            market=_market(request.market),
            side=request.side,
            ticketUsd=request.ticketUsd,
            leverage=request.leverage,
            notionalUsd=notional,
            maxLossUsd=request.maxLossUsd,
            estimatedOpenCostUsd=estimated_open,
            estimatedCloseCostUsd=estimated_close,
            estimatedRoundTripCostUsd=estimated_open + estimated_close,
            liquidationPrice=None,
            stopLossPrice=None,
            openingAllowed=True,
            riskDecisionId=_id("risk"),
            createdAt=now,
            expiresAt=now + timedelta(seconds=self.quote_ttl_seconds),
        )
        with self._lock:
            self._quotes[quote_id] = QuoteRecord(response=response)
        return response

    def accept_open(self, user_id: str, request: OpenRequest) -> AcceptedTradeResponse:
        payload_hash = _hash_payload(request.model_dump(mode="json"))
        with self._lock:
            existing = self._idempotent_lookup(user_id, request.idempotencyKey, payload_hash)
            if existing is not None:
                return existing

            quote = self._quotes.get(request.quoteId)
            if quote is None:
                raise StoreNotFound("quote not found")
            if quote.response.expiresAt <= _now():
                raise StoreConflict("quote expired")
            if any(item.userId == user_id and item.status in {PositionStatus.OPENING, PositionStatus.OPEN, PositionStatus.CLOSING, PositionStatus.UNKNOWN} for item in self._positions.values()):
                raise StoreConflict("user already has an active position")

            now = _now()
            intent = TradeIntentResponse(
                id=_id("intent"),
                userId=user_id,
                idempotencyKey=request.idempotencyKey,
                action=TradeAction.OPEN,
                status=TradeIntentStatus.ACCEPTED,
                quoteId=quote.response.quoteId,
                positionId=None,
                market=quote.response.market,
                side=quote.response.side,
                createdAt=now,
                updatedAt=now,
            )
            execution = ExecutionAttemptResponse(
                id=_id("exec"),
                tradeIntentId=intent.id,
                userId=user_id,
                venue=quote.response.venue,
                action=TradeAction.OPEN,
                status=ExecutionAttemptStatus.CREATED,
                createdAt=now,
                updatedAt=now,
            )
            position = PositionResponse(
                id=_id("pos"),
                userId=user_id,
                venue=quote.response.venue,
                market=quote.response.market,
                side=quote.response.side,
                status=PositionStatus.OPENING,
                quoteId=quote.response.quoteId,
                openIntentId=intent.id,
                closeIntentId=None,
                ticketUsd=quote.response.ticketUsd,
                leverage=quote.response.leverage,
                notionalUsd=quote.response.notionalUsd,
                entryPrice=None,
                stopLossPrice=quote.response.stopLossPrice,
                liquidationPrice=quote.response.liquidationPrice,
                createdAt=now,
                updatedAt=now,
            )
            intent = intent.model_copy(update={"positionId": position.id, "updatedAt": now})
            self._intents[intent.id] = intent
            self._executions[execution.id] = execution
            self._positions[position.id] = position
            self._idempotency[(user_id, request.idempotencyKey)] = (payload_hash, execution.id)
            return AcceptedTradeResponse(intent=intent, executionAttempt=execution, position=position)

    def accept_close(self, user_id: str, request: CloseRequest) -> AcceptedTradeResponse:
        payload_hash = _hash_payload(request.model_dump(mode="json"))
        with self._lock:
            existing = self._idempotent_lookup(user_id, request.idempotencyKey, payload_hash)
            if existing is not None:
                return existing

            position = self._positions.get(request.positionId)
            if position is None or position.userId != user_id:
                raise StoreNotFound("position not found")
            if position.status not in {PositionStatus.OPENING, PositionStatus.OPEN, PositionStatus.UNKNOWN}:
                raise StoreConflict(f"position cannot close from {position.status}")

            now = _now()
            intent = TradeIntentResponse(
                id=_id("intent"),
                userId=user_id,
                idempotencyKey=request.idempotencyKey,
                action=TradeAction.CLOSE,
                status=TradeIntentStatus.ACCEPTED,
                quoteId=position.quoteId,
                positionId=position.id,
                market=position.market,
                side=position.side,
                createdAt=now,
                updatedAt=now,
            )
            execution = ExecutionAttemptResponse(
                id=_id("exec"),
                tradeIntentId=intent.id,
                userId=user_id,
                venue=position.venue,
                action=TradeAction.CLOSE,
                status=ExecutionAttemptStatus.CREATED,
                createdAt=now,
                updatedAt=now,
            )
            updated_position = position.model_copy(update={"status": PositionStatus.CLOSING, "closeIntentId": intent.id, "updatedAt": now})
            reconciliation = ReconciliationResponse(
                id=_id("recon"),
                positionId=position.id,
                status=ReconciliationStatus.PENDING,
                venueRealizedPnlUsd=None,
                walletDeltaUsd=None,
                differenceUsd=None,
                createdAt=now,
                updatedAt=now,
            )
            self._intents[intent.id] = intent
            self._executions[execution.id] = execution
            self._positions[position.id] = updated_position
            self._reconciliations[reconciliation.id] = reconciliation
            self._idempotency[(user_id, request.idempotencyKey)] = (payload_hash, execution.id)
            return AcceptedTradeResponse(intent=intent, executionAttempt=execution, position=updated_position)

    def state(self, user_id: str | None = None) -> StateResponse:
        with self._lock:
            positions = list(self._positions.values())
            intents = list(self._intents.values())
            executions = list(self._executions.values())
            reconciliations = list(self._reconciliations.values())
            withdrawals = list(self._withdrawals.values())
            user = self._users.get(user_id or "")
            wallet = self._wallets.get(self._wallet_by_user.get(user_id or "") or "")
        if user_id is not None:
            positions = [item for item in positions if item.userId == user_id]
            intents = [item for item in intents if item.userId == user_id]
            executions = [item for item in executions if item.userId == user_id]
            withdrawals = [item for item in withdrawals if item.userId == user_id]
            position_ids = {item.id for item in positions}
            reconciliations = [item for item in reconciliations if item.positionId in position_ids]
        return StateResponse(
            user=user,
            wallet=wallet,
            positions=positions,
            intents=intents,
            executionAttempts=executions,
            reconciliations=reconciliations,
            withdrawals=withdrawals,
        )

    def _idempotent_lookup(self, user_id: str, key: str, payload_hash: str) -> AcceptedTradeResponse | None:
        existing = self._idempotency.get((user_id, key))
        if existing is None:
            return None
        previous_hash, execution_id = existing
        if previous_hash != payload_hash:
            raise StoreConflict("idempotency key reused with different payload")
        execution = self._executions[execution_id]
        intent = self._intents[execution.tradeIntentId]
        position = self._positions.get(intent.positionId or "")
        return AcceptedTradeResponse(intent=intent, executionAttempt=execution, position=position)

    def _wallet_for_user(self, user_id: str, *, chain_id: int, custody_provider: str, now: datetime) -> WalletAccountResponse:
        wallet_id = self._wallet_by_user.get(user_id)
        if wallet_id is not None:
            return self._wallets[wallet_id]
        wallet = WalletAccountResponse(
            id=_id("wallet"),
            userId=user_id,
            chainId=chain_id,
            address=_dev_address(user_id),
            walletType=WalletType.PLATFORM_CUSTODY,
            status=WalletStatus.ACTIVE,
            custodyProvider=custody_provider,
            custodyKeyRef=f"development:{user_id}",
            createdAt=now,
            updatedAt=now,
        )
        self._wallets[wallet.id] = wallet
        self._wallet_by_user[user_id] = wallet.id
        return wallet


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> datetime:
    return datetime.now(UTC)


def _market(value: str) -> str:
    return value.upper().replace("/", "-")


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _dev_address(seed: str) -> str:
    digest = hashlib.sha256(f"tick-dev-wallet:{seed}".encode()).hexdigest()
    return f"0x{digest[-40:]}"
