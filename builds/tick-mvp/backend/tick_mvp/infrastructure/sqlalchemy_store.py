from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from tick_mvp.core.config import get_settings
from tick_mvp.domain.schemas import (
    AcceptedTradeResponse,
    CloseRequest,
    DepositAddressResponse,
    OpenRequest,
    QuoteRequest,
    QuoteResponse,
    StateResponse,
    WithdrawalRequest,
)
from tick_mvp.domain.states import (
    AuthProvider,
    ExecutionAttemptStatus,
    PositionStatus,
    ReconciliationStatus,
    TradeAction,
    TradeIntentStatus,
    TradeSide,
    UserStatus,
    WalletStatus,
    WalletType,
    WithdrawalStatus,
)
from tick_mvp.infrastructure.custody import PrivateKeyCipher, PlatformWalletFactory
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.memory_store import StoreConflict, StoreNotFound
from tick_mvp.infrastructure.model_mappers import (
    execution_response,
    intent_response,
    position_response,
    quote_response,
    reconciliation_response,
    user_response,
    wallet_response,
    withdrawal_response,
)
from tick_mvp.infrastructure.models import (
    AuthIdentity,
    ExecutionAttempt,
    Position,
    Quote,
    Reconciliation,
    TradeIntent,
    User,
    WalletAccount,
    Withdrawal,
)


