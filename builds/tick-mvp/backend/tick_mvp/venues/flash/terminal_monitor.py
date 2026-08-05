from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import PositionStatus
from tick_mvp.execution.terminal_reducer import TerminalEventReducer, TrackedPosition
from tick_mvp.venues.base import TerminalPositionEvent
from tick_mvp.venues.flash.client import FlashClient
from tick_mvp.venues.flash.constants import SOLANA_MAINNET_CHAIN_ID, USDC_MINT, USD_DECIMALS


LOGGER = logging.getLogger("tick.flash-terminal")
POLL_SECONDS = 0.20
ABSENCE_CONFIRMATIONS = 2


class FlashTerminalMonitor:
    """Continuously reduce Flash raw-basket state into TICK position truth."""

    def __init__(
        self,
        settings: Settings,
        reducer: TerminalEventReducer | None = None,
        *,
        client_factory: Callable[[], FlashClient] | None = None,
    ) -> None:
        self._settings = settings
        self._reducer = reducer or TerminalEventReducer(settings)
        self._client_factory = client_factory or (
            lambda: FlashClient(settings.flash_api_url)
        )
        self._clients: dict[str, FlashClient] = {}
        self._absence_counts: dict[str, int] = {}
        self._last_metrics: dict[str, dict[str, Any]] = {}

    async def run(self) -> None:
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Flash terminal monitor cycle failed")
            await asyncio.sleep(POLL_SECONDS)

    async def check_once(self) -> int:
        positions = await asyncio.to_thread(self._reducer.active_positions, "flash")
        active_owners = {position.owner for position in positions}
        for owner in set(self._clients) - active_owners:
            self._clients.pop(owner).close()
        active_ids = {position.id for position in positions}
        for position_id in set(self._absence_counts) - active_ids:
            self._absence_counts.pop(position_id, None)
            self._last_metrics.pop(position_id, None)
        if not positions:
            return 0
        results = await asyncio.gather(
            *(self._observe(position) for position in positions),
            return_exceptions=True,
        )
        applied = 0
        for position, result in zip(positions, results, strict=True):
            if isinstance(result, BaseException):
                LOGGER.warning(
                    "Flash position observation failed positionId=%s error=%s",
                    position.id,
                    result,
                )
            elif result:
                applied += 1
        return applied

    def close(self) -> None:
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    async def _observe(self, tracked: TrackedPosition) -> bool:
        client = self._clients.setdefault(tracked.owner, self._client_factory())
        basket, market_key = _position_key(tracked.venue_position_id)
        owner_state = await asyncio.to_thread(client.owner, tracked.owner)
        metrics = _position_metrics(owner_state, market_key)
        if metrics is not None:
            self._absence_counts.pop(tracked.id, None)
            self._last_metrics[tracked.id] = metrics
            selected = _selected_metrics(metrics)
            await asyncio.to_thread(
                self._reducer.observe_live_position,
                tracked.id,
                venue="flash",
                metrics=selected,
                liquidation_price=_decimal(metrics.get("liquidationPriceUi")),
            )
            return False

        raw_basket = await asyncio.to_thread(client.raw_basket, basket)
        if _raw_position_present(raw_basket, market_key):
            self._absence_counts.pop(tracked.id, None)
            return False

        absence_count = self._absence_counts.get(tracked.id, 0) + 1
        self._absence_counts[tracked.id] = absence_count
        if absence_count < ABSENCE_CONFIRMATIONS:
            return False

        account_balance_after = _available_collateral_usd(raw_basket)
        last_metrics = self._last_metrics.get(tracked.id)
        reason = _terminal_reason(
            tracked,
            last_metrics=last_metrics,
            account_balance_after=account_balance_after,
        )
        event = TerminalPositionEvent(
            venue="flash",
            owner=tracked.owner,
            venue_position_id=tracked.venue_position_id,
            status=(
                PositionStatus.LIQUIDATED
                if reason == "liquidation"
                else PositionStatus.CLOSED
            ),
            reason=reason,
            source="flash_raw_basket_monitor",
            observed_at=datetime.now(UTC),
            transaction_hash=f"flash-snapshot:{tracked.id}",
            block_number=None,
            log_index=0,
            returned_collateral_usd=None,
            payload={
                "basketPubkey": basket,
                "rawSource": raw_basket.get("source"),
                "accountBalanceAfterUsd": str(account_balance_after),
                "absenceConfirmations": absence_count,
                "lastPositionMetrics": _selected_metrics(last_metrics or {}),
                "terminalReasonInference": (
                    "liquidation_price_or_wallet_loss"
                    if reason == "liquidation"
                    else "position_absent_without_liquidation_evidence"
                ),
            },
            chain_id=SOLANA_MAINNET_CHAIN_ID,
        )
        position_id = await asyncio.to_thread(
            self._reducer.apply,
            event,
            defer_to_active_close=True,
        )
        if position_id is None:
            return False
        await asyncio.to_thread(
            self._reducer.reconcile_wallet,
            position_id,
            account_balance_after,
        )
        LOGGER.info(
            "Flash terminal state applied positionId=%s reason=%s balanceAfter=%s",
            position_id,
            reason,
            account_balance_after,
        )
        return True


