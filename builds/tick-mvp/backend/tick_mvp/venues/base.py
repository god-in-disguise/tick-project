from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from tick_mvp.domain.states import TradeSide


TransactionPreparedHandler = Callable[[str, int], None]


class VenueError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class VenueQuote:
    venue: str
    market: str
    side: TradeSide
    ticket_usd: Decimal
    leverage: Decimal
    notional_usd: Decimal
    estimated_open_cost_usd: Decimal
    estimated_close_cost_usd: Decimal
    estimated_round_trip_cost_usd: Decimal
    liquidation_price: Decimal | None
    stop_loss_price: Decimal | None
    opening_allowed: bool
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VenueTxResult:
    status: str
    tx_hash: str | None
    nonce: int | None
    block_number: int | None
    gas_used: int | None
    effective_gas_price: int | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VenueOpenResult:
    status: str
    tx: VenueTxResult
    venue_position_id: str | None
    entry_price: Decimal | None
    liquidation_price: Decimal | None
    stop_loss_price: Decimal | None
    opened_at: datetime | None
    account_balance_before_usd: Decimal | None
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VenueCloseResult:
    status: str
    tx: VenueTxResult
    closed_at: datetime | None
    venue_realized_pnl_usd: Decimal | None
    account_balance_after_usd: Decimal | None
    close_cashflow_usd: Decimal | None
    payload: dict[str, Any]
