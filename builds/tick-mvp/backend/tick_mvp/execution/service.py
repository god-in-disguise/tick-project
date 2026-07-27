from __future__ import annotations

import logging
import time
from decimal import Decimal

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import TradeAction
from tick_mvp.execution.repository import ExecutionContext, ExecutionRepository
from tick_mvp.venues.registry import create_venue


LOGGER = logging.getLogger("tick.execution")
BALANCE_SETTLEMENT_TIMEOUT_SECONDS = 4.0
BALANCE_SETTLEMENT_POLL_SECONDS = 0.25
BALANCE_SETTLEMENT_EPSILON_USD = Decimal("0.01")


class ExecutionService:
    def __init__(self, settings: Settings | None = None, repository: ExecutionRepository | None = None) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or ExecutionRepository(self._settings)
        self._venue = create_venue(self._settings)

    def start(self) -> None:
        start = getattr(self._venue, "start", None)
        if start is not None:
            start()

    def stop(self) -> None:
        stop = getattr(self._venue, "stop", None)
        if stop is not None:
            stop()

    def prepare_user_wallet(self, user_id: str, required_collateral_usd: Decimal) -> dict[str, object]:
        _, private_key_hex = self._repository.load_user_wallet_credentials(user_id)
        prepare = getattr(self._venue, "prepare_wallet", None)
        if prepare is None:
            return {"userId": user_id, "status": "unsupported"}
        result = prepare(
            private_key_hex=private_key_hex,
            required_collateral_usd=required_collateral_usd,
        )
        return {"userId": user_id, "status": "ready", **result}

    def execute(self, execution_attempt_id: str) -> dict[str, object]:
        started = time.perf_counter()
        context = self._repository.load(execution_attempt_id)
        loaded_at = time.perf_counter()
        if not self._settings.tick_real_execution_enabled:
            LOGGER.info("real execution disabled", extra={"executionAttemptId": execution_attempt_id})
            return {
                "executionAttemptId": execution_attempt_id,
                "status": "dry_run",
                "reason": "TICK_REAL_EXECUTION_ENABLED=false",
            }
        try:
            result = self._execute_live(context)
            finished_at = time.perf_counter()
            LOGGER.info(
                "execution timing executionAttemptId=%s contextLoadMs=%.1f venueAndPersistenceMs=%.1f totalMs=%.1f",
                execution_attempt_id,
                (loaded_at - started) * 1000,
                (finished_at - loaded_at) * 1000,
                (finished_at - started) * 1000,
            )
            return result
        except Exception as exc:
            self._repository.mark_failed(context, f"{type(exc).__name__}: {exc}")
            raise

    def _execute_live(self, context: ExecutionContext) -> dict[str, object]:
        if context.action == TradeAction.OPEN:
            result = self._venue.open_position(
                private_key_hex=context.private_key_hex,
                market=context.market,
                side=context.side,
                ticket_usd=context.ticket_usd,
                leverage=context.leverage,
                quote_payload=context.quote_payload,
                stop_loss_price=context.stop_loss_price,
                on_transaction_prepared=lambda tx_hash, nonce: self._repository.mark_broadcast_pending(
                    context,
                    tx_hash=tx_hash,
                    nonce=nonce,
                ),
            )
            self._repository.mark_open_result(context, result)
            return {
                "executionAttemptId": context.execution_id,
                "status": result.status,
                "txHash": result.tx.tx_hash,
                "venuePositionId": result.venue_position_id,
            }

        result = self._venue.close_position(
            private_key_hex=context.private_key_hex,
            market=context.market,
            side=context.side,
            venue_position_id=context.venue_position_id,
            on_transaction_prepared=lambda tx_hash, nonce: self._repository.mark_broadcast_pending(
                context,
                tx_hash=tx_hash,
                nonce=nonce,
            ),
        )
        wallet_delta_usd = self._repository.mark_close_result(context, result)
        if result.status == "closed" and wallet_delta_usd is None:
            try:
                account_balance_after = self._wait_for_close_balance(context)
                wallet_delta_usd = self._repository.mark_close_reconciliation(
                    context,
                    account_balance_after_usd=account_balance_after,
                )
            except Exception:
                LOGGER.exception(
                    "close accounting reconciliation deferred",
                    extra={"executionAttemptId": context.execution_id},
                )
        return {
            "executionAttemptId": context.execution_id,
            "status": result.status,
            "txHash": result.tx.tx_hash,
            "walletDeltaUsd": str(wallet_delta_usd) if wallet_delta_usd is not None else None,
        }

    def _wait_for_close_balance(
        self,
        context: ExecutionContext,
        *,
        timeout_seconds: float = BALANCE_SETTLEMENT_TIMEOUT_SECONDS,
        poll_seconds: float = BALANCE_SETTLEMENT_POLL_SECONDS,
    ) -> Decimal:
        deadline = time.monotonic() + timeout_seconds
        open_state_balance = (
            context.account_balance_before_open_usd - context.ticket_usd
            if context.account_balance_before_open_usd is not None
            else None
        )
        while True:
            balance = self._venue.collateral_balance_usd(private_key_hex=context.private_key_hex)
            if open_state_balance is None or balance > open_state_balance + BALANCE_SETTLEMENT_EPSILON_USD:
                return balance
            if time.monotonic() >= deadline:
                return balance
            time.sleep(poll_seconds)