def _position_key(venue_position_id: str) -> tuple[str, str]:
    values = venue_position_id.rsplit(":", 1)
    if len(values) != 2 or not all(values):
        raise ValueError("invalid Flash venue position id")
    return values[0], values[1]


def _position_metrics(owner_state: dict[str, Any], market_key: str) -> dict[str, Any] | None:
    metrics = owner_state.get("positionMetrics") or {}
    exact = metrics.get(market_key)
    if isinstance(exact, dict):
        return exact
    if len(metrics) == 1:
        only = next(iter(metrics.values()))
        return only if isinstance(only, dict) else None
    return None


def _selected_metrics(metrics: dict[str, Any]) -> dict[str, str | None]:
    fields = (
        "marketSymbol",
        "sideUi",
        "entryPriceUi",
        "liquidationPriceUi",
        "pnlWithFeeUsdUi",
        "pnlWithoutFeeUsdUi",
        "pnlPercentageWithFee",
        "exitFeeUsd",
        "borrowFeeUsd",
        "priceImpactUsd",
        "totalFeeUsd",
    )
    return {
        field: str(metrics[field]) if metrics.get(field) is not None else None
        for field in fields
    }


def _raw_position_present(raw_basket: dict[str, Any], market_key: str) -> bool:
    positions = list((raw_basket.get("account") or {}).get("positions") or [])
    return any(str(position.get("market")) == market_key for position in positions)


def _available_collateral_usd(raw_basket: dict[str, Any]) -> Decimal:
    account = raw_basket.get("account") or {}
    debits = _mint_amount(account.get("debits") or [])
    pending = _mint_amount(account.get("pendingCredits") or [])
    return max(Decimal(0), Decimal(debits - pending).scaleb(-USD_DECIMALS))


def _mint_amount(rows: list[dict[str, Any]]) -> int:
    return sum(
        int(row.get("amount") or 0)
        for row in rows
        if row.get("mint") == USDC_MINT
    )


def _terminal_reason(
    tracked: TrackedPosition,
    *,
    last_metrics: dict[str, Any] | None,
    account_balance_after: Decimal,
) -> str:
    if last_metrics and _liquidation_price_crossed(tracked.side, last_metrics):
        return "liquidation"
    if tracked.account_balance_before_usd is not None:
        wallet_delta = account_balance_after - tracked.account_balance_before_usd
        if wallet_delta <= -(tracked.ticket_usd * Decimal("0.95")):
            return "liquidation"
    return "external_close"


def _liquidation_price_crossed(side: str, metrics: dict[str, Any]) -> bool:
    exit_price = _oracle_price(metrics.get("exitPrice"))
    liquidation_price = _decimal(metrics.get("liquidationPriceUi")) or _oracle_price(
        metrics.get("liquidationPrice")
    )
    if exit_price is None or liquidation_price is None:
        return False
    return (
        exit_price <= liquidation_price
        if side == "long"
        else exit_price >= liquidation_price
    )


def _oracle_price(value: Any) -> Decimal | None:
    if not isinstance(value, dict) or value.get("price") is None:
        return None
    try:
        return Decimal(str(value["price"])) * (
            Decimal(10) ** int(value.get("exponent") or 0)
        )
    except (InvalidOperation, TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
