from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import TradeAction
from tick_mvp.execution.repository import ExecutionContext, ExecutionRepository
from tick_mvp.venues.registry import create_venue
from tick_mvp.wallets.accounting import (
    GasAccountingService,
    gas_transaction,
    gas_transactions_from_payload,
    spendable_usdc,
)
from tick_mvp.wallets.gas import GasFundingService


LOGGER = logging.getLogger("tick.execution")
BALANCE_SETTLEMENT_TIMEOUT_SECONDS = 4.0
BALANCE_SETTLEMENT_POLL_SECONDS = 0.25
BALANCE_SETTLEMENT_EPSILON_USD = Decimal("0.01")


class ExecutionService:
    BALANCE_CACHE_SECONDS = 30.0

    def __init__(
        self,
        settings: Settings | None = None,
        repository: ExecutionRepository | None = None,
        gas_funding: GasFundingService | None = None,
        gas_accounting: GasAccountingService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or ExecutionRepository(self._settings)
        self._venue = create_venue(self._settings)
        self._gas_funding = gas_funding or GasFundingService(self._settings)
        self._gas_accounting = gas_accounting or GasAccountingService(self._settings)
        self._balance_cache: dict[str, tuple[float, Decimal]] = {}
        self._balance_lock = threading.Lock()

    def start(self) -> None:
        start = getattr(self._venue, "start", None)
        if start is not None:
            start()

    def stop(self) -> None:
        stop = getattr(self._venue, "stop", None)
        if stop is not None:
            stop()
        self._gas_funding.close()

    def prepare_user_wallet(self, user_id: str, required_collateral_usd: Decimal) -> dict[str, object]:
        gas = None
        if self._settings.tick_real_execution_enabled:
            wallet_id, wallet_address, private_key_hex = (
                self._repository.load_user_wallet_context(user_id)
            )
        else:
            wallet_address, private_key_hex = (
                self._repository.load_user_wallet_credentials(user_id)
            )
            wallet_id = ""
        prepare = getattr(self._venue, "prepare_wallet", None)
        if prepare is None:
            return {"userId": user_id, "status": "unsupported"}

        def ensure_transaction_gas() -> dict[str, object]:
            nonlocal gas
            if gas is None:
                gas = self._gas_funding.ensure_funded(
                    user_id=user_id,
                    wallet_id=wallet_id,
                    wallet_address=wallet_address,
                )
            return gas

        result = prepare(
            private_key_hex=private_key_hex,
            required_collateral_usd=required_collateral_usd,
            ensure_transaction_gas=(
                ensure_transaction_gas
                if self._settings.tick_real_execution_enabled
                else None
            ),
        )
        raw_balance = _decimal_or_none(result.get("collateralBalanceUsd"))
        if raw_balance is not None:
            self._remember_balance(user_id, raw_balance)
            self._require_spendable(
                user_id=user_id,
                required_usdc=required_collateral_usd,
                raw_balance=raw_balance,
            )
        self._charge_payload_transactions(
            user_id=user_id,
            execution_attempt_id=None,
            payload=result.get("gasTransactions"),
            wallet_address=wallet_address,
        )
        return {"userId": user_id, "status": "ready", "gas": gas, **result}

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
            if self._settings.gas_payer_mode.strip().lower() == "user_wallet":
                self._ensure_execution_gas(context)
            if context.action == TradeAction.OPEN:
                self._require_open_balance(context)
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
                take_profit_price=context.take_profit_price,
                on_transaction_prepared=lambda tx_hash, nonce: self._repository.mark_broadcast_pending(
                    context,
                    tx_hash=tx_hash,
                    nonce=nonce,
                ),
            )
            self._repository.mark_open_result(context, result)
            self._charge_result(
                context,
                result.tx,
                extra_transactions=result.payload.get("gasTransactions"),
            )
            self._adjust_cached_balance(context.user_id, -context.ticket_usd)
            self._refresh_open_liquidation_price(context, result)
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
        self._charge_result(context, result.tx)
        wallet_delta_usd = self._repository.mark_close_result(context, result)
        if result.status == "closed" and wallet_delta_usd is None:
            try:
                account_balance_after = self._wait_for_close_balance(context)
                wallet_delta_usd = self._repository.mark_close_reconciliation(
                    context,
                    account_balance_after_usd=account_balance_after,
                )
                self._remember_balance(context.user_id, account_balance_after)
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

    def _refresh_open_liquidation_price(self, context: ExecutionContext, result) -> None:
        if result.status != "open":
            return
        refresh = getattr(self._venue, "current_liquidation_price", None)
        if refresh is None:
            return
        try:
            liquidation_price = refresh(
                market=context.market,
                position=result.payload.get("position"),
            )
            if liquidation_price is not None:
                self._repository.update_liquidation_price(
                    context.position_id,
                    liquidation_price,
                    source="venue_onchain",
                )
        except Exception:
            LOGGER.exception(
                "liquidation price refresh deferred",
                extra={"executionAttemptId": context.execution_id},
            )

    def _ensure_execution_gas(self, context: ExecutionContext) -> None:
        self._gas_funding.ensure_funded(
            user_id=context.user_id,
            wallet_id=context.wallet_id,
            wallet_address=context.wallet_address,
        )

    def _require_open_balance(self, context: ExecutionContext) -> None:
        raw_balance = self._cached_balance(context.user_id)
        if raw_balance is None:
            LOGGER.info(
                "open balance preflight skipped userId=%s executionAttemptId=%s reason=no_prepared_snapshot",
                context.user_id,
                context.execution_id,
            )
            return
        self._require_spendable(
            user_id=context.user_id,
            required_usdc=context.ticket_usd,
            raw_balance=raw_balance,
        )

    def _require_spendable(
        self,
        *,
        user_id: str,
        required_usdc: Decimal,
        raw_balance: Decimal,
    ) -> None:
        charges = self._gas_accounting.total_charges_usdc(user_id)
        available = spendable_usdc(raw_balance, charges)
        if available < required_usdc:
            raise InsufficientSpendableUSDC(
                f"insufficient spendable USDC: {available:.6f} available"
            )

    def _charge_result(
        self,
        context: ExecutionContext,
        tx,
        *,
        extra_transactions: object = None,
    ) -> None:
        transactions = gas_transactions_from_payload(extra_transactions)
        primary = gas_transaction(
            tx_hash=tx.tx_hash,
            gas_used=tx.gas_used,
            effective_gas_price=tx.effective_gas_price,
            operation=context.action.value,
            gas_payer_address=tx.payload.get("gasPayer"),
        )
        if primary is not None:
            transactions.append(primary)
        self._charge_transactions(
            user_id=context.user_id,
            execution_attempt_id=context.execution_id,
            transactions=transactions,
            wallet_address=context.wallet_address,
        )

    def _charge_payload_transactions(
        self,
        *,
        user_id: str,
        execution_attempt_id: str | None,
        payload: object,
        wallet_address: str,
    ) -> None:
        self._charge_transactions(
            user_id=user_id,
            execution_attempt_id=execution_attempt_id,
            transactions=gas_transactions_from_payload(payload),
            wallet_address=wallet_address,
        )

    def _charge_transactions(
        self,
        *,
        user_id: str,
        execution_attempt_id: str | None,
        transactions: list,
        wallet_address: str,
    ) -> None:
        for transaction in transactions:
            self._gas_funding.note_spent(
                transaction.gas_payer_address or wallet_address,
                transaction.native_cost,
            )
            try:
                self._gas_accounting.charge(
                    user_id=user_id,
                    transaction=transaction,
                    execution_attempt_id=execution_attempt_id,
                )
            except Exception:
                LOGGER.exception(
                    "gas accounting deferred userId=%s txHash=%s",
                    user_id,
                    transaction.tx_hash,
                )

    def _cached_balance(self, user_id: str) -> Decimal | None:
        with self._balance_lock:
            cached = self._balance_cache.get(user_id)
        if cached is None or time.monotonic() - cached[0] > self.BALANCE_CACHE_SECONDS:
            return None
        return cached[1]

    def _remember_balance(self, user_id: str, balance: Decimal) -> None:
        with self._balance_lock:
            self._balance_cache[user_id] = (time.monotonic(), balance)

    def _adjust_cached_balance(self, user_id: str, delta: Decimal) -> None:
        with self._balance_lock:
            cached = self._balance_cache.get(user_id)
            if cached is None:
                return
            self._balance_cache[user_id] = (
                time.monotonic(),
                max(Decimal(0), cached[1] + delta),
            )

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


class InsufficientSpendableUSDC(RuntimeError):
    pass


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))