class SQLAlchemyStore:
    def __init__(self, default_venue: str, quote_ttl_seconds: int = 5, session_factory=None, quote_engine=None) -> None:
        settings = get_settings()
        self.default_venue = default_venue
        self.quote_ttl_seconds = quote_ttl_seconds
        self.chain_id = settings.arb_chain_id
        self.custody_provider = settings.custody_provider
        self._settings = settings
        self._session_factory = session_factory or create_session_factory()
        self._quote_engine = quote_engine

    def start(self) -> None:
        start = getattr(self._quote_engine, "start", None)
        if start is not None:
            start()

    def stop(self) -> None:
        stop = getattr(self._quote_engine, "stop", None)
        if stop is not None:
            stop()

    def markets(self, *, limit: int = 10) -> dict[str, Any]:
        return self._market_method("markets")(limit=limit)

    def chart(self, market: str, *, window_seconds: int = 90) -> dict[str, Any]:
        return self._market_method("chart")(market, window_seconds=window_seconds)

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        return self._market_method("tape")(market, since=since)

    def upsert_google_user(
        self,
        *,
        provider_subject: str,
        email: str,
        display_name: str | None,
        avatar_url: str | None,
        chain_id: int,
        custody_provider: str,
    ):
        now = _now()
        normalized_email = email.lower()
        with session_scope(self._session_factory) as session:
            identity = (
                session.query(AuthIdentity)
                .filter(AuthIdentity.provider == AuthProvider.GOOGLE.value, AuthIdentity.provider_subject == provider_subject)
                .one_or_none()
            )
            if identity is None:
                user = session.query(User).filter(User.email == normalized_email).one_or_none()
                if user is None:
                    user = User(
                        id=_id("user"),
                        email=normalized_email,
                        display_name=display_name,
                        avatar_url=avatar_url,
                        status=UserStatus.ACTIVE.value,
                        created_at=now,
                        updated_at=now,
                        last_login_at=now,
                    )
                    session.add(user)
                    session.flush()
                identity = AuthIdentity(
                    id=_id("auth"),
                    user_id=user.id,
                    provider=AuthProvider.GOOGLE.value,
                    provider_subject=provider_subject,
                    email=normalized_email,
                    payload={},
                    created_at=now,
                    updated_at=now,
                )
                session.add(identity)
            else:
                user = session.get(User, identity.user_id)
                if user is None:
                    raise StoreNotFound("user not found")

            user.email = normalized_email
            user.display_name = display_name
            user.avatar_url = avatar_url
            user.updated_at = now
            user.last_login_at = now
            identity.email = normalized_email
            identity.updated_at = now
            wallet = self._wallet_for_user(session, user.id, chain_id=chain_id, custody_provider=custody_provider, now=now)
            session.flush()
            return user_response(user, identity), wallet_response(wallet)

    def user(self, user_id: str):
        with session_scope(self._session_factory) as session:
            user = session.get(User, user_id)
            if user is None:
                raise StoreNotFound("user not found")
            identity = _primary_identity(session, user.id)
            return user_response(user, identity)

    def wallet_for_user(self, user_id: str):
        with session_scope(self._session_factory) as session:
            wallet = _primary_wallet(session, user_id)
            if wallet is None:
                raise StoreNotFound("wallet not found")
            return wallet_response(wallet)

    def deposit_address(self, user_id: str) -> DepositAddressResponse:
        wallet = self.wallet_for_user(user_id)
        return DepositAddressResponse(chainId=wallet.chainId, walletId=wallet.id, address=wallet.address)

    def request_withdrawal(self, user_id: str, request: WithdrawalRequest) -> WithdrawalResponse:
        request_hash = _hash_payload(request.model_dump(mode="json"))
        now = _now()
        with session_scope(self._session_factory) as session:
            existing = (
                session.query(Withdrawal)
                .filter(Withdrawal.user_id == user_id, Withdrawal.idempotency_key == request.idempotencyKey)
                .one_or_none()
            )
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise StoreConflict("idempotency key reused with different payload")
                return withdrawal_response(existing)

            wallet = _primary_wallet(session, user_id)
            if wallet is None:
                raise StoreNotFound("wallet not found")
            withdrawal = Withdrawal(
                id=_id("withdrawal"),
                user_id=user_id,
                wallet_id=wallet.id,
                idempotency_key=request.idempotencyKey,
                request_hash=request_hash,
                asset=request.asset.upper(),
                amount=request.amount,
                destination_address=request.destinationAddress,
                status=WithdrawalStatus.REQUESTED.value,
                created_at=now,
                updated_at=now,
                payload={},
            )
            session.add(withdrawal)
            session.flush()
            return withdrawal_response(withdrawal)

    def create_quote(self, user_id: str, request: QuoteRequest) -> QuoteResponse:
        now = _now()
        if self._quote_engine is not None:
            venue_quote = self._quote_engine.quote_open(
                market=request.market,
                side=request.side,
                ticket_usd=request.ticketUsd,
                leverage=request.leverage,
                max_loss_usd=request.maxLossUsd,
            )
            venue = venue_quote.venue
            market = venue_quote.market
            side = venue_quote.side.value
            ticket_usd = venue_quote.ticket_usd
            leverage = venue_quote.leverage
            notional = venue_quote.notional_usd
            estimated_open = venue_quote.estimated_open_cost_usd
            estimated_close = venue_quote.estimated_close_cost_usd
            estimated_round_trip = venue_quote.estimated_round_trip_cost_usd
            liquidation_price = venue_quote.liquidation_price
            stop_loss_price = venue_quote.stop_loss_price
            opening_allowed = venue_quote.opening_allowed
            payload = {
                **venue_quote.payload,
                "quoteSource": "live_venue",
                "liquidationPrice": str(liquidation_price) if liquidation_price is not None else None,
                "stopLossPrice": str(stop_loss_price) if stop_loss_price is not None else None,
            }
        else:
            venue = self.default_venue
            market = _market(request.market)
            side = request.side.value
            ticket_usd = request.ticketUsd
            leverage = request.leverage
            notional = request.ticketUsd * request.leverage
            estimated_open = notional * Decimal("0.0002")
            estimated_close = notional * Decimal("0.0002")
            estimated_round_trip = estimated_open + estimated_close
            liquidation_price = None
            stop_loss_price = None
            opening_allowed = True
            payload = {"quoteSource": "static_placeholder"}
        quote = Quote(
            id=_id("quote"),
            user_id=user_id,
            venue=venue,
            market=market,
            side=side,
            ticket_usd=ticket_usd,
            leverage=leverage,
            notional_usd=notional,
            max_loss_usd=request.maxLossUsd,
            estimated_open_cost_usd=estimated_open,
            estimated_close_cost_usd=estimated_close,
            estimated_round_trip_cost_usd=estimated_round_trip,
            liquidation_price=liquidation_price,
            stop_loss_price=stop_loss_price,
            opening_allowed=opening_allowed,
            risk_decision_id=_id("risk"),
            payload=payload,
            created_at=now,
            expires_at=now + timedelta(seconds=self.quote_ttl_seconds),
        )
        with session_scope(self._session_factory) as session:
            session.add(quote)
            session.flush()
            return quote_response(quote)

    def accept_open(self, user_id: str, request: OpenRequest) -> AcceptedTradeResponse:
        request_hash = _hash_payload(request.model_dump(mode="json"))
        now = _now()
        with session_scope(self._session_factory) as session:
            existing = self._idempotent_lookup(session, user_id, request.idempotencyKey, request_hash)
            if existing is not None:
                return existing

            quote = session.get(Quote, request.quoteId)
            if quote is None:
                raise StoreNotFound("quote not found")
            if quote.user_id != user_id:
                raise StoreNotFound("quote not found")
            if quote.expires_at <= now:
                raise StoreConflict("quote expired")
            if _active_position_exists(session, user_id):
                raise StoreConflict("user already has an active position")
            wallet = _primary_wallet(session, user_id)
            if wallet is None:
                raise StoreNotFound("wallet not found")

            intent = TradeIntent(
                id=_id("intent"),
                user_id=user_id,
                idempotency_key=request.idempotencyKey,
                request_hash=request_hash,
                action=TradeAction.OPEN.value,
                status=TradeIntentStatus.ACCEPTED.value,
                quote_id=quote.id,
                position_id=None,
                wallet_id=wallet.id,
                market=quote.market,
                side=quote.side,
                payload={},
                created_at=now,
                updated_at=now,
            )
            session.add(intent)
            session.flush()

            execution = ExecutionAttempt(
                id=_id("exec"),
                trade_intent_id=intent.id,
                user_id=user_id,
                venue=quote.venue,
                action=TradeAction.OPEN.value,
                status=ExecutionAttemptStatus.CREATED.value,
                gas_charge_asset=self._settings.gas_charge_asset,
                payload={},
                created_at=now,
                updated_at=now,
            )
            position = Position(
                id=_id("pos"),
                user_id=user_id,
                wallet_id=wallet.id,
                venue=quote.venue,
                venue_position_id=None,
                market=quote.market,
                side=quote.side,
                status=PositionStatus.OPENING.value,
                quote_id=quote.id,
                open_intent_id=intent.id,
                close_intent_id=None,
                ticket_usd=quote.ticket_usd,
                leverage=quote.leverage,
                notional_usd=quote.notional_usd,
                entry_price=None,
                stop_loss_price=quote.stop_loss_price,
                liquidation_price=quote.liquidation_price,
                payload={},
                created_at=now,
                updated_at=now,
            )
            intent.position_id = position.id
            session.add_all([execution, position])
            session.flush()
            return AcceptedTradeResponse(
                intent=intent_response(intent),
                executionAttempt=execution_response(execution),
                position=position_response(position),
            )

    def accept_close(self, user_id: str, request: CloseRequest) -> AcceptedTradeResponse:
        request_hash = _hash_payload(request.model_dump(mode="json"))
        now = _now()
        with session_scope(self._session_factory) as session:
            existing = self._idempotent_lookup(session, user_id, request.idempotencyKey, request_hash)
            if existing is not None:
                return existing

            position = session.get(Position, request.positionId)
            if position is None or position.user_id != user_id:
                raise StoreNotFound("position not found")
            if position.status not in {PositionStatus.OPENING.value, PositionStatus.OPEN.value, PositionStatus.UNKNOWN.value}:
                raise StoreConflict(f"position cannot close from {position.status}")
            wallet = _primary_wallet(session, user_id)
            if wallet is None:
                raise StoreNotFound("wallet not found")

            intent = TradeIntent(
                id=_id("intent"),
                user_id=user_id,
                idempotency_key=request.idempotencyKey,
                request_hash=request_hash,
                action=TradeAction.CLOSE.value,
                status=TradeIntentStatus.ACCEPTED.value,
                quote_id=position.quote_id,
                position_id=position.id,
                wallet_id=wallet.id,
                market=position.market,
                side=position.side,
                payload={},
                created_at=now,
                updated_at=now,
            )
            session.add(intent)
            session.flush()

            execution = ExecutionAttempt(
                id=_id("exec"),
                trade_intent_id=intent.id,
                user_id=user_id,
                venue=position.venue,
                action=TradeAction.CLOSE.value,
                status=ExecutionAttemptStatus.CREATED.value,
                gas_charge_asset=self._settings.gas_charge_asset,
                payload={},
                created_at=now,
                updated_at=now,
            )
            position.status = PositionStatus.CLOSING.value
            position.close_intent_id = intent.id
            position.updated_at = now
            reconciliation = Reconciliation(
                id=_id("recon"),
                position_id=position.id,
                status=ReconciliationStatus.PENDING.value,
                payload={},
                created_at=now,
                updated_at=now,
            )
            session.add_all([execution, reconciliation])
            session.flush()
            return AcceptedTradeResponse(
                intent=intent_response(intent),
                executionAttempt=execution_response(execution),
                position=position_response(position),
            )

    def state(self, user_id: str | None = None) -> StateResponse:
        with session_scope(self._session_factory) as session:
            user = session.get(User, user_id) if user_id else None
            identity = _primary_identity(session, user_id) if user_id else None
            wallet = _primary_wallet(session, user_id) if user_id else None
            positions_query = session.query(Position)
            intents_query = session.query(TradeIntent)
            executions_query = session.query(ExecutionAttempt)
            withdrawals_query = session.query(Withdrawal)
            if user_id is not None:
                positions_query = positions_query.filter(Position.user_id == user_id)
                intents_query = intents_query.filter(TradeIntent.user_id == user_id)
                executions_query = executions_query.filter(ExecutionAttempt.user_id == user_id)
                withdrawals_query = withdrawals_query.filter(Withdrawal.user_id == user_id)
            positions = positions_query.order_by(Position.created_at.desc()).all()
            position_ids = [item.id for item in positions]
            reconciliations = []
            if position_ids:
                reconciliations = session.query(Reconciliation).filter(Reconciliation.position_id.in_(position_ids)).all()
            return StateResponse(
                user=user_response(user, identity) if user and identity else None,
                wallet=wallet_response(wallet) if wallet else None,
                positions=[position_response(item) for item in positions],
                intents=[intent_response(item) for item in intents_query.order_by(TradeIntent.created_at.desc()).all()],
                executionAttempts=[execution_response(item) for item in executions_query.order_by(ExecutionAttempt.created_at.desc()).all()],
                reconciliations=[reconciliation_response(item) for item in reconciliations],
                withdrawals=[withdrawal_response(item) for item in withdrawals_query.order_by(Withdrawal.created_at.desc()).all()],
            )

    def _idempotent_lookup(self, session, user_id: str, key: str, request_hash: str) -> AcceptedTradeResponse | None:
        intent = session.query(TradeIntent).filter(TradeIntent.user_id == user_id, TradeIntent.idempotency_key == key).one_or_none()
        if intent is None:
            return None
        if intent.request_hash != request_hash:
            raise StoreConflict("idempotency key reused with different payload")
        execution = session.query(ExecutionAttempt).filter(ExecutionAttempt.trade_intent_id == intent.id).one()
        position = session.get(Position, intent.position_id) if intent.position_id else None
        return AcceptedTradeResponse(
            intent=intent_response(intent),
            executionAttempt=execution_response(execution),
            position=position_response(position) if position else None,
        )

    def _wallet_for_user(self, session, user_id: str, *, chain_id: int, custody_provider: str, now: datetime) -> WalletAccount:
        wallet = _primary_wallet(session, user_id)
        if wallet is not None:
            return wallet
        address, encrypted_private_key = self._new_wallet()
        wallet = WalletAccount(
            id=_id("wallet"),
            user_id=user_id,
            chain_id=chain_id,
            address=address,
            wallet_type=WalletType.PLATFORM_CUSTODY.value,
            status=WalletStatus.ACTIVE.value,
            custody_provider=custody_provider,
            custody_key_ref=f"encrypted_postgres:{user_id}",
            encrypted_private_key=encrypted_private_key,
            gas_wallet=False,
            payload={},
            created_at=now,
            updated_at=now,
        )
        session.add(wallet)
        session.flush()
        return wallet

    def _new_wallet(self) -> tuple[str, bytes | None]:
        if self.custody_provider == "development":
            seed = uuid.uuid4().hex
            return _dev_address(seed), None
        cipher = PrivateKeyCipher(self._settings.custody_private_key_encryption_key)
        generated = PlatformWalletFactory(cipher).create_arbitrum_wallet()
        return generated.address, generated.encrypted_private_key

    def _market_method(self, name: str):
        method = getattr(self._quote_engine, name, None)
        if method is None:
            raise StoreNotFound(f"market data method is unavailable: {name}")
        return method


def _primary_identity(session, user_id: str) -> AuthIdentity | None:
    return session.query(AuthIdentity).filter(AuthIdentity.user_id == user_id).order_by(AuthIdentity.created_at.asc()).first()


def _primary_wallet(session, user_id: str) -> WalletAccount | None:
    return session.query(WalletAccount).filter(WalletAccount.user_id == user_id, WalletAccount.status == WalletStatus.ACTIVE.value).order_by(WalletAccount.created_at.asc()).first()


def _active_position_exists(session, user_id: str) -> bool:
    return (
        session.query(Position.id)
        .filter(
            Position.user_id == user_id,
            Position.status.in_([PositionStatus.OPENING.value, PositionStatus.OPEN.value, PositionStatus.CLOSING.value, PositionStatus.UNKNOWN.value]),
        )
        .first()
        is not None
    )


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
