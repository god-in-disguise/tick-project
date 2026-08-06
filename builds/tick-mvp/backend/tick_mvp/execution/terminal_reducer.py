from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.accounting import net_wallet_delta, reconciliation_difference
from tick_mvp.domain.states import (
    ExecutionAttemptStatus,
    PositionStatus,
    ReconciliationStatus,
    TradeAction,
    VenueEventType,
    can_transition,
)
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.memory_store import StoreConflict
from tick_mvp.infrastructure.models import (
    ExecutionAttempt,
    LedgerEvent,
    Position,
    Reconciliation,
    TradeIntent,
    VenueEvent,
    WalletAccount,
)
from tick_mvp.wallets.accounting import platform_gas_complete
from tick_mvp.venues.base import TerminalPositionEvent


RECONCILIATION_TOLERANCE_USD = Decimal("0.02")


@dataclass(frozen=True, slots=True)
class TrackedPosition:
    id: str
    owner: str
    venue_position_id: str
    venue: str
    market: str
    side: str
    status: PositionStatus
    ticket_usd: Decimal
    liquidation_price: Decimal | None
    account_balance_before_usd: Decimal | None


class TerminalEventReducer:
    def __init__(self, settings: Settings | None = None, session_factory=None) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory or create_session_factory()

    def wallet_addresses(self, venue: str | None = None) -> list[str]:
        with session_scope(self._session_factory) as session:
            query = session.query(WalletAccount.address)
            if venue is not None:
                query = query.filter(WalletAccount.chain_id == self._chain_id(venue))
            return [str(row[0]) for row in query.all()]

    def active_positions(self, venue: str = "gtrade") -> list[TrackedPosition]:
        with session_scope(self._session_factory) as session:
            rows = (
                session.query(Position, WalletAccount)
                .join(WalletAccount, WalletAccount.id == Position.wallet_id)
                .filter(
                    Position.venue == venue,
                    Position.status.in_(
                        [
                            PositionStatus.OPENING.value,
                            PositionStatus.OPEN.value,
                            PositionStatus.CLOSING.value,
                            PositionStatus.UNKNOWN.value,
                        ]
                    ),
                    Position.venue_position_id.is_not(None),
                )
                .all()
            )
            return [
                TrackedPosition(
                    id=position.id,
                    owner=wallet.address,
                    venue_position_id=str(position.venue_position_id),
                    venue=position.venue,
                    market=position.market,
                    side=position.side,
                    status=PositionStatus(position.status),
                    ticket_usd=Decimal(position.ticket_usd),
                    liquidation_price=(
                        Decimal(position.liquidation_price)
                        if position.liquidation_price is not None
                        else None
                    ),
                    account_balance_before_usd=_decimal_or_none(
                        (position.payload or {}).get("accountBalanceBeforeOpenUsd")
                    ),
                )
                for position, wallet in rows
            ]

    def observe_live_position(
        self,
        position_id: str,
        *,
        venue: str,
        metrics: dict[str, str | None],
        liquidation_price: Decimal | None,
    ) -> bool:
        """Persist changed venue metrics without creating synthetic market history."""
        with session_scope(self._session_factory) as session:
            position = (
                session.query(Position)
                .filter(Position.id == position_id, Position.venue == venue)
                .with_for_update()
                .one_or_none()
            )
            if position is None or position.status in {
                PositionStatus.CLOSED.value,
                PositionStatus.LIQUIDATED.value,
            }:
                return False
            payload = position.payload or {}
            if (
                payload.get("venueLiveMetrics") == metrics
                and (
                    liquidation_price is None
                    or position.liquidation_price == liquidation_price
                )
            ):
                return False
            now = datetime.now(UTC)
            position.payload = {
                **payload,
                "venueLiveMetrics": metrics,
                "venueLiveMetricsAt": now.isoformat(),
            }
            if liquidation_price is not None:
                position.liquidation_price = liquidation_price
            position.updated_at = now
            return True

    def apply(
        self,
        event: TerminalPositionEvent,
        *,
        defer_to_active_close: bool = False,
    ) -> str | None:
        with session_scope(self._session_factory) as session:
            chain_id = self._chain_id(event.venue)
            wallet = (
                session.query(WalletAccount)
                .filter(
                    func.lower(WalletAccount.address) == event.owner.lower(),
                    WalletAccount.chain_id == chain_id,
                )
                .first()
            )
            if wallet is None:
                return None
            position = (
                session.query(Position)
                .filter(
                    Position.wallet_id == wallet.id,
                    Position.venue == event.venue,
                    Position.venue_position_id == event.venue_position_id,
                )
                .order_by(Position.created_at.desc())
                .with_for_update()
                .first()
            )
            if position is None:
                candidates = (
                    session.query(Position)
                    .filter(
                        Position.wallet_id == wallet.id,
                        Position.venue == event.venue,
                        Position.status.in_(
                            [
                                PositionStatus.OPENING.value,
                                PositionStatus.OPEN.value,
                                PositionStatus.CLOSING.value,
                                PositionStatus.UNKNOWN.value,
                            ]
                        ),
                    )
                    .with_for_update()
                    .all()
                )
                if len(candidates) != 1:
                    return None
                position = candidates[0]
                position.venue_position_id = event.venue_position_id
            existing_event = self._existing_event(session, event)
            if existing_event is not None:
                if position.closed_at is None or event.observed_at < position.closed_at:
                    position.closed_at = event.observed_at
                    existing_event.observed_at = event.observed_at
            else:
                event_type = _event_type(event.reason)
                session.add(
                    VenueEvent(
                        id=f"event_{uuid.uuid4().hex}",
                        position_id=position.id,
                        execution_attempt_id=None,
                        venue=event.venue,
                        event_type=event_type.value,
                        source=event.source,
                        chain_id=event.chain_id or chain_id,
                        block_number=event.block_number,
                        block_hash=None,
                        transaction_hash=event.transaction_hash,
                        log_index=event.log_index,
                        payload=event.payload,
                        observed_at=event.observed_at,
                    )
                )

            if defer_to_active_close and _active_close_exists(session, position.id):
                return None

            existing_reason = str((position.payload or {}).get("terminalReason") or "")
            use_event_as_terminal_truth = _prefer_terminal_reason(
                current=existing_reason,
                candidate=event.reason,
            )
            if use_event_as_terminal_truth:
                if position.status != PositionStatus.LIQUIDATED.value:
                    _transition_position(position, event.status)
                position.closed_at = event.observed_at
                position.updated_at = datetime.now(UTC)
                position.payload = {
                    **(position.payload or {}),
                    "terminalReason": event.reason,
                    "terminalEventSource": event.source,
                    "terminalTransactionHash": event.transaction_hash,
                    "returnedCollateralUsd": (
                        str(event.returned_collateral_usd)
                        if event.returned_collateral_usd is not None
                        else None
                    ),
                }

            reconciliation = _reconciliation(session, position.id)
            if reconciliation is None:
                now = datetime.now(UTC)
                reconciliation = Reconciliation(
                    id=f"recon_{uuid.uuid4().hex}",
                    position_id=position.id,
                    status=ReconciliationStatus.PENDING.value,
                    payload={},
                    created_at=now,
                    updated_at=now,
                )
                session.add(reconciliation)
            if (
                use_event_as_terminal_truth
                and event.returned_collateral_usd is not None
            ):
                reconciliation.status = ReconciliationStatus.VENUE_ACCOUNTED.value
                reconciliation.venue_realized_pnl_usd = (
                    event.returned_collateral_usd - Decimal(position.ticket_usd)
                )
                reconciliation.payload = {
                    **(reconciliation.payload or {}),
                    "terminalReason": event.reason,
                    "returnedCollateralUsd": str(event.returned_collateral_usd),
                    "terminalEvent": event.payload,
                }
                reconciliation.updated_at = datetime.now(UTC)
            return position.id

    def reconcile_wallet(self, position_id: str, account_balance_after_usd: Decimal) -> Decimal | None:
        with session_scope(self._session_factory) as session:
            position = session.get(Position, position_id)
            if position is None:
                return None
            reconciliation = _reconciliation(session, position.id)
            if reconciliation is None:
                return None
            gas_ledger_total = (
                session.query(func.coalesce(func.sum(LedgerEvent.amount), 0))
                .filter(
                    LedgerEvent.position_id == position.id,
                    LedgerEvent.event_type == "gas_charge",
                    LedgerEvent.asset == "USDC",
                )
                .scalar()
            )
            wallet_delta = net_wallet_delta(
                position.payload,
                account_balance_after_usd,
                Decimal(gas_ledger_total or 0),
            )
            reconciliation.wallet_delta_usd = wallet_delta
            venue_pnl = (
                Decimal(reconciliation.venue_realized_pnl_usd)
                if reconciliation.venue_realized_pnl_usd is not None
                else None
            )
            gas_complete = (
                self._settings.gas_payer_mode != "platform_agent"
                or platform_gas_complete(session, position)
            )
            difference = reconciliation_difference(
                wallet_delta,
                venue_pnl,
                Decimal(gas_ledger_total or 0),
            )
            reconciliation.difference_usd = difference
            if wallet_delta is None:
                reconciliation.status = ReconciliationStatus.VENUE_ACCOUNTED.value
            elif venue_pnl is None:
                reconciliation.status = ReconciliationStatus.WALLET_OBSERVED.value
            elif not gas_complete:
                reconciliation.status = ReconciliationStatus.VENUE_ACCOUNTED.value
            elif abs(difference or Decimal(0)) <= RECONCILIATION_TOLERANCE_USD:
                reconciliation.status = ReconciliationStatus.WALLET_RECONCILED.value
            else:
                reconciliation.status = ReconciliationStatus.MISMATCHED.value
            reconciliation.payload = {
                **(reconciliation.payload or {}),
                "accountBalanceAfterTerminalUsd": str(account_balance_after_usd),
            }
            reconciliation.updated_at = datetime.now(UTC)
            return wallet_delta

    def _existing_event(self, session, event: TerminalPositionEvent) -> VenueEvent | None:
        if event.transaction_hash is None or event.log_index is None:
            return None
        return (
            session.query(VenueEvent)
            .filter(
                VenueEvent.chain_id == (
                    event.chain_id or self._chain_id(event.venue)
                ),
                VenueEvent.transaction_hash == event.transaction_hash,
                VenueEvent.log_index == event.log_index,
            )
            .first()
        )

    def _chain_id(self, venue: str) -> int:
        if venue == "avantis":
            return self._settings.base_chain_id
        return self._settings.arb_chain_id


