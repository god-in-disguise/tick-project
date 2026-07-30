from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.accounting import net_wallet_delta
from tick_mvp.domain.states import ExecutionAttemptStatus, PositionStatus, ReconciliationStatus, TradeAction, TradeIntentStatus, TradeSide
from tick_mvp.infrastructure.custody import PrivateKeyCipher
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.memory_store import StoreNotFound
from tick_mvp.infrastructure.models import (
    ExecutionAttempt,
    LedgerEvent,
    Position,
    Quote,
    Reconciliation,
    TradeIntent,
    WalletAccount,
)
from tick_mvp.venues.base import VenueCloseResult, VenueOpenResult


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    execution_id: str
    intent_id: str
    user_id: str
    action: TradeAction
    market: str
    side: TradeSide
    wallet_id: str
    wallet_address: str
    private_key_hex: str
    quote_id: str | None
    position_id: str | None
    ticket_usd: Decimal
    leverage: Decimal
    notional_usd: Decimal
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    liquidation_price: Decimal | None
    venue_position_id: str | None
    quote_payload: dict[str, Any]
    account_balance_before_open_usd: Decimal | None = None


class ExecutionRepository:
    def __init__(self, settings: Settings | None = None, session_factory=None) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory or create_session_factory()

    def load(self, execution_attempt_id: str) -> ExecutionContext:
        with session_scope(self._session_factory) as session:
            execution = session.get(ExecutionAttempt, execution_attempt_id)
            if execution is None:
                raise StoreNotFound("execution attempt not found")
            intent = session.get(TradeIntent, execution.trade_intent_id)
            if intent is None:
                raise StoreNotFound("trade intent not found")
            wallet = session.get(WalletAccount, intent.wallet_id)
            if wallet is None:
                raise StoreNotFound("wallet not found")
            private_key = self._decrypt_wallet_key(wallet)
            quote = session.get(Quote, intent.quote_id) if intent.quote_id else None
            position = session.get(Position, intent.position_id) if intent.position_id else None
            if intent.action == TradeAction.OPEN.value:
                if quote is None or position is None:
                    raise StoreNotFound("open execution missing quote or position")
                market = quote.market
                side = TradeSide(quote.side)
                ticket_usd = Decimal(quote.ticket_usd)
                leverage = Decimal(quote.leverage)
                notional_usd = Decimal(quote.notional_usd)
                stop_loss_price = Decimal(quote.stop_loss_price) if quote.stop_loss_price is not None else None
                take_profit_price = Decimal(quote.take_profit_price) if quote.take_profit_price is not None else None
                liquidation_price = Decimal(quote.liquidation_price) if quote.liquidation_price is not None else None
                quote_payload = dict(quote.payload or {})
                position_id = position.id
                venue_position_id = position.venue_position_id
            else:
                if position is None:
                    raise StoreNotFound("close execution missing position")
                market = position.market
                side = TradeSide(position.side)
                ticket_usd = Decimal(position.ticket_usd)
                leverage = Decimal(position.leverage)
                notional_usd = Decimal(position.notional_usd)
                stop_loss_price = Decimal(position.stop_loss_price) if position.stop_loss_price is not None else None
                take_profit_price = Decimal(position.take_profit_price) if position.take_profit_price is not None else None
                liquidation_price = Decimal(position.liquidation_price) if position.liquidation_price is not None else None
                quote_payload = dict((quote.payload if quote else {}) or {})
                position_id = position.id
                venue_position_id = position.venue_position_id
            raw_balance_before_open = (position.payload or {}).get("accountBalanceBeforeOpenUsd")

            return ExecutionContext(
                execution_id=execution.id,
                intent_id=intent.id,
                user_id=execution.user_id,
                action=TradeAction(intent.action),
                market=market,
                side=side,
                wallet_id=wallet.id,
                wallet_address=wallet.address,
                private_key_hex=private_key,
                quote_id=intent.quote_id,
                position_id=position_id,
                ticket_usd=ticket_usd,
                leverage=leverage,
                notional_usd=notional_usd,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                liquidation_price=liquidation_price,
                venue_position_id=venue_position_id,
                quote_payload=quote_payload,
                account_balance_before_open_usd=(
                    Decimal(str(raw_balance_before_open))
                    if raw_balance_before_open is not None
                    else None
                ),
            )

    def load_user_wallet_credentials(self, user_id: str) -> tuple[str, str]:
        _, address, private_key = self.load_user_wallet_context(user_id)
        return address, private_key

    def load_user_wallet_context(self, user_id: str) -> tuple[str, str, str]:
        with session_scope(self._session_factory) as session:
            wallet = (
                session.query(WalletAccount)
                .filter(WalletAccount.user_id == user_id)
                .order_by(WalletAccount.created_at.asc())
                .first()
            )
            if wallet is None:
                raise StoreNotFound("wallet not found")
            return wallet.id, wallet.address, self._decrypt_wallet_key(wallet)

    def mark_broadcast_pending(
        self,
        context: ExecutionContext,
        *,
        tx_hash: str,
        nonce: int,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            execution = _execution(session, context.execution_id)
            prepared_transaction = {
                "txHash": tx_hash,
                "nonce": nonce,
                "preparedAt": now.isoformat(),
            }
            payload = execution.payload or {}
            prepared_transactions = list(payload.get("preparedTransactions") or [])
            prepared_transactions.append(prepared_transaction)
            execution.status = ExecutionAttemptStatus.BROADCAST_PENDING.value
            execution.tx_hash = tx_hash
            execution.nonce = nonce
            execution.payload = {
                **payload,
                "preparedTransaction": prepared_transaction,
                "preparedTransactions": prepared_transactions,
            }
            execution.updated_at = now

    def mark_open_result(self, context: ExecutionContext, result: VenueOpenResult) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            execution = _execution(session, context.execution_id)
            position = _position(session, context.position_id)
            intent = _intent(session, context.intent_id)
            _apply_tx_result(execution, result.tx)
            execution.payload = {**(execution.payload or {}), "openResult": result.payload}
            if result.account_balance_before_usd is not None:
                position.payload = {
                    **(position.payload or {}),
                    "accountBalanceBeforeOpenUsd": str(result.account_balance_before_usd),
                }
            if result.status == "open":
                execution.status = ExecutionAttemptStatus.VENUE_EXECUTED.value
                position.status = PositionStatus.OPEN.value
                position.venue_position_id = result.venue_position_id
                position.entry_price = result.entry_price
                position.liquidation_price = result.liquidation_price or position.liquidation_price
                position.stop_loss_price = result.stop_loss_price or position.stop_loss_price
                position.take_profit_price = result.take_profit_price or position.take_profit_price
                position.opened_at = result.opened_at
                intent.status = TradeIntentStatus.CONSUMED.value
            elif result.tx.status == "confirmed":
                execution.status = ExecutionAttemptStatus.AWAITING_VENUE_EXECUTION.value
            else:
                execution.status = ExecutionAttemptStatus.FAILED.value
                execution.error = "open initiation transaction reverted"
                position.status = PositionStatus.CLOSED.value
            execution.updated_at = now
            position.updated_at = now
            intent.updated_at = now

    def update_liquidation_price(
        self,
        position_id: str | None,
        liquidation_price: Decimal,
        *,
        source: str,
    ) -> None:
        if position_id is None:
            return
        now = _now()
        with session_scope(self._session_factory) as session:
            position = _position(session, position_id)
            position.liquidation_price = liquidation_price
            position.payload = {
                **(position.payload or {}),
                "liquidationPriceSource": source,
                "liquidationPriceUpdatedAt": now.isoformat(),
            }
            position.updated_at = now

    def mark_close_result(self, context: ExecutionContext, result: VenueCloseResult) -> Decimal | None:
        now = _now()
        wallet_delta_usd: Decimal | None = None
        with session_scope(self._session_factory) as session:
            execution = _execution(session, context.execution_id)
            position = _position(session, context.position_id)
            intent = _intent(session, context.intent_id)
            _apply_tx_result(execution, result.tx)
            execution.payload = {**(execution.payload or {}), "closeResult": result.payload}
            if result.status == "closed":
                execution.status = ExecutionAttemptStatus.VENUE_EXECUTED.value
                position.status = PositionStatus.CLOSED.value
                position.closed_at = result.closed_at
                intent.status = TradeIntentStatus.CONSUMED.value
                reconciliation = (
                    session.query(Reconciliation)
                    .filter(Reconciliation.position_id == position.id)
                    .order_by(Reconciliation.created_at.desc())
                    .first()
                )
                if reconciliation is not None:
                    wallet_delta_usd = _net_wallet_delta(
                        session,
                        position,
                        result.account_balance_after_usd,
                    )
                    reconciliation.status = (
                        ReconciliationStatus.WALLET_RECONCILED.value
                        if wallet_delta_usd is not None
                        else ReconciliationStatus.VENUE_ACCOUNTED.value
                    )
                    reconciliation.venue_realized_pnl_usd = result.venue_realized_pnl_usd
                    reconciliation.wallet_delta_usd = wallet_delta_usd
                    reconciliation.payload = {**(reconciliation.payload or {}), "closeResult": result.payload}
                    reconciliation.updated_at = now
            elif result.tx.status == "confirmed":
                execution.status = ExecutionAttemptStatus.AWAITING_VENUE_EXECUTION.value
            else:
                execution.status = ExecutionAttemptStatus.FAILED.value
                execution.error = "close initiation transaction reverted"
                position.status = PositionStatus.UNKNOWN.value
            execution.updated_at = now
            position.updated_at = now
            intent.updated_at = now
        return wallet_delta_usd

    def mark_close_reconciliation(
        self,
        context: ExecutionContext,
        *,
        account_balance_after_usd: Decimal,
    ) -> Decimal | None:
        now = _now()
        with session_scope(self._session_factory) as session:
            position = _position(session, context.position_id)
            reconciliation = (
                session.query(Reconciliation)
                .filter(Reconciliation.position_id == position.id)
                .order_by(Reconciliation.created_at.desc())
                .first()
            )
            if reconciliation is None:
                return None
            wallet_delta_usd = _net_wallet_delta(
                session,
                position,
                account_balance_after_usd,
            )
            reconciliation.status = (
                ReconciliationStatus.WALLET_RECONCILED.value
                if wallet_delta_usd is not None
                else ReconciliationStatus.VENUE_ACCOUNTED.value
            )
            reconciliation.wallet_delta_usd = wallet_delta_usd
            reconciliation.payload = {
                **(reconciliation.payload or {}),
                "accountBalanceAfterCloseUsd": str(account_balance_after_usd),
            }
            reconciliation.updated_at = now
            return wallet_delta_usd

    def mark_failed(self, context: ExecutionContext, error: str) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            execution = _execution(session, context.execution_id)
            position = _position(session, context.position_id)
            execution.status = ExecutionAttemptStatus.FAILED.value
            execution.error = error
            execution.updated_at = now
            position.status = PositionStatus.CLOSED.value if context.action == TradeAction.OPEN else PositionStatus.UNKNOWN.value
            position.payload = {**(position.payload or {}), "lastExecutionError": error}
            position.updated_at = now

    def _decrypt_wallet_key(self, wallet: WalletAccount) -> str:
        if not wallet.encrypted_private_key:
            raise StoreNotFound("wallet has no encrypted private key")
        return PrivateKeyCipher(self._settings.custody_private_key_encryption_key).decrypt(wallet.encrypted_private_key)


def _apply_tx_result(execution: ExecutionAttempt, tx: Any) -> None:
    execution.tx_hash = tx.tx_hash
    execution.nonce = tx.nonce
    execution.gas_cost_native = _gas_native(tx.gas_used, tx.effective_gas_price)
    execution.payload = {
        **(execution.payload or {}),
        "tx": tx.payload,
        "blockNumber": tx.block_number,
        "gasUsed": tx.gas_used,
        "effectiveGasPrice": tx.effective_gas_price,
    }


def _gas_native(gas_used: int | None, effective_gas_price: int | None) -> Decimal | None:
    if gas_used is None or effective_gas_price is None:
        return None
    return Decimal(gas_used * effective_gas_price) / Decimal(10**18)


def _net_wallet_delta(
    session,
    position: Position,
    account_balance_after_usd: Decimal | None,
) -> Decimal | None:
    gas_ledger_total = (
        session.query(func.coalesce(func.sum(LedgerEvent.amount), 0))
        .filter(
            LedgerEvent.position_id == position.id,
            LedgerEvent.event_type == "gas_charge",
            LedgerEvent.asset == "USDC",
        )
        .scalar()
    )
    return net_wallet_delta(
        position.payload,
        account_balance_after_usd,
        Decimal(gas_ledger_total or 0),
    )


def _execution(session, execution_id: str) -> ExecutionAttempt:
    execution = session.get(ExecutionAttempt, execution_id)
    if execution is None:
        raise StoreNotFound("execution attempt not found")
    return execution


def _position(session, position_id: str | None) -> Position:
    if position_id is None:
        raise StoreNotFound("position not found")
    position = session.get(Position, position_id)
    if position is None:
        raise StoreNotFound("position not found")
    return position


def _intent(session, intent_id: str) -> TradeIntent:
    intent = session.get(TradeIntent, intent_id)
    if intent is None:
        raise StoreNotFound("trade intent not found")
    return intent


def _now() -> datetime:
    return datetime.now(UTC)
