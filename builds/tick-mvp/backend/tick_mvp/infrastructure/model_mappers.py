from __future__ import annotations

from tick_mvp.domain.schemas import (
    ExecutionAttemptResponse,
    PositionResponse,
    QuoteResponse,
    ReconciliationResponse,
    TradeIntentResponse,
    UserResponse,
    WalletAccountResponse,
    WithdrawalResponse,
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


def user_response(user: User, identity: AuthIdentity) -> UserResponse:
    return UserResponse(
        id=user.id,
        authProvider=AuthProvider(identity.provider),
        providerSubject=identity.provider_subject,
        email=user.email,
        displayName=user.display_name,
        avatarUrl=user.avatar_url,
        status=UserStatus(user.status),
        createdAt=user.created_at,
        lastLoginAt=user.last_login_at,
    )


def wallet_response(wallet: WalletAccount) -> WalletAccountResponse:
    return WalletAccountResponse(
        id=wallet.id,
        userId=wallet.user_id,
        chainId=wallet.chain_id,
        address=wallet.address,
        walletType=WalletType(wallet.wallet_type),
        status=WalletStatus(wallet.status),
        custodyProvider=wallet.custody_provider,
        custodyKeyRef=wallet.custody_key_ref,
        createdAt=wallet.created_at,
        updatedAt=wallet.updated_at,
    )


def quote_response(quote: Quote) -> QuoteResponse:
    return QuoteResponse(
        quoteId=quote.id,
        userId=quote.user_id,
        venue=quote.venue,
        market=quote.market,
        side=TradeSide(quote.side),
        ticketUsd=quote.ticket_usd,
        leverage=quote.leverage,
        notionalUsd=quote.notional_usd,
        maxLossUsd=quote.max_loss_usd,
        estimatedOpenCostUsd=quote.estimated_open_cost_usd,
        estimatedCloseCostUsd=quote.estimated_close_cost_usd,
        estimatedRoundTripCostUsd=quote.estimated_round_trip_cost_usd,
        liquidationPrice=quote.liquidation_price,
        stopLossPrice=quote.stop_loss_price,
        openingAllowed=quote.opening_allowed,
        riskDecisionId=quote.risk_decision_id,
        createdAt=quote.created_at,
        expiresAt=quote.expires_at,
    )


def intent_response(intent: TradeIntent) -> TradeIntentResponse:
    return TradeIntentResponse(
        id=intent.id,
        userId=intent.user_id,
        idempotencyKey=intent.idempotency_key,
        action=TradeAction(intent.action),
        status=TradeIntentStatus(intent.status),
        quoteId=intent.quote_id,
        positionId=intent.position_id,
        market=intent.market,
        side=TradeSide(intent.side) if intent.side else None,
        createdAt=intent.created_at,
        updatedAt=intent.updated_at,
    )


def execution_response(execution: ExecutionAttempt) -> ExecutionAttemptResponse:
    return ExecutionAttemptResponse(
        id=execution.id,
        tradeIntentId=execution.trade_intent_id,
        userId=execution.user_id,
        venue=execution.venue,
        action=TradeAction(execution.action),
        status=ExecutionAttemptStatus(execution.status),
        txHash=execution.tx_hash,
        createdAt=execution.created_at,
        updatedAt=execution.updated_at,
    )


def position_response(position: Position) -> PositionResponse:
    return PositionResponse(
        id=position.id,
        userId=position.user_id,
        venue=position.venue,
        market=position.market,
        side=TradeSide(position.side),
        status=PositionStatus(position.status),
        quoteId=position.quote_id,
        openIntentId=position.open_intent_id,
        closeIntentId=position.close_intent_id,
        ticketUsd=position.ticket_usd,
        leverage=position.leverage,
        notionalUsd=position.notional_usd,
        entryPrice=position.entry_price,
        stopLossPrice=position.stop_loss_price,
        liquidationPrice=position.liquidation_price,
        createdAt=position.created_at,
        updatedAt=position.updated_at,
        openedAt=position.opened_at,
    )


def reconciliation_response(reconciliation: Reconciliation) -> ReconciliationResponse:
    return ReconciliationResponse(
        id=reconciliation.id,
        positionId=reconciliation.position_id,
        status=ReconciliationStatus(reconciliation.status),
        venueRealizedPnlUsd=reconciliation.venue_realized_pnl_usd,
        walletDeltaUsd=reconciliation.wallet_delta_usd,
        differenceUsd=reconciliation.difference_usd,
        createdAt=reconciliation.created_at,
        updatedAt=reconciliation.updated_at,
    )


def withdrawal_response(withdrawal: Withdrawal) -> WithdrawalResponse:
    return WithdrawalResponse(
        id=withdrawal.id,
        userId=withdrawal.user_id,
        walletId=withdrawal.wallet_id,
        asset=withdrawal.asset,
        amount=withdrawal.amount,
        destinationAddress=withdrawal.destination_address,
        status=WithdrawalStatus(withdrawal.status),
        txHash=withdrawal.tx_hash,
        createdAt=withdrawal.created_at,
        updatedAt=withdrawal.updated_at,
    )
