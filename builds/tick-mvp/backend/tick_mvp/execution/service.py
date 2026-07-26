from __future__ import annotations

import logging

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import TradeAction
from tick_mvp.execution.repository import ExecutionContext, ExecutionRepository
from tick_mvp.venues.registry import create_venue


LOGGER = logging.getLogger("tick.execution")


class ExecutionService:
    def __init__(self, settings: Settings | None = None, repository: ExecutionRepository | None = None) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or ExecutionRepository(self._settings)
        self._venue = create_venue(self._settings)

    def execute(self, execution_attempt_id: str) -> dict[str, object]:
        context = self._repository.load(execution_attempt_id)
        if not self._settings.tick_real_execution_enabled:
            LOGGER.info("real execution disabled", extra={"executionAttemptId": execution_attempt_id})
            return {
                "executionAttemptId": execution_attempt_id,
                "status": "dry_run",
                "reason": "TICK_REAL_EXECUTION_ENABLED=false",
            }
        try:
            return self._execute_live(context)
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
        )
        self._repository.mark_close_result(context, result)
        return {
            "executionAttemptId": context.execution_id,
            "status": result.status,
            "txHash": result.tx.tx_hash,
            "walletDeltaUsd": str(result.wallet_delta_usd) if result.wallet_delta_usd is not None else None,
        }

