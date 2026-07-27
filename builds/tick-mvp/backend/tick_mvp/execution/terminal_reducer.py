from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.accounting import whole_trade_wallet_delta
from tick_mvp.domain.states import PositionStatus, ReconciliationStatus, VenueEventType
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.infrastructure.models import Position, Reconciliation, VenueEvent, WalletAccount
from tick_mvp.venues.gtrade.terminal_monitor import TerminalPositionEvent


@dataclass(frozen=True, slots=True)
class TrackedPosition:
    id: str
    owner: str
    venue_position_id: str


class TerminalEventReducer:
    def __init__(self, settings: Settings | None = None, session_factory=None) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory or create_session_factory()

    def wallet_addresses(self) -> list[str]:
        with session_scope(self._session_factory) as session:
            return [str(row[0]) for row in session.query(WalletAccount.address).all()]

    def active_positions(self) -> list[TrackedPosition]:
        with session_scope(self._session_factory) as session:
            rows = (
                session.query(Position, WalletAccount)
                .join(WalletAccount, WalletAccount.id == Position.wallet_id)
                .filter(
                    Position.venue == "gtrade",
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
                )
                for position, wallet in rows
            ]

    def apply(self, event: TerminalPositionEvent) -> str | None:
        with session_scope(self._session_factory) as session:
            wallet = (
                session.query(WalletAccount)
                .filter(func.lower(WalletAccount.address) == event.owner.lower())
                .first()
            )
            if wallet is None:
                return None
            position = (
                session.query(Position)
                .filter(
                    Position.wallet_id == wallet.id,
                    Position.venue == "gtrade",
                    Position.venue_position_id == event.venue_position_id,
                )
                .order_by(Position.created_at.desc())
                .first()
            )
            if position is None:
                return None
            existing_event = self._existing_event(session, event)
            if existing_event is not None:
                if position.closed_at is None or event.observed_at < position.closed_at:
                    position.closed_at = event.observed_at
                    existing_event.observed_at = event.observed_at
                return position.id

            event_type = _event_type(event.reason)
            session.add(
                VenueEvent(
                    id=f"event_{uuid.uuid4().hex}",
                    position_id=position.id,
                    execution_attempt_id=None,
                    venue="gtrade",
                    event_type=event_type.value,
                    source=event.source,
                    chain_id=self._settings.arb_chain_id,
                    block_number=event.block_number,
                    block_hash=None,
                    transaction_hash=event.transaction_hash,
                    log_index=event.log_index,
                    payload=event.payload,
                    observed_at=event.observed_at,
                )
            )

            existing_reason = str((position.payload or {}).get("terminalReason") or "")
            use_event_as_terminal_truth = _prefer_terminal_reason(
                current=existing_reason,
                candidate=event.reason,
            )
            if use_event_as_terminal_truth:
                if position.status != PositionStatus.LIQUIDATED.value:
                    position.status = event.status.value
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
            if (
                use_event_as_terminal_truth
                and reconciliation is not None
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
            wallet_delta = whole_trade_wallet_delta(position.payload, account_balance_after_usd)
            reconciliation.wallet_delta_usd = wallet_delta
            reconciliation.status = (
                ReconciliationStatus.WALLET_RECONCILED.value
                if wallet_delta is not None
                else ReconciliationStatus.VENUE_ACCOUNTED.value
            )
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
                VenueEvent.chain_id == self._settings.arb_chain_id,
                VenueEvent.transaction_hash == event.transaction_hash,
                VenueEvent.log_index == event.log_index,
            )
            .first()
        )


def _reconciliation(session, position_id: str) -> Reconciliation | None:
    return (
        session.query(Reconciliation)
        .filter(Reconciliation.position_id == position_id)
        .order_by(Reconciliation.created_at.desc())
        .first()
    )


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
