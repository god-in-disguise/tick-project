from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from tick_mvp.states import ExecutionAttemptStatus, PositionStatus, ReconciliationStatus, TradeAction, TradeIntentStatus, TradeSide


class QuoteRequest(BaseModel):
    market: str
    side: TradeSide
    ticketUsd: Decimal = Field(gt=0)
    leverage: Decimal = Field(gt=0)
    maxLossUsd: Decimal | None = Field(default=None, gt=0)


class DevSessionRequest(BaseModel):
    userId: str = Field(default="dev-user", min_length=1, max_length=120)
    walletAddress: str | None = Field(default=None, max_length=120)


class SessionResponse(BaseModel):
    token: str
    userId: str
    walletAddress: str | None = None
    tokenType: str = "bearer"
    expiresIn: int


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
    createdAt: datetime
    updatedAt: datetime


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


class StateResponse(BaseModel):
    positions: list[PositionResponse]
    intents: list[TradeIntentResponse]
    executionAttempts: list[ExecutionAttemptResponse]
    reconciliations: list[ReconciliationResponse]


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
