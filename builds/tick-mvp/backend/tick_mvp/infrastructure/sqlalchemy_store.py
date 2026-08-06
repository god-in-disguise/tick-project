from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from tick_mvp.core.config import get_settings
from tick_mvp.domain.invitations import InviteAuthError
from tick_mvp.domain.schemas import (
    AcceptedTradeResponse,
    CloseRequest,
    DemoResetResponse,
    DepositAddressResponse,
    OpenRequest,
    QuoteRequest,
    QuoteResponse,
    StateResponse,
    TradingProfileResponse,
    VenueModeResponse,
    WalletBalancesResponse,
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
    TradingMode,
    UserStatus,
    VenueMode,
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
    trading_profile_response,
    user_response,
    wallet_response,
    withdrawal_response,
)
from tick_mvp.infrastructure.models import (
    AuthIdentity,
    DemoProfileReset,
    ExecutionAttempt,
    InviteCode,
    LedgerEvent,
    Position,
    Quote,
    Reconciliation,
    TradeIntent,
    TradingProfile,
    User,
    WalletAccount,
    Withdrawal,
)
from tick_mvp.venues.flash.constants import SOLANA_MAINNET_CHAIN_ID


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

    def readiness(self) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            session.execute(text("SELECT 1"))
        health = getattr(self._quote_engine, "health", None)
        return {
            "postgres": True,
            "marketFeed": health() if health is not None else None,
        }

    def markets(self, *, limit: int = 10, venue: str | None = None) -> dict[str, Any]:
        return self._market_method("markets")(limit=limit, venue=venue)

    def chart(self, market: str, *, window_seconds: int = 90) -> dict[str, Any]:
        return self._market_method("chart")(market, window_seconds=window_seconds)

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        return self._market_method("tape")(market, since=since)

    def upsert_auth_user(
        self,
        *,
        provider: AuthProvider,
        provider_subject: str,
        email: str,
        display_name: str | None,
        avatar_url: str | None,
        chain_id: int,
        custody_provider: str,
    ):
        with session_scope(self._session_factory) as session:
            return self._upsert_auth_user(
                session,
                provider=provider,
                provider_subject=provider_subject,
                email=email,
                display_name=display_name,
                avatar_url=avatar_url,
                chain_id=chain_id,
                custody_provider=custody_provider,
            )

    def create_invite_code(
        self,
        *,
        code_hash: str,
        display_name: str | None = None,
        expires_at: datetime | None = None,
    ) -> str:
        now = _now()
        with session_scope(self._session_factory) as session:
            invite = InviteCode(
                id=_id("invite"),
                code_hash=code_hash,
                display_name=display_name,
                status="active",
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            session.add(invite)
            session.flush()
            return invite.id

    def redeem_invite_code(
        self,
        *,
        code_hash: str,
        chain_id: int,
        custody_provider: str,
    ):
        now = _now()
        with session_scope(self._session_factory) as session:
            invite = (
                session.query(InviteCode)
                .filter(InviteCode.code_hash == code_hash)
                .with_for_update()
                .one_or_none()
            )
            if (
                invite is None
                or invite.status != "active"
                or (invite.expires_at is not None and invite.expires_at <= now)
            ):
                raise InviteAuthError("invalid or expired invite")

            user, wallet = self._upsert_auth_user(
                session,
                provider=AuthProvider.INVITE_CODE,
                provider_subject=invite.id,
                email=_placeholder_email(invite.id),
                display_name=invite.display_name or "TICK trader",
                avatar_url=None,
                chain_id=chain_id,
                custody_provider=custody_provider,
            )
            if invite.redeemed_by_user_id not in {None, user.id}:
                raise InviteAuthError("invalid or expired invite")
            invite.redeemed_by_user_id = user.id
            invite.redeemed_at = invite.redeemed_at or now
            invite.last_used_at = now
            invite.updated_at = now
            session.flush()
            return user, wallet

    def _upsert_auth_user(
        self,
        session,
        *,
        provider: AuthProvider,
        provider_subject: str,
        email: str,
        display_name: str | None,
        avatar_url: str | None,
        chain_id: int,
        custody_provider: str,
    ):
        now = _now()
        normalized_email = email.strip().lower()
        identity = (
            session.query(AuthIdentity)
            .filter(
                AuthIdentity.provider == provider.value,
                AuthIdentity.provider_subject == provider_subject,
            )
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
                    active_trading_mode=TradingMode.DEMO.value,
                    active_venue=VenueMode.GTRADE.value,
                    created_at=now,
                    updated_at=now,
                    last_login_at=now,
                )
                session.add(user)
                session.flush()
            identity = AuthIdentity(
                id=_id("auth"),
                user_id=user.id,
                provider=provider.value,
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
        user.display_name = display_name or user.display_name
        user.avatar_url = avatar_url or user.avatar_url
        user.updated_at = now
        user.last_login_at = now
        identity.email = normalized_email
        identity.updated_at = now
        wallet = self._wallet_for_user(
            session,
            user.id,
            chain_id=chain_id,
            custody_provider=custody_provider,
            now=now,
        )
        self._ensure_trading_profiles(session, user.id, now=now)
        session.flush()
        return user_response(user, identity), wallet_response(wallet)

    def user(self, user_id: str):
        with session_scope(self._session_factory) as session:
            user = session.get(User, user_id)
            if user is None:
                raise StoreNotFound("user not found")
            identity = _primary_identity(session, user.id)
            return user_response(user, identity)

    def wallet_for_user(self, user_id: str, venue: VenueMode | str | None = None):
        with session_scope(self._session_factory) as session:
            selected = _active_venue(session, user_id) if venue is None else VenueMode(venue)
            wallet = _venue_wallet(session, user_id, selected, self.chain_id)
            if wallet is None:
                raise StoreNotFound("wallet not found")
            return wallet_response(wallet)

    def switch_venue(self, user_id: str, venue: VenueMode) -> VenueModeResponse:
        now = _now()
        with session_scope(self._session_factory) as session:
            user = session.get(User, user_id, with_for_update=True)
            if user is None:
                raise StoreNotFound("user not found")
            if _active_position_exists(session, user_id):
                raise StoreConflict("finish the active trade before switching venue")
            chain_id = _chain_id_for_venue(venue, self.chain_id)
            wallet = self._wallet_for_user(
                session,
                user_id,
                chain_id=chain_id,
                custody_provider=self.custody_provider,
                now=now,
                venue=venue,
            )
            user.active_venue = venue.value
            user.updated_at = now
            session.flush()
            return VenueModeResponse(venue=venue, wallet=wallet_response(wallet))

    def trading_profile(self, user_id: str) -> TradingProfileResponse:
        with session_scope(self._session_factory) as session:
            profile = _active_profile(session, user_id)
            return trading_profile_response(profile)

    def switch_trading_mode(self, user_id: str, mode: TradingMode) -> TradingProfileResponse:
        now = _now()
        with session_scope(self._session_factory) as session:
            user = session.get(User, user_id, with_for_update=True)
            if user is None:
                raise StoreNotFound("user not found")
            if _active_position_exists(session, user_id):
                raise StoreConflict("finish the active trade before switching mode")
            _active_profile(session, user_id)
            profile = _profile_for_mode(session, user_id, mode.value)
            user.active_trading_mode = mode.value
            user.updated_at = now
            profile.updated_at = now
            session.flush()
            return trading_profile_response(profile)

    def reset_demo_profile(self, user_id: str) -> DemoResetResponse:
        now = _now()
        with session_scope(self._session_factory) as session:
            profile = (
                session.query(TradingProfile)
                .filter(
                    TradingProfile.user_id == user_id,
                    TradingProfile.mode == TradingMode.DEMO.value,
                )
                .with_for_update()
                .one_or_none()
            )
            if profile is None:
                raise StoreNotFound("demo profile not found")
            if _active_position_exists(
                session,
                user_id,
                trading_mode=TradingMode.DEMO.value,
                profile_season=profile.current_season,
            ):
                raise StoreConflict("close the demo trade before resetting")

            positions = (
                session.query(Position)
                .filter(
                    Position.user_id == user_id,
                    Position.trading_mode == TradingMode.DEMO.value,
                    Position.profile_season == profile.current_season,
                    Position.status.in_([PositionStatus.CLOSED.value, PositionStatus.LIQUIDATED.value]),
                )
                .all()
            )
            position_ids = [position.id for position in positions]
            reconciliations = (
                session.query(Reconciliation)
                .filter(Reconciliation.position_id.in_(position_ids))
                .all()
                if position_ids
                else []
            )
            settled = [
                item
                for item in reconciliations
                if item.wallet_delta_usd is not None
            ]
            starting_balance = Decimal(profile.starting_balance_usd or 1000)
            ending_balance = Decimal(profile.balance_usd or 0)
            ended_season = profile.current_season
            reset = DemoProfileReset(
                id=_id("demo_reset"),
                profile_id=profile.id,
                user_id=user_id,
                ended_season=ended_season,
                starting_balance_usd=starting_balance,
                ending_balance_usd=ending_balance,
                realized_pnl_usd=ending_balance - starting_balance,
                trade_count=len(settled),
                win_count=sum(1 for item in settled if Decimal(item.wallet_delta_usd) > 0),
                reset_at=now,
                payload={},
            )
            session.add(reset)
            profile.current_season += 1
            profile.starting_balance_usd = Decimal("1000")
            profile.balance_usd = Decimal("1000")
            profile.reset_count += 1
            profile.last_reset_at = now
            profile.updated_at = now
            session.flush()
            return DemoResetResponse(
                profile=trading_profile_response(profile),
                endedSeason=ended_season,
                endingBalanceUsd=ending_balance,
                realizedPnlUsd=ending_balance - starting_balance,
                tradeCount=reset.trade_count,
                winCount=reset.win_count,
                resetAt=now,
            )

    def demo_balances(self, user_id: str) -> WalletBalancesResponse | None:
        with session_scope(self._session_factory) as session:
            profile = _active_profile(session, user_id)
            if profile.mode != TradingMode.DEMO.value:
                return None
            balance = Decimal(profile.balance_usd or 0)
            return WalletBalancesResponse(
                chainId=self.chain_id,
                address="demo",
                nativeEth=None,
                usdc=balance,
                onchainUsdc=None,
                gasChargesUsdc=Decimal(0),
                spendableUsdc=balance,
                gtradeAllowanceUsdc=None,
                source="demo_ledger",
                fetchedAt=_now(),
                tradingMode=TradingMode.DEMO,
                profileSeason=profile.current_season,
            )

    def is_demo_mode(self, user_id: str) -> bool:
        return self.trading_profile(user_id).mode == TradingMode.DEMO

    def deposit_address(self, user_id: str) -> DepositAddressResponse:
        wallet = self.wallet_for_user(user_id)
        return DepositAddressResponse(chainId=wallet.chainId, walletId=wallet.id, address=wallet.address)

    def reserved_gas_charges_usdc(
        self,
        user_id: str,
        venue: VenueMode | str | None = None,
    ) -> Decimal:
        selected = VenueMode(venue) if venue is not None else None
        with session_scope(self._session_factory) as session:
            rows = (
                session.query(LedgerEvent.amount, LedgerEvent.payload)
                .filter(
                    LedgerEvent.user_id == user_id,
                    LedgerEvent.event_type == "gas_charge",
                    LedgerEvent.asset == "USDC",
                )
                .all()
            )
        total = sum(
            (
                Decimal(amount or 0)
                for amount, payload in rows
                if selected is None
                or str((payload or {}).get("venue") or VenueMode.GTRADE.value)
                == selected.value
            ),
            Decimal(0),
        )
        return max(Decimal(0), -Decimal(total or 0))

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

            user = session.get(User, user_id, with_for_update=True)
            if user is None:
                raise StoreNotFound("user not found")
            if user.active_trading_mode == TradingMode.DEMO.value:
                raise StoreConflict("withdrawals are unavailable in demo mode")
            if (
                user.active_venue == VenueMode.FLASH.value
                and not self._settings.flash_real_execution_enabled
            ):
                raise StoreConflict("Flash withdrawals are not enabled")
            if request.asset.upper() != "USDC":
                raise StoreConflict("only USDC withdrawals are supported")
            if _active_position_exists(session, user_id):
                raise StoreConflict("withdrawal unavailable while a position is active")
            if _pending_withdrawal_exists(session, user_id):
                raise StoreConflict("user already has a pending withdrawal")
            venue = VenueMode(user.active_venue)
            wallet = _venue_wallet(session, user_id, venue, self.chain_id)
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
                payload={
                    "venue": venue.value,
                    "chainId": wallet.chain_id,
                },
            )
            session.add(withdrawal)
            session.flush()
            return withdrawal_response(withdrawal)

    def create_quote(self, user_id: str, request: QuoteRequest) -> QuoteResponse:
        now = _now()
        with session_scope(self._session_factory) as session:
            active_venue = _active_venue(session, user_id)
        if self._quote_engine is not None:
            venue_quote = self._quote_engine.quote_open(
                venue=active_venue.value,
                market=request.market,
                side=request.side,
                ticket_usd=request.ticketUsd,
                leverage=request.leverage,
                max_loss_usd=request.maxLossUsd,
                take_profit_usd=request.takeProfitUsd,
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
            take_profit_price = venue_quote.take_profit_price
            opening_allowed = venue_quote.opening_allowed
            payload = {
                **venue_quote.payload,
                "quoteSource": "live_venue",
                "liquidationPrice": str(liquidation_price) if liquidation_price is not None else None,
                "stopLossPrice": str(stop_loss_price) if stop_loss_price is not None else None,
                "takeProfitPrice": str(take_profit_price) if take_profit_price is not None else None,
            }
        else:
            venue = active_venue.value
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
            take_profit_price = None
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
            take_profit_usd=request.takeProfitUsd,
            estimated_open_cost_usd=estimated_open,
            estimated_close_cost_usd=estimated_close,
            estimated_round_trip_cost_usd=estimated_round_trip,
            liquidation_price=liquidation_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            opening_allowed=opening_allowed,
            risk_decision_id=_id("risk"),
            payload=payload,
            created_at=now,
            expires_at=now + timedelta(seconds=self.quote_ttl_seconds),
        )
        with session_scope(self._session_factory) as session:
            profile = _active_profile(session, user_id)
            if _active_venue(session, user_id).value != quote.venue:
                raise StoreConflict("venue changed while the quote was being created")
            quote.trading_mode = profile.mode
            quote.profile_season = profile.current_season
            session.add(quote)
            session.flush()
            return quote_response(quote)

    def accept_open(self, user_id: str, request: OpenRequest) -> AcceptedTradeResponse:
        request_hash = _hash_payload(request.model_dump(mode="json"))
        now = _now()
        with session_scope(self._session_factory) as session:
            profile = _active_profile(session, user_id, for_update=True)
            existing = self._idempotent_lookup(
                session,
                user_id,
                profile.mode,
                profile.current_season,
                request.idempotencyKey,
                request_hash,
            )
            if existing is not None:
                return existing

            quote = session.get(Quote, request.quoteId)
            if quote is None:
                raise StoreNotFound("quote not found")
            if quote.user_id != user_id:
                raise StoreNotFound("quote not found")
            if (
                quote.trading_mode != profile.mode
                or quote.profile_season != profile.current_season
            ):
                raise StoreConflict("quote belongs to another trading profile")
            if quote.expires_at <= now:
                raise StoreConflict("quote expired")
            if not quote.opening_allowed:
                reason = (quote.payload or {}).get("openingBlockedReason")
                detail = f": {reason}" if reason else ""
                raise StoreConflict(f"quote is not executable{detail}")
            user = session.get(User, user_id, with_for_update=True)
            if user is None:
                raise StoreNotFound("user not found")
            if quote.venue != user.active_venue:
                raise StoreConflict("quote belongs to another venue")
            if _active_position_exists(
                session,
                user_id,
                trading_mode=profile.mode,
                profile_season=profile.current_season,
            ):
                raise StoreConflict("user already has an active position")
            if profile.mode == TradingMode.LIVE.value and _pending_withdrawal_exists(session, user_id):
                raise StoreConflict("user has a pending withdrawal")
            if (
                profile.mode == TradingMode.DEMO.value
                and Decimal(profile.balance_usd or 0) < Decimal(quote.ticket_usd)
            ):
                raise StoreConflict(
                    f"insufficient demo balance: {Decimal(profile.balance_usd or 0):.2f} available"
                )
            wallet = (
                _venue_wallet(session, user_id, VenueMode(user.active_venue), self.chain_id)
                if profile.mode == TradingMode.LIVE.value
                else None
            )
            if profile.mode == TradingMode.LIVE.value and wallet is None:
                raise StoreNotFound("wallet not found")

            intent = TradeIntent(
                id=_id("intent"),
                user_id=user_id,
                trading_mode=profile.mode,
                profile_season=profile.current_season,
                idempotency_key=request.idempotencyKey,
                request_hash=request_hash,
                action=TradeAction.OPEN.value,
                status=TradeIntentStatus.ACCEPTED.value,
                quote_id=quote.id,
                position_id=None,
                wallet_id=wallet.id if wallet else None,
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
                trading_mode=profile.mode,
                profile_season=profile.current_season,
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
                trading_mode=profile.mode,
                profile_season=profile.current_season,
                wallet_id=wallet.id if wallet else None,
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
                take_profit_price=quote.take_profit_price,
                liquidation_price=quote.liquidation_price,
                payload={"simulation": True} if profile.mode == TradingMode.DEMO.value else {},
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
            profile = _active_profile(session, user_id, for_update=True)
            existing = self._idempotent_lookup(
                session,
                user_id,
                profile.mode,
                profile.current_season,
                request.idempotencyKey,
                request_hash,
            )
            if existing is not None:
                return existing

            position = (
                session.query(Position)
                .filter(Position.id == request.positionId)
                .with_for_update()
                .one_or_none()
            )
            if (
                position is None
                or position.user_id != user_id
                or position.trading_mode != profile.mode
                or position.profile_season != profile.current_season
            ):
                raise StoreNotFound("position not found")
            if position.status not in {PositionStatus.OPENING.value, PositionStatus.OPEN.value, PositionStatus.UNKNOWN.value}:
                raise StoreConflict(f"position cannot close from {position.status}")
            wallet = _primary_wallet(session, user_id) if profile.mode == TradingMode.LIVE.value else None
            if profile.mode == TradingMode.LIVE.value and wallet is None:
                raise StoreNotFound("wallet not found")

            intent = TradeIntent(
                id=_id("intent"),
                user_id=user_id,
                trading_mode=profile.mode,
                profile_season=profile.current_season,
                idempotency_key=request.idempotencyKey,
                request_hash=request_hash,
                action=TradeAction.CLOSE.value,
                status=TradeIntentStatus.ACCEPTED.value,
                quote_id=position.quote_id,
                position_id=position.id,
                wallet_id=wallet.id if wallet else None,
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
                trading_mode=profile.mode,
                profile_season=profile.current_season,
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
            active_venue = _active_venue(session, user_id) if user_id else VenueMode.GTRADE
            wallet = _venue_wallet(session, user_id, active_venue, self.chain_id) if user_id else None
            profile = _active_profile(session, user_id) if user_id else None
            positions_query = session.query(Position)
            intents_query = session.query(TradeIntent)
            executions_query = session.query(ExecutionAttempt)
            withdrawals_query = session.query(Withdrawal)
            if user_id is not None:
                positions_query = positions_query.filter(
                    Position.user_id == user_id,
                    Position.trading_mode == profile.mode,
                    Position.profile_season == profile.current_season,
                    Position.venue == active_venue.value,
                )
                intents_query = intents_query.filter(
                    TradeIntent.user_id == user_id,
                    TradeIntent.trading_mode == profile.mode,
                    TradeIntent.profile_season == profile.current_season,
                )
                executions_query = executions_query.filter(
                    ExecutionAttempt.user_id == user_id,
                    ExecutionAttempt.trading_mode == profile.mode,
                    ExecutionAttempt.profile_season == profile.current_season,
                    ExecutionAttempt.venue == active_venue.value,
                )
                withdrawals_query = withdrawals_query.filter(
                    Withdrawal.user_id == user_id
                )
                if profile.mode == TradingMode.DEMO.value:
                    withdrawals_query = withdrawals_query.filter(False)
            positions = positions_query.order_by(Position.created_at.desc()).all()
            position_ids = [item.id for item in positions]
            reconciliations = []
            if position_ids:
                reconciliations = session.query(Reconciliation).filter(Reconciliation.position_id.in_(position_ids)).all()
            return StateResponse(
                user=user_response(user, identity) if user and identity else None,
                wallet=wallet_response(wallet) if wallet else None,
                tradingProfile=trading_profile_response(profile) if profile else None,
                positions=[position_response(item) for item in positions],
                intents=[intent_response(item) for item in intents_query.order_by(TradeIntent.created_at.desc()).all()],
                executionAttempts=[execution_response(item) for item in executions_query.order_by(ExecutionAttempt.created_at.desc()).all()],
                reconciliations=[reconciliation_response(item) for item in reconciliations],
                withdrawals=[withdrawal_response(item) for item in withdrawals_query.order_by(Withdrawal.created_at.desc()).all()],
            )

    def _idempotent_lookup(
        self,
        session,
        user_id: str,
        trading_mode: str,
        profile_season: int,
        key: str,
        request_hash: str,
    ) -> AcceptedTradeResponse | None:
        intent = session.query(TradeIntent).filter(
            TradeIntent.user_id == user_id,
            TradeIntent.trading_mode == trading_mode,
            TradeIntent.profile_season == profile_season,
            TradeIntent.idempotency_key == key,
        ).one_or_none()
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

    def _wallet_for_user(
        self,
        session,
        user_id: str,
        *,
        chain_id: int,
        custody_provider: str,
        now: datetime,
        venue: VenueMode = VenueMode.GTRADE,
    ) -> WalletAccount:
        wallet = _venue_wallet(session, user_id, venue, self.chain_id)
        if wallet is not None:
            return wallet
        address, encrypted_private_key = self._new_wallet(venue)
        wallet = WalletAccount(
            id=_id("wallet"),
            user_id=user_id,
            chain_id=chain_id,
            address=address,
            wallet_type=WalletType.PLATFORM_CUSTODY.value,
            status=WalletStatus.ACTIVE.value,
            custody_provider=custody_provider,
            custody_key_ref=f"encrypted_postgres:{user_id}:{venue.value}",
            encrypted_private_key=encrypted_private_key,
            gas_wallet=False,
            payload={"venue": venue.value},
            created_at=now,
            updated_at=now,
        )
        session.add(wallet)
        session.flush()
        return wallet

    def _ensure_trading_profiles(self, session, user_id: str, *, now: datetime) -> None:
        existing = {
            profile.mode
            for profile in session.query(TradingProfile).filter(TradingProfile.user_id == user_id).all()
        }
        if TradingMode.LIVE.value not in existing:
            session.add(
                TradingProfile(
                    id=_id("profile"),
                    user_id=user_id,
                    mode=TradingMode.LIVE.value,
                    current_season=1,
                    starting_balance_usd=None,
                    balance_usd=None,
                    reset_count=0,
                    created_at=now,
                    updated_at=now,
                )
            )
        if TradingMode.DEMO.value not in existing:
            session.add(
                TradingProfile(
                    id=_id("profile"),
                    user_id=user_id,
                    mode=TradingMode.DEMO.value,
                    current_season=1,
                    starting_balance_usd=Decimal("1000"),
                    balance_usd=Decimal("1000"),
                    reset_count=0,
                    created_at=now,
                    updated_at=now,
                )
            )

    def _new_wallet(self, venue: VenueMode) -> tuple[str, bytes | None]:
        if self.custody_provider == "development":
            seed = uuid.uuid4().hex
            return _dev_address(seed), None
        cipher = PrivateKeyCipher(self._settings.custody_private_key_encryption_key)
        factory = PlatformWalletFactory(cipher)
        generated = (
            factory.create_solana_wallet()
            if venue == VenueMode.FLASH
            else factory.create_arbitrum_wallet()
        )
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


def _active_venue(session, user_id: str) -> VenueMode:
    user = session.get(User, user_id)
    if user is None:
        raise StoreNotFound("user not found")
    return VenueMode(user.active_venue)


def _chain_id_for_venue(venue: VenueMode, arbitrum_chain_id: int) -> int:
    if venue == VenueMode.FLASH:
        return SOLANA_MAINNET_CHAIN_ID
    if venue == VenueMode.AVANTIS:
        return 8453
    return arbitrum_chain_id


def _venue_wallet(
    session,
    user_id: str,
    venue: VenueMode,
    arbitrum_chain_id: int,
) -> WalletAccount | None:
    return (
        session.query(WalletAccount)
        .filter(
            WalletAccount.user_id == user_id,
            WalletAccount.chain_id == _chain_id_for_venue(venue, arbitrum_chain_id),
            WalletAccount.status == WalletStatus.ACTIVE.value,
        )
        .order_by(WalletAccount.created_at.asc())
        .first()
    )


def _profile_for_mode(session, user_id: str, mode: str) -> TradingProfile:
    profile = (
        session.query(TradingProfile)
        .filter(
            TradingProfile.user_id == user_id,
            TradingProfile.mode == mode,
        )
        .one_or_none()
    )
    if profile is None:
        raise StoreNotFound("trading profile not found")
    return profile


def _active_profile(session, user_id: str, *, for_update: bool = False) -> TradingProfile:
    user = session.get(User, user_id)
    if user is None:
        raise StoreNotFound("user not found")
    query = session.query(TradingProfile).filter(
        TradingProfile.user_id == user_id,
        TradingProfile.mode == user.active_trading_mode,
    )
    if for_update:
        query = query.with_for_update()
    profile = query.one_or_none()
    if profile is None:
        now = _now()
        live = TradingProfile(
            id=_id("profile"),
            user_id=user_id,
            mode=TradingMode.LIVE.value,
            current_season=1,
            starting_balance_usd=None,
            balance_usd=None,
            reset_count=0,
            created_at=now,
            updated_at=now,
        )
        demo = TradingProfile(
            id=_id("profile"),
            user_id=user_id,
            mode=TradingMode.DEMO.value,
            current_season=1,
            starting_balance_usd=Decimal("1000"),
            balance_usd=Decimal("1000"),
            reset_count=0,
            created_at=now,
            updated_at=now,
        )
        session.add_all([live, demo])
        session.flush()
        profile = live if user.active_trading_mode == TradingMode.LIVE.value else demo
        if for_update:
            profile = (
                session.query(TradingProfile)
                .filter(TradingProfile.id == profile.id)
                .with_for_update()
                .one()
            )
    return profile


def _active_position_exists(
    session,
    user_id: str,
    *,
    trading_mode: str | None = None,
    profile_season: int | None = None,
) -> bool:
    query = session.query(Position.id).filter(
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
    if trading_mode is not None:
        query = query.filter(Position.trading_mode == trading_mode)
    if profile_season is not None:
        query = query.filter(Position.profile_season == profile_season)
    return (
        query.first() is not None
    )


def _pending_withdrawal_exists(session, user_id: str) -> bool:
    return (
        session.query(Withdrawal.id)
        .filter(
            Withdrawal.user_id == user_id,
            Withdrawal.status.in_(
                [
                    WithdrawalStatus.REQUESTED.value,
                    WithdrawalStatus.VALIDATED.value,
                    WithdrawalStatus.SIGNED.value,
                    WithdrawalStatus.BROADCAST.value,
                    WithdrawalStatus.UNKNOWN.value,
                ]
            ),
        )
        .first()
        is not None
    )


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> datetime:
    return datetime.now(UTC)


def _placeholder_email(invite_id: str) -> str:
    return f"invite+{invite_id}@pending.tick.local"


def _market(value: str) -> str:
    return value.upper().replace("/", "-")


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _dev_address(seed: str) -> str:
    digest = hashlib.sha256(f"tick-dev-wallet:{seed}".encode()).hexdigest()
    return f"0x{digest[-40:]}"