def _reconciliation(session, position_id: str) -> Reconciliation | None:
    return (
        session.query(Reconciliation)
        .filter(Reconciliation.position_id == position_id)
        .order_by(Reconciliation.created_at.desc())
        .first()
    )


def _active_close_exists(session, position_id: str) -> bool:
    active_statuses = [
        ExecutionAttemptStatus.CREATED.value,
        ExecutionAttemptStatus.CLAIMED.value,
        ExecutionAttemptStatus.SIGNED.value,
        ExecutionAttemptStatus.BROADCAST_PENDING.value,
        ExecutionAttemptStatus.BROADCAST.value,
        ExecutionAttemptStatus.INITIATION_CONFIRMED.value,
        ExecutionAttemptStatus.AWAITING_VENUE_EXECUTION.value,
        ExecutionAttemptStatus.UNKNOWN.value,
    ]
    return (
        session.query(ExecutionAttempt.id)
        .join(TradeIntent, TradeIntent.id == ExecutionAttempt.trade_intent_id)
        .filter(
            TradeIntent.position_id == position_id,
            ExecutionAttempt.action == TradeAction.CLOSE.value,
            ExecutionAttempt.status.in_(active_statuses),
        )
        .first()
        is not None
    )


def _transition_position(position: Position, target: PositionStatus) -> None:
    current = PositionStatus(position.status)
    if current == target:
        return
    if not can_transition(current, target):
        raise StoreConflict(f"invalid position transition: {current.value} -> {target.value}")
    position.status = target.value


def _event_type(reason: str) -> VenueEventType:
    if reason == "liquidation":
        return VenueEventType.LIQUIDATION_OBSERVED
    if reason == "stop_loss":
        return VenueEventType.STOP_LOSS_OBSERVED
    return VenueEventType.UNREGISTER_TRADE_OBSERVED


def _prefer_terminal_reason(*, current: str, candidate: str) -> bool:
    priority = {
        "": 0,
        "external_close": 1,
        "manual_close": 2,
        "take_profit": 3,
        "stop_loss": 3,
        "liquidation": 4,
    }
    return priority.get(candidate, 0) >= priority.get(current, 0)


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
