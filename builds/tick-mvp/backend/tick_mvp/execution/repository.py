from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.accounting import net_wallet_delta
from tick_mvp.domain.states import ExecutionAttemptStatus, PositionStatus, ReconciliationStatus, TradeAction, TradeIntentStatus, TradeSide, TradingMode
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
    TradingProfile,
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
    wallet_id: str | None
    wallet_address: str | None
    private_key_hex: str | None
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
    trading_mode: TradingMode = TradingMode.LIVE
    profile_season: int = 1
    max_loss_usd: Decimal | None = None
    take_profit_usd: Decimal | None = None
    entry_price: Decimal | None = None
    open_cost_usd: Decimal = Decimal(0)
    account_balance_before_open_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class DemoPositionSnapshot:
    position_id: str
    user_id: str
    profile_season: int
    venue: str
    market: str
    side: TradeSide
    ticket_usd: Decimal
    leverage: Decimal
    notional_usd: Decimal
    entry_price: Decimal
    stop_loss_price: Decimal | None
    take_profit_price: Decimal | None
    liquidation_price: Decimal | None
    max_loss_usd: Decimal | None
    take_profit_usd: Decimal | None
    open_cost_usd: Decimal


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
            trading_mode = TradingMode(execution.trading_mode)
            wallet = session.get(WalletAccount, intent.wallet_id) if intent.wallet_id else None
            if trading_mode == TradingMode.LIVE and wallet is None:
                raise StoreNotFound("wallet not found")
            private_key = self._decrypt_wallet_key(wallet) if wallet else None
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
                max_loss_usd = Decimal(quote.max_loss_usd) if quote.max_loss_usd is not None else None
                take_profit_usd = Decimal(quote.take_profit_usd) if quote.take_profit_usd is not None else None
                entry_price = None
                open_cost_usd = Decimal(quote.estimated_open_cost_usd)
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
                max_loss_usd = Decimal(quote.max_loss_usd) if quote and quote.max_loss_usd is not None else None
                take_profit_usd = Decimal(quote.take_profit_usd) if quote and quote.take_profit_usd is not None else None
                entry_price = Decimal(position.entry_price) if position.entry_price is not None else None
                open_cost_usd = Decimal(
                    (position.payload or {}).get("openCostUsd")
                    or (quote.estimated_open_cost_usd if quote else 0)
                )
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
                trading_mode=trading_mode,
                profile_season=execution.profile_season,
                action=TradeAction(intent.action),
                market=market,
                side=side,
                wallet_id=wallet.id if wallet else None,
                wallet_address=wallet.address if wallet else None,
                private_key_hex=private_key,
                quote_id=intent.quote_id,
                position_id=position_id,
                ticket_usd=ticket_usd,
                leverage=leverage,
                notional_usd=notional_usd,
                max_loss_usd=max_loss_usd,
                take_profit_usd=take_profit_usd,
                entry_price=entry_price,
                open_cost_usd=open_cost_usd,
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

    def mark_demo_open(
        self,
        context: ExecutionContext,
        *,
        entry_price: Decimal,
        liquidation_price: Decimal | None,
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        open_cost_usd: Decimal,
        close_cost_usd: Decimal,
        quote_payload: dict[str, Any],
        delay_ms: int,
    ) -> None:
        now = _now()
        with session_scope(self._session_factory) as session:
            profile = _demo_profile(session, context, for_update=True)
            execution = _execution(session, context.execution_id)
            position = _position(session, context.position_id)
            intent = _intent(session, context.intent_id)
            available = Decimal(profile.balance_usd or 0)
            if available < context.ticket_usd:
                raise ValueError(f"insufficient demo balance: {available:.2f} available")
            profile.balance_usd = available - context.ticket_usd
            profile.updated_at = now
            execution.status = ExecutionAttemptStatus.VENUE_EXECUTED.value
            execution.payload = {
                **(execution.payload or {}),
                "simulation": {
                    "delayMs": delay_ms,
                    "filledAt": now.isoformat(),
                    "source": "live_venue_quote",
                },
            }
            execution.updated_at = now
            position.status = PositionStatus.OPEN.value
            position.venue_position_id = f"demo:{position.id}"
            position.entry_price = entry_price
            position.liquidation_price = liquidation_price
            position.stop_loss_price = stop_loss_price
            position.take_profit_price = take_profit_price
            position.opened_at = now
            position.payload = {
                **(position.payload or {}),
                "simulation": True,
                "openCostUsd": str(open_cost_usd),
                "estimatedCloseCostUsd": str(close_cost_usd),
                "accountBalanceBeforeOpenUsd": str(available),
                "accountBalanceAfterOpenUsd": str(profile.balance_usd),
                "fillQuote": quote_payload,
            }
            position.updated_at = now
            intent.status = TradeIntentStatus.CONSUMED.value
            intent.updated_at = now
            session.add(
                LedgerEvent(
                    id=_id("ledger"),
                    user_id=context.user_id,
                    trading_mode=TradingMode.DEMO.value,
                    profile_season=context.profile_season,
                    position_id=position.id,
                    event_type="demo_collateral_locked",
                    asset="USDC",
                    amount=-context.ticket_usd,
                    source="demo_engine",
                    execution_attempt_id=execution.id,
                    payload={},
                    created_at=now,
                )
            )

    def mark_demo_close(
        self,
        context: ExecutionContext,
        *,
        exit_price: Decimal,
        gross_pnl_usd: Decimal,
        open_cost_usd: Decimal,
        close_cost_usd: Decimal,
        returned_usd: Decimal,
        reason: str,
        quote_payload: dict[str, Any],
        delay_ms: int,
    ) -> Decimal:
        now = _now()
        net_pnl = returned_usd - context.ticket_usd
        with session_scope(self._session_factory) as session:
            profile = _demo_profile(session, context, for_update=True)
            execution = _execution(session, context.execution_id)
            position = _position(session, context.position_id)
            intent = _intent(session, context.intent_id)
            balance_before = Decimal(profile.balance_usd or 0)
            profile.balance_usd = balance_before + returned_usd
            profile.updated_at = now
            execution.status = ExecutionAttemptStatus.VENUE_EXECUTED.value
            execution.payload = {
                **(execution.payload or {}),
                "simulation": {
                    "delayMs": delay_ms,
                    "filledAt": now.isoformat(),
                    "source": "live_venue_quote",
                },
            }
            execution.updated_at = now
            position.status = (
                PositionStatus.LIQUIDATED.value
                if reason == "liquidation"
                else PositionStatus.CLOSED.value
            )
            position.closed_at = now
            position.payload = {
                **(position.payload or {}),
                "terminalReason": reason,
                "exitPrice": str(exit_price),
                "grossPricePnlUsd": str(gross_pnl_usd),
                "openCostUsd": str(open_cost_usd),
                "closeCostUsd": str(close_cost_usd),
                "returnedUsd": str(returned_usd),
                "accountBalanceAfterCloseUsd": str(profile.balance_usd),
                "closeFillQuote": quote_payload,
            }
            position.updated_at = now
            intent.status = TradeIntentStatus.CONSUMED.value
            intent.updated_at = now
            reconciliation = (
                session.query(Reconciliation)
                .filter(Reconciliation.position_id == position.id)
                .order_by(Reconciliation.created_at.desc())
                .first()
            )
            if reconciliation is not None:
                reconciliation.status = ReconciliationStatus.WALLET_RECONCILED.value
                reconciliation.venue_realized_pnl_usd = net_pnl
                reconciliation.wallet_delta_usd = net_pnl
                reconciliation.difference_usd = Decimal(0)
                reconciliation.payload = {
                    **(reconciliation.payload or {}),
                    "source": "demo_engine",
                    "grossPricePnlUsd": str(gross_pnl_usd),
                    "openCostUsd": str(open_cost_usd),
                    "closeCostUsd": str(close_cost_usd),
                    "returnedUsd": str(returned_usd),
                }
                reconciliation.updated_at = now
            session.add(
                LedgerEvent(
                    id=_id("ledger"),
                    user_id=context.user_id,
                    trading_mode=TradingMode.DEMO.value,
                    profile_season=context.profile_season,
                    position_id=position.id,
                    event_type="demo_position_settled",
                    asset="USDC",
                    amount=returned_usd,
                    source="demo_engine",
                    execution_attempt_id=execution.id,
                    payload={"netPnlUsd": str(net_pnl)},
                    created_at=now,
                )
            )
        return net_pnl

    def open_demo_positions(self) -> list[DemoPositionSnapshot]:
        with session_scope(self._session_factory) as session:
            positions = (
                session.query(Position)
                .filter(
                    Position.trading_mode == TradingMode.DEMO.value,
                    Position.status == PositionStatus.OPEN.value,
                )
                .all()
            )
            snapshots: list[DemoPositionSnapshot] = []
            for position in positions:
                if position.entry_price is None:
                    continue
                quote = session.get(Quote, position.quote_id) if position.quote_id else None
                snapshots.append(
                    DemoPositionSnapshot(
                        position_id=position.id,
                        user_id=position.user_id,
                        profile_season=position.profile_season,
                        venue=position.venue,
                        market=position.market,
                        side=TradeSide(position.side),
                        ticket_usd=Decimal(position.ticket_usd),
                        leverage=Decimal(position.leverage),
                        notional_usd=Decimal(position.notional_usd),
                        entry_price=Decimal(position.entry_price),
                        stop_loss_price=(
                            Decimal(position.stop_loss_price)
                            if position.stop_loss_price is not None
                            else None
                        ),
                        take_profit_price=(
                            Decimal(position.take_profit_price)
                            if position.take_profit_price is not None
                            else None
                        ),
                        liquidation_price=(
                            Decimal(position.liquidation_price)
                            if position.liquidation_price is not None
                            else None
                        ),
                        max_loss_usd=(
                            Decimal(quote.max_loss_usd)
                            if quote and quote.max_loss_usd is not None
                            else None
                        ),
                        take_profit_usd=(
                            Decimal(quote.take_profit_usd)
                            if quote and quote.take_profit_usd is not None
                            else None
                        ),
                        open_cost_usd=Decimal(
                            (position.payload or {}).get("openCostUsd")
                            or (quote.estimated_open_cost_usd if quote else 0)
                        ),
                    )
                )
            return snapshots

    def settle_demo_terminal(
        self,
        snapshot: DemoPositionSnapshot,
        *,
        exit_price: Decimal,
        gross_pnl_usd: Decimal,
        close_cost_usd: Decimal,
        returned_usd: Decimal,
        reason: str,
        quote_payload: dict[str, Any],
    ) -> bool:
        now = _now()
        net_pnl = returned_usd - snapshot.ticket_usd
        with session_scope(self._session_factory) as session:
            position = (
                session.query(Position)
                .filter(Position.id == snapshot.position_id)
                .with_for_update()
                .one_or_none()
            )
            if position is None or position.status != PositionStatus.OPEN.value:
                return False
            profile = (
                session.query(TradingProfile)
                .filter(
                    TradingProfile.user_id == snapshot.user_id,
                    TradingProfile.mode == TradingMode.DEMO.value,
                    TradingProfile.current_season == snapshot.profile_season,
                )
                .with_for_update()
                .one_or_none()
            )
            if profile is None:
                return False
            intent = TradeIntent(
                id=_id("intent"),
                user_id=snapshot.user_id,
                trading_mode=TradingMode.DEMO.value,
                profile_season=snapshot.profile_season,
                idempotency_key=f"demo-terminal:{position.id}:{reason}",
                request_hash=f"demo-terminal:{position.id}:{reason}",
                action=TradeAction.CLOSE.value,
                status=TradeIntentStatus.CONSUMED.value,
                quote_id=position.quote_id,
                position_id=position.id,
                wallet_id=None,
                market=position.market,
                side=position.side,
                payload={"trigger": reason},
                created_at=now,
                updated_at=now,
            )
            execution = ExecutionAttempt(
                id=_id("exec"),
                trade_intent_id=intent.id,
                user_id=snapshot.user_id,
                trading_mode=TradingMode.DEMO.value,
                profile_season=snapshot.profile_season,
                venue=position.venue,
                action=TradeAction.CLOSE.value,
                status=ExecutionAttemptStatus.VENUE_EXECUTED.value,
                gas_charge_asset=None,
                payload={"simulation": {"source": "demo_risk_monitor", "trigger": reason}},
                created_at=now,
                updated_at=now,
            )
            profile.balance_usd = Decimal(profile.balance_usd or 0) + returned_usd
            profile.updated_at = now
            position.status = (
                PositionStatus.LIQUIDATED.value
                if reason == "liquidation"
                else PositionStatus.CLOSED.value
            )
            position.close_intent_id = intent.id
            position.closed_at = now
            position.updated_at = now
            position.payload = {
                **(position.payload or {}),
                "terminalReason": reason,
                "exitPrice": str(exit_price),
                "grossPricePnlUsd": str(gross_pnl_usd),
                "closeCostUsd": str(close_cost_usd),
                "returnedUsd": str(returned_usd),
                "accountBalanceAfterCloseUsd": str(profile.balance_usd),
                "closeFillQuote": quote_payload,
            }
            reconciliation = Reconciliation(
                id=_id("recon"),
                position_id=position.id,
                status=ReconciliationStatus.WALLET_RECONCILED.value,
                venue_realized_pnl_usd=net_pnl,
                wallet_delta_usd=net_pnl,
                difference_usd=Decimal(0),
                payload={
                    "source": "demo_risk_monitor",
                    "terminalReason": reason,
                    "grossPricePnlUsd": str(gross_pnl_usd),
                    "openCostUsd": str(snapshot.open_cost_usd),
                    "closeCostUsd": str(close_cost_usd),
                    "returnedUsd": str(returned_usd),
                },
                created_at=now,
                updated_at=now,
            )
            ledger = LedgerEvent(
                id=_id("ledger"),
                user_id=snapshot.user_id,
                trading_mode=TradingMode.DEMO.value,
                profile_season=snapshot.profile_season,
                position_id=position.id,
                event_type="demo_position_settled",
                asset="USDC",
                amount=returned_usd,
                source="demo_risk_monitor",
                execution_attempt_id=execution.id,
                payload={"netPnlUsd": str(net_pnl), "terminalReason": reason},
                created_at=now,
            )
            session.add_all([intent, execution, reconciliation, ledger])
            return True

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


def _demo_profile(session, context: ExecutionContext, *, for_update: bool) -> TradingProfile:
    query = session.query(TradingProfile).filter(
        TradingProfile.user_id == context.user_id,
        TradingProfile.mode == TradingMode.DEMO.value,
        TradingProfile.current_season == context.profile_season,
    )
    if for_update:
        query = query.with_for_update()
    profile = query.one_or_none()
    if profile is None:
        raise StoreNotFound("demo profile season is no longer active")
    return profile


def _id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}_{uuid4().hex}"


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
