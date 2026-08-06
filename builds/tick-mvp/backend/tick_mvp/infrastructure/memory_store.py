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
    DemoResetResponse,
    DepositAddressResponse,
    ExecutionAttemptResponse,
    OpenRequest,
    PositionResponse,
    QuoteRequest,
    QuoteResponse,
    ReconciliationResponse,
    StateResponse,
    TradeIntentResponse,
    TradingProfileResponse,
    UserResponse,
    VenueModeResponse,
    WalletAccountResponse,
    WalletBalancesResponse,
    WithdrawalRequest,
    WithdrawalResponse,
)
from tick_mvp.domain.invitations import InviteAuthError
from tick_mvp.domain.states import (
    AuthProvider,
    ExecutionAttemptStatus,
    PositionStatus,
    ReconciliationStatus,
    TradeAction,
    TradeIntentStatus,
    TradingMode,
    UserStatus,
    VenueMode,
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


@dataclass(slots=True)
class InviteRecord:
    id: str
    code_hash: str
    display_name: str | None
    status: str
    expires_at: datetime | None
    redeemed_by_user_id: str | None = None
    redeemed_at: datetime | None = None
    last_used_at: datetime | None = None


@dataclass
class MemoryStore:
    default_venue: str
    quote_ttl_seconds: int = 5
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _quotes: dict[str, QuoteRecord] = field(default_factory=dict)
    _users: dict[str, UserResponse] = field(default_factory=dict)
    _user_by_provider: dict[tuple[AuthProvider, str], str] = field(default_factory=dict)
    _invites_by_hash: dict[str, InviteRecord] = field(default_factory=dict)
    _wallets: dict[str, WalletAccountResponse] = field(default_factory=dict)
    _wallet_by_user: dict[tuple[str, VenueMode], str] = field(default_factory=dict)
    _intents: dict[str, TradeIntentResponse] = field(default_factory=dict)
    _executions: dict[str, ExecutionAttemptResponse] = field(default_factory=dict)
    _positions: dict[str, PositionResponse] = field(default_factory=dict)
    _reconciliations: dict[str, ReconciliationResponse] = field(default_factory=dict)
    _withdrawals: dict[str, WithdrawalResponse] = field(default_factory=dict)
    _profiles: dict[tuple[str, TradingMode], TradingProfileResponse] = field(default_factory=dict)
    _active_modes: dict[str, TradingMode] = field(default_factory=dict)
    _active_venues: dict[str, VenueMode] = field(default_factory=dict)
    _idempotency: dict[tuple[str, TradingMode, int, str], tuple[str, str]] = field(default_factory=dict)
    _withdrawal_idempotency: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)

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
    ) -> tuple[UserResponse, WalletAccountResponse]:
        now = _now()
        normalized_email = email.strip().lower()
        with self._lock:
            key = (provider, provider_subject)
            existing_user_id = self._user_by_provider.get(key)
            if existing_user_id is None:
                user = UserResponse(
                    id=_id("user"),
                    authProvider=provider,
                    providerSubject=provider_subject,
                    email=normalized_email,
                    displayName=display_name,
                    avatarUrl=avatar_url,
                    status=UserStatus.ACTIVE,
                    createdAt=now,
                    lastLoginAt=now,
                )
                self._users[user.id] = user
                self._user_by_provider[key] = user.id
                self._active_modes[user.id] = TradingMode.DEMO
                self._active_venues[user.id] = VenueMode.GTRADE
            else:
                previous = self._users[existing_user_id]
                user = previous.model_copy(
                    update={
                        "authProvider": provider,
                        "providerSubject": provider_subject,
                        "email": normalized_email,
                        "displayName": display_name or previous.displayName,
                        "avatarUrl": avatar_url or previous.avatarUrl,
                        "lastLoginAt": now,
                    }
                )
                self._users[user.id] = user

            wallet = self._wallet_for_user(user.id, chain_id=chain_id, custody_provider=custody_provider, now=now)
            self._ensure_profiles(user.id)
            return user, wallet

    def create_invite_code(
        self,
        *,
        code_hash: str,
        display_name: str | None = None,
        expires_at: datetime | None = None,
    ) -> str:
        with self._lock:
            invite = InviteRecord(
                id=_id("invite"),
                code_hash=code_hash,
                display_name=display_name,
                status="active",
                expires_at=expires_at,
            )
            self._invites_by_hash[code_hash] = invite
            return invite.id

    def redeem_invite_code(
        self,
        *,
        code_hash: str,
        chain_id: int,
        custody_provider: str,
    ) -> tuple[UserResponse, WalletAccountResponse]:
        now = _now()
        with self._lock:
            invite = self._invites_by_hash.get(code_hash)
            if (
                invite is None
                or invite.status != "active"
                or (invite.expires_at is not None and invite.expires_at <= now)
            ):
                raise InviteAuthError("invalid or expired invite")

            user, wallet = self.upsert_auth_user(
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
            return user, wallet

    def user(self, user_id: str) -> UserResponse:
        with self._lock:
            user = self._users.get(user_id)
        if user is None:
            raise StoreNotFound("user not found")
        return user

    def wallet_for_user(self, user_id: str, venue: VenueMode | str | None = None) -> WalletAccountResponse:
        with self._lock:
            selected = VenueMode(venue) if venue is not None else self._active_venue(user_id)
            wallet_id = self._wallet_by_user.get((user_id, selected))
            wallet = self._wallets.get(wallet_id or "")
        if wallet is None:
            raise StoreNotFound("wallet not found")
        return wallet

    def switch_venue(self, user_id: str, venue: VenueMode) -> VenueModeResponse:
        with self._lock:
            if any(
                item.userId == user_id
                and item.status in {
                    PositionStatus.OPENING,
                    PositionStatus.OPEN,
                    PositionStatus.CLOSING,
                    PositionStatus.UNKNOWN,
                }
                for item in self._positions.values()
            ):
                raise StoreConflict("finish the active trade before switching venue")
            user = self._users.get(user_id)
            if user is None:
                raise StoreNotFound("user not found")
            now = _now()
            chain_id = (
                501
                if venue == VenueMode.FLASH
                else 8453
                if venue == VenueMode.AVANTIS
                else 42161
            )
            wallet = self._wallet_for_user(
                user_id,
                chain_id=chain_id,
                custody_provider="development",
                now=now,
                venue=venue,
            )
            self._active_venues[user_id] = venue
            self._users[user_id] = user.model_copy(update={"activeVenue": venue})
            return VenueModeResponse(venue=venue, wallet=wallet)

    def trading_profile(self, user_id: str) -> TradingProfileResponse:
        with self._lock:
            self._ensure_profiles(user_id)
            return self._profiles[(user_id, self._active_mode(user_id))]

    def switch_trading_mode(self, user_id: str, mode: TradingMode) -> TradingProfileResponse:
        with self._lock:
            if any(
                item.userId == user_id
                and item.status in {
                    PositionStatus.OPENING,
                    PositionStatus.OPEN,
                    PositionStatus.CLOSING,
                    PositionStatus.UNKNOWN,
                }
                for item in self._positions.values()
            ):
                raise StoreConflict("finish the active trade before switching mode")
            self._ensure_profiles(user_id)
            user = self._users.get(user_id)
            if user is None:
                raise StoreNotFound("user not found")
            self._active_modes[user_id] = mode
            return self._profiles[(user_id, mode)]

    def reset_demo_profile(self, user_id: str) -> DemoResetResponse:
        now = _now()
        with self._lock:
            self._ensure_profiles(user_id)
            profile = self._profiles[(user_id, TradingMode.DEMO)]
            if any(
                item.userId == user_id
                and item.tradingMode == TradingMode.DEMO
                and item.profileSeason == profile.season
                and item.status in {
                    PositionStatus.OPENING,
                    PositionStatus.OPEN,
                    PositionStatus.CLOSING,
                    PositionStatus.UNKNOWN,
                }
                for item in self._positions.values()
            ):
                raise StoreConflict("close the demo trade before resetting")
            ending = Decimal(profile.balanceUsd or 0)
            starting = Decimal(profile.startingBalanceUsd or 1000)
            completed = [
                item
                for item in self._positions.values()
                if item.userId == user_id
                and item.tradingMode == TradingMode.DEMO
                and item.profileSeason == profile.season
                and item.status in {PositionStatus.CLOSED, PositionStatus.LIQUIDATED}
            ]
            position_ids = {item.id for item in completed}
            settled = [
                item
                for item in self._reconciliations.values()
                if item.positionId in position_ids and item.walletDeltaUsd is not None
            ]
            updated = profile.model_copy(
                update={
                    "season": profile.season + 1,
                    "startingBalanceUsd": Decimal("1000"),
                    "balanceUsd": Decimal("1000"),
                    "resetCount": profile.resetCount + 1,
                    "lastResetAt": now,
                }
            )
            self._profiles[(user_id, TradingMode.DEMO)] = updated
            return DemoResetResponse(
                profile=updated,
                endedSeason=profile.season,
                endingBalanceUsd=ending,
                realizedPnlUsd=ending - starting,
                tradeCount=len(settled),
                winCount=sum(1 for item in settled if Decimal(item.walletDeltaUsd or 0) > 0),
                resetAt=now,
            )

    def demo_balances(self, user_id: str) -> WalletBalancesResponse | None:
        profile = self.trading_profile(user_id)
        if profile.mode != TradingMode.DEMO:
            return None
        balance = Decimal(profile.balanceUsd or 0)
        return WalletBalancesResponse(
            chainId=42161,
            address="demo",
            usdc=balance,
            gasChargesUsdc=Decimal(0),
            spendableUsdc=balance,
            source="demo_ledger",
            fetchedAt=_now(),
            tradingMode=TradingMode.DEMO,
            profileSeason=profile.season,
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
        del venue
        return Decimal(0)

    def request_withdrawal(self, user_id: str, request: WithdrawalRequest) -> WithdrawalResponse:
        payload_hash = _hash_payload(request.model_dump(mode="json"))
        with self._lock:
            if self._active_mode(user_id) == TradingMode.DEMO:
                raise StoreConflict("withdrawals are unavailable in demo mode")
            venue = self._active_venue(user_id)
            existing = self._withdrawal_idempotency.get((user_id, request.idempotencyKey))
            if existing is not None:
                previous_hash, withdrawal_id = existing
                if previous_hash != payload_hash:
                    raise StoreConflict("idempotency key reused with different payload")
                return self._withdrawals[withdrawal_id]

            wallet_id = self._wallet_by_user.get((user_id, venue))
            if wallet_id is None:
                raise StoreNotFound("wallet not found")
            if request.asset.upper() != "USDC":
                raise StoreConflict("only USDC withdrawals are supported")
            if any(
                item.userId == user_id
                and item.status
                in {
                    PositionStatus.OPENING,
                    PositionStatus.OPEN,
                    PositionStatus.CLOSING,
                    PositionStatus.UNKNOWN,
                }
                for item in self._positions.values()
            ):
                raise StoreConflict("withdrawal unavailable while a position is active")
            if any(
                item.userId == user_id
                and item.status
                in {
                    WithdrawalStatus.REQUESTED,
                    WithdrawalStatus.VALIDATED,
                    WithdrawalStatus.SIGNED,
                    WithdrawalStatus.BROADCAST,
                    WithdrawalStatus.UNKNOWN,
                }
                for item in self._withdrawals.values()
            ):
                raise StoreConflict("user already has a pending withdrawal")
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
        profile = self.trading_profile(user_id)
        response = QuoteResponse(
            quoteId=quote_id,
            userId=user_id,
            tradingMode=profile.mode,
            profileSeason=profile.season,
            venue=self._active_venue(user_id).value,
            market=_market(request.market),
            side=request.side,
            ticketUsd=request.ticketUsd,
            leverage=request.leverage,
            notionalUsd=notional,
            maxLossUsd=request.maxLossUsd,
            takeProfitUsd=request.takeProfitUsd,
            estimatedOpenCostUsd=estimated_open,
            estimatedCloseCostUsd=estimated_close,
            estimatedRoundTripCostUsd=estimated_open + estimated_close,
            liquidationPrice=None,
            stopLossPrice=None,
            takeProfitPrice=None,
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
            profile = self.trading_profile(user_id)
            existing = self._idempotent_lookup(user_id, profile, request.idempotencyKey, payload_hash)
            if existing is not None:
                return existing

            quote = self._quotes.get(request.quoteId)
            if quote is None:
                raise StoreNotFound("quote not found")
            if quote.response.expiresAt <= _now():
                raise StoreConflict("quote expired")
            if quote.response.tradingMode != profile.mode or quote.response.profileSeason != profile.season:
                raise StoreConflict("quote belongs to another trading profile")
            if quote.response.venue != self._active_venue(user_id).value:
                raise StoreConflict("quote belongs to another venue")
            if any(
                item.userId == user_id
                and item.tradingMode == profile.mode
                and item.profileSeason == profile.season
                and item.status in {PositionStatus.OPENING, PositionStatus.OPEN, PositionStatus.CLOSING, PositionStatus.UNKNOWN}
                for item in self._positions.values()
            ):
                raise StoreConflict("user already has an active position")
            if profile.mode == TradingMode.LIVE and any(
                item.userId == user_id
                and item.status
                in {
                    WithdrawalStatus.REQUESTED,
                    WithdrawalStatus.VALIDATED,
                    WithdrawalStatus.SIGNED,
                    WithdrawalStatus.BROADCAST,
                    WithdrawalStatus.UNKNOWN,
                }
                for item in self._withdrawals.values()
            ):
                raise StoreConflict("user has a pending withdrawal")

            now = _now()
            intent = TradeIntentResponse(
                id=_id("intent"),
                userId=user_id,
                tradingMode=profile.mode,
                profileSeason=profile.season,
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
                tradingMode=profile.mode,
                profileSeason=profile.season,
                venue=quote.response.venue,
                action=TradeAction.OPEN,
                status=ExecutionAttemptStatus.CREATED,
                createdAt=now,
                updatedAt=now,
            )
            position = PositionResponse(
                id=_id("pos"),
                userId=user_id,
                tradingMode=profile.mode,
                profileSeason=profile.season,
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
                takeProfitPrice=quote.response.takeProfitPrice,
                liquidationPrice=quote.response.liquidationPrice,
                createdAt=now,
                updatedAt=now,
            )
            intent = intent.model_copy(update={"positionId": position.id, "updatedAt": now})
            self._intents[intent.id] = intent
            self._executions[execution.id] = execution
            self._positions[position.id] = position
            self._idempotency[(user_id, profile.mode, profile.season, request.idempotencyKey)] = (payload_hash, execution.id)
            return AcceptedTradeResponse(intent=intent, executionAttempt=execution, position=position)

    def accept_close(self, user_id: str, request: CloseRequest) -> AcceptedTradeResponse:
        payload_hash = _hash_payload(request.model_dump(mode="json"))
        with self._lock:
            profile = self.trading_profile(user_id)
            existing = self._idempotent_lookup(user_id, profile, request.idempotencyKey, payload_hash)
            if existing is not None:
                return existing

            position = self._positions.get(request.positionId)
            if (
                position is None
                or position.userId != user_id
                or position.tradingMode != profile.mode
                or position.profileSeason != profile.season
            ):
                raise StoreNotFound("position not found")
            if position.status not in {PositionStatus.OPENING, PositionStatus.OPEN, PositionStatus.UNKNOWN}:
                raise StoreConflict(f"position cannot close from {position.status}")

            now = _now()
            intent = TradeIntentResponse(
                id=_id("intent"),
                userId=user_id,
                tradingMode=profile.mode,
                profileSeason=profile.season,
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
                tradingMode=profile.mode,
                profileSeason=profile.season,
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
            self._idempotency[(user_id, profile.mode, profile.season, request.idempotencyKey)] = (payload_hash, execution.id)
            return AcceptedTradeResponse(intent=intent, executionAttempt=execution, position=updated_position)

    def state(self, user_id: str | None = None) -> StateResponse:
        with self._lock:
            positions = list(self._positions.values())
            intents = list(self._intents.values())
            executions = list(self._executions.values())
            reconciliations = list(self._reconciliations.values())
            withdrawals = list(self._withdrawals.values())
            user = self._users.get(user_id or "")
            active_venue = self._active_venue(user_id) if user_id else VenueMode.GTRADE
            wallet = self._wallets.get(self._wallet_by_user.get((user_id or "", active_venue)) or "")
            profile = self.trading_profile(user_id) if user_id else None
        if user_id is not None:
            positions = [item for item in positions if item.userId == user_id and item.tradingMode == profile.mode and item.profileSeason == profile.season and item.venue == active_venue.value]
            intents = [item for item in intents if item.userId == user_id and item.tradingMode == profile.mode and item.profileSeason == profile.season]
            executions = [item for item in executions if item.userId == user_id and item.tradingMode == profile.mode and item.profileSeason == profile.season and item.venue == active_venue.value]
            withdrawals = [item for item in withdrawals if item.userId == user_id and profile.mode == TradingMode.LIVE]
            position_ids = {item.id for item in positions}
            reconciliations = [item for item in reconciliations if item.positionId in position_ids]
        return StateResponse(
            user=user,
            wallet=wallet,
            tradingProfile=profile,
            positions=positions,
            intents=intents,
            executionAttempts=executions,
            reconciliations=reconciliations,
            withdrawals=withdrawals,
        )

    def _idempotent_lookup(self, user_id: str, profile: TradingProfileResponse, key: str, payload_hash: str) -> AcceptedTradeResponse | None:
        existing = self._idempotency.get((user_id, profile.mode, profile.season, key))
        if existing is None:
            return None
        previous_hash, execution_id = existing
        if previous_hash != payload_hash:
            raise StoreConflict("idempotency key reused with different payload")
        execution = self._executions[execution_id]
        intent = self._intents[execution.tradeIntentId]
        position = self._positions.get(intent.positionId or "")
        return AcceptedTradeResponse(intent=intent, executionAttempt=execution, position=position)

    def _wallet_for_user(
        self,
        user_id: str,
        *,
        chain_id: int,
        custody_provider: str,
        now: datetime,
        venue: VenueMode = VenueMode.GTRADE,
    ) -> WalletAccountResponse:
        wallet_id = self._wallet_by_user.get((user_id, venue))
        if wallet_id is not None:
            return self._wallets[wallet_id]
        wallet = WalletAccountResponse(
            id=_id("wallet"),
            userId=user_id,
            chainId=chain_id,
            address=_dev_address(f"{user_id}:{venue.value}"),
            walletType=WalletType.PLATFORM_CUSTODY,
            status=WalletStatus.ACTIVE,
            custodyProvider=custody_provider,
            custodyKeyRef=f"development:{user_id}:{venue.value}",
            createdAt=now,
            updatedAt=now,
        )
        self._wallets[wallet.id] = wallet
        self._wallet_by_user[(user_id, venue)] = wallet.id
        return wallet

    def _ensure_profiles(self, user_id: str) -> None:
        if (user_id, TradingMode.LIVE) not in self._profiles:
            self._profiles[(user_id, TradingMode.LIVE)] = TradingProfileResponse(
                mode=TradingMode.LIVE,
                season=1,
                startingBalanceUsd=None,
                balanceUsd=None,
            )
        if (user_id, TradingMode.DEMO) not in self._profiles:
            self._profiles[(user_id, TradingMode.DEMO)] = TradingProfileResponse(
                mode=TradingMode.DEMO,
                season=1,
                startingBalanceUsd=Decimal("1000"),
                balanceUsd=Decimal("1000"),
            )

    def _active_mode(self, user_id: str) -> TradingMode:
        self._ensure_profiles(user_id)
        return self._active_modes.get(user_id, TradingMode.LIVE)

    def _active_venue(self, user_id: str) -> VenueMode:
        return self._active_venues.get(user_id, VenueMode.GTRADE)


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
