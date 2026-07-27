from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

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


class QuoteRequest(BaseModel):
    market: str
    side: TradeSide
    ticketUsd: Decimal = Field(gt=0)
    leverage: Decimal = Field(gt=0)
    maxLossUsd: Decimal | None = Field(default=None, gt=0)


class DevSessionRequest(BaseModel):
    userId: str = Field(default="dev-user", min_length=1, max_length=120)
    walletAddress: str | None = Field(default=None, max_length=120)


class GoogleSessionRequest(BaseModel):
    idToken: str = Field(min_length=1)
    nonce: str | None = Field(default=None, max_length=160)
    devEmail: str | None = Field(default=None, max_length=320)
    devName: str | None = Field(default=None, max_length=160)


class UserResponse(BaseModel):
    id: str
    authProvider: AuthProvider
    providerSubject: str
    email: str
    displayName: str | None = None
    avatarUrl: str | None = None
    status: UserStatus
    createdAt: datetime
    lastLoginAt: datetime


class WalletAccountResponse(BaseModel):
    id: str
    userId: str
    chainId: int
    address: str
    walletType: WalletType
    status: WalletStatus
    custodyProvider: str
    custodyKeyRef: str
    createdAt: datetime
    updatedAt: datetime


class SessionResponse(BaseModel):
    token: str
    userId: str
    walletAddress: str | None = None
    tokenType: str = "bearer"
    expiresIn: int
    user: UserResponse | None = None
    wallet: WalletAccountResponse | None = None


class MeResponse(BaseModel):
    user: UserResponse
    wallet: WalletAccountResponse | None = None


class QuoteResponse(BaseModel):
    quoteId: str
    userId: str
    venue: str
    market: str
    side: TradeSide
    ticketUsd: Decimal
    leverage: Decimal
    notionalUsd: Decimal
    maxLossUsd: Decimal | None
    estimatedOpenCostUsd: Decimal
    estimatedCloseCostUsd: Decimal
    estimatedRoundTripCostUsd: Decimal
    liquidationPrice: Decimal | None
    stopLossPrice: Decimal | None
    openingAllowed: bool
    riskDecisionId: str
    createdAt: datetime
    expiresAt: datetime


class OpenRequest(BaseModel):
    quoteId: str
    idempotencyKey: str = Field(min_length=8, max_length=160)


class CloseRequest(BaseModel):
    positionId: str
    idempotencyKey: str = Field(min_length=8, max_length=160)


class DepositAddressResponse(BaseModel):
    chainId: int
    asset: str = "USDC"
    address: str
    walletId: str


class WalletBalancesResponse(BaseModel):
    chainId: int
    address: str
    nativeEth: Decimal | None = None
    usdc: Decimal | None = None
    gtradeAllowanceUsdc: Decimal | None = None
    source: str
    fetchedAt: datetime
    unavailableReason: str | None = None


class WithdrawalRequest(BaseModel):
    asset: str = Field(default="USDC", min_length=1, max_length=20)
    amount: Decimal = Field(gt=0)
    destinationAddress: str = Field(min_length=20, max_length=120)
    idempotencyKey: str = Field(min_length=8, max_length=160)


class WithdrawalResponse(BaseModel):
    id: str
    userId: str
    walletId: str
    asset: str
    amount: Decimal
    destinationAddress: str
    status: WithdrawalStatus
    txHash: str | None = None
    createdAt: datetime
    updatedAt: datetime


class TradeIntentResponse(BaseModel):
    id: str
    userId: str
    idempotencyKey: str
    action: TradeAction
    status: TradeIntentStatus
    quoteId: str | None
    positionId: str | None
    market: str
    side: TradeSide | None
    createdAt: datetime
    updatedAt: datetime


class ExecutionAttemptResponse(BaseModel):
    id: str
    tradeIntentId: str
    userId: str
    venue: str
    action: TradeAction
    status: ExecutionAttemptStatus
    txHash: str | None = None
    createdAt: datetime
    updatedAt: datetime


class JobDispatchResponse(BaseModel):
    jobId: str | None = None
    queued: bool


class PositionResponse(BaseModel):
    id: str
    userId: str
    venue: str
    market: str
    side: TradeSide
    status: PositionStatus
    quoteId: str | None
    openIntentId: str | None
    closeIntentId: str | None
    ticketUsd: Decimal
    leverage: Decimal
    notionalUsd: Decimal
    entryPrice: Decimal | None
    stopLossPrice: Decimal | None
    liquidationPrice: Decimal | None
    terminalReason: str | None = None
    createdAt: datetime
    updatedAt: datetime
    openedAt: datetime | None = None


class ReconciliationResponse(BaseModel):
    id: str
    positionId: str
    status: ReconciliationStatus
    venueRealizedPnlUsd: Decimal | None
    walletDeltaUsd: Decimal | None
    differenceUsd: Decimal | None
    createdAt: datetime
    updatedAt: datetime


class AcceptedTradeResponse(BaseModel):
    intent: TradeIntentResponse
    executionAttempt: ExecutionAttemptResponse
    position: PositionResponse | None = None
    job: JobDispatchResponse | None = None


class StateResponse(BaseModel):
    user: UserResponse | None = None
    wallet: WalletAccountResponse | None = None
    positions: list[PositionResponse]
    intents: list[TradeIntentResponse]
    executionAttempts: list[ExecutionAttemptResponse]
    reconciliations: list[ReconciliationResponse]
    withdrawals: list[WithdrawalResponse] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
