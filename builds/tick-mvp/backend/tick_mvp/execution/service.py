from __future__ import annotations

import logging
import hashlib
import threading
import time
from decimal import Decimal

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import TradeAction, TradeSide, TradingMode
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
        self._wallet_ready_cache: dict[str, tuple[float, Decimal]] = {}
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

    def recoverable_execution_ids(self) -> list[str]:
        return self._repository.recoverable_execution_ids()

    def recover_ambiguous_executions(self) -> dict[str, int]:
        recover = getattr(self._venue, "recover_execution", None)
        if recover is None:
            return {"checked": 0, "resolved": 0}
        checked = 0
        resolved = 0
        for execution_id in self._repository.ambiguous_execution_ids():
            checked += 1
            try:
                context = self._repository.load(execution_id)
                if (
                    context.private_key_hex is None
                    or context.tx_hash is None
                ):
                    continue
                recovery = recover(
                    private_key_hex=context.private_key_hex,
                    market=context.market,
                    venue_position_id=context.venue_position_id,
                    tx_hash=context.tx_hash,
                    signed_raw_transaction=context.signed_raw_transaction,
                )
                outcome = self._repository.apply_execution_recovery(context, recovery)
                tx = recovery.get("tx")
                if tx is not None:
                    self._charge_result(context, tx)
                if outcome == "open":
                    self._adjust_cached_balance(context.user_id, -context.ticket_usd)
                elif outcome == "closed":
                    try:
                        account_balance_after = self._venue.collateral_balance_usd(
                            private_key_hex=context.private_key_hex
                        )
                        self._repository.mark_close_reconciliation(
                            context,
                            account_balance_after_usd=account_balance_after,
                        )
                        self._remember_balance(context.user_id, account_balance_after)
                    except Exception:
                        LOGGER.exception(
                            "recovered close accounting deferred",
                            extra={"executionAttemptId": execution_id},
                        )
                if outcome in {"open", "closed", "terminal", "reverted", "already_resolved"}:
                    resolved += 1
                LOGGER.info(
                    "execution recovery checked executionAttemptId=%s outcome=%s txHash=%s",
                    execution_id,
                    outcome,
                    context.tx_hash,
                )
            except Exception:
                LOGGER.exception(
                    "execution recovery failed",
                    extra={"executionAttemptId": execution_id},
                )
        return {"checked": checked, "resolved": resolved}

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
        if not result.get("allowanceReady", True):
            raise WalletNotReady("wallet collateral allowance is not ready")
        if not result.get("delegationReady", True):
            raise WalletNotReady("wallet trading delegation is not ready")
        self._remember_wallet_ready(user_id, required_collateral_usd)
        return {"userId": user_id, "status": "ready", "gas": gas, **result}

    def execute(self, execution_attempt_id: str) -> dict[str, object]:
        started = time.perf_counter()
        context = self._repository.claim(execution_attempt_id)
        if context is None:
            LOGGER.info(
                "execution already claimed",
                extra={"executionAttemptId": execution_attempt_id},
            )
            return {
                "executionAttemptId": execution_attempt_id,
                "status": "already_claimed",
            }
        loaded_at = time.perf_counter()
        if context.trading_mode == TradingMode.DEMO:
            try:
                return self._execute_demo(context)
            except Exception as exc:
                self._repository.mark_failed(context, f"{type(exc).__name__}: {exc}")
                raise
        if not self._settings.tick_real_execution_enabled:
            LOGGER.info("real execution disabled", extra={"executionAttemptId": execution_attempt_id})
            return {
                "executionAttemptId": execution_attempt_id,
                "status": "dry_run",
                "reason": "TICK_REAL_EXECUTION_ENABLED=false",
            }
        try:
            if context.action == TradeAction.OPEN:
                self._ensure_open_wallet_ready(context)
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

    def check_demo_positions(self) -> int:
        settled = 0
        for position in self._repository.open_demo_positions():
            try:
                fill_quote = self._venue.quote_open(
                    market=position.market,
                    side=position.side,
                    ticket_usd=position.ticket_usd,
                    leverage=position.leverage,
                    max_loss_usd=position.max_loss_usd,
                    take_profit_usd=position.take_profit_usd,
                )
                price = Decimal(str(fill_quote.payload["price"]))
                reason = _demo_terminal_reason(position, price)
                if reason is None:
                    continue
                direction = Decimal(1) if position.side == TradeSide.LONG else Decimal(-1)
                gross_pnl = (
                    (price - position.entry_price)
                    / position.entry_price
                    * position.notional_usd
                    * direction
                )
                returned = max(
                    Decimal(0),
                    position.ticket_usd
                    + gross_pnl
                    - position.open_cost_usd
                    - fill_quote.estimated_close_cost_usd,
                )
                if reason == "liquidation":
                    returned = Decimal(0)
                if self._repository.settle_demo_terminal(
                    position,
                    exit_price=price,
                    gross_pnl_usd=gross_pnl,
                    close_cost_usd=fill_quote.estimated_close_cost_usd,
                    returned_usd=returned,
                    reason=reason,
                    quote_payload=fill_quote.payload,
                ):
                    settled += 1
            except Exception:
                LOGGER.exception(
                    "demo risk monitor failed",
                    extra={"positionId": position.position_id},
                )
        return settled

    def _execute_live(self, context: ExecutionContext) -> dict[str, object]:
        if context.private_key_hex is None:
            raise WalletNotReady("live execution wallet key is unavailable")
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
                on_transaction_prepared=lambda tx_hash, nonce, raw_tx: self._repository.mark_broadcast_pending(
                    context,
                    tx_hash=tx_hash,
                    nonce=nonce,
                    signed_raw_transaction=raw_tx,
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
            on_transaction_prepared=lambda tx_hash, nonce, raw_tx: self._repository.mark_broadcast_pending(
                context,
                tx_hash=tx_hash,
                nonce=nonce,
                signed_raw_transaction=raw_tx,
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

    def _execute_demo(self, context: ExecutionContext) -> dict[str, object]:
        delay_ms = _demo_delay_ms(context.execution_id, context.action)
        time.sleep(delay_ms / 1000)
        fill_quote = self._venue.quote_open(
            market=context.market,
            side=context.side,
            ticket_usd=context.ticket_usd,
            leverage=context.leverage,
            max_loss_usd=context.max_loss_usd,
            take_profit_usd=context.take_profit_usd,
        )
        fill_price = Decimal(str(fill_quote.payload["price"]))
        if context.action == TradeAction.OPEN:
            self._repository.mark_demo_open(
                context,
                entry_price=fill_price,
                liquidation_price=fill_quote.liquidation_price,
                stop_loss_price=fill_quote.stop_loss_price,
                take_profit_price=fill_quote.take_profit_price,
                open_cost_usd=fill_quote.estimated_open_cost_usd,
                close_cost_usd=fill_quote.estimated_close_cost_usd,
                quote_payload=fill_quote.payload,
                delay_ms=delay_ms,
            )
            return {
                "executionAttemptId": context.execution_id,
                "status": "open",
                "venuePositionId": f"demo:{context.position_id}",
                "fillPrice": str(fill_price),
                "delayMs": delay_ms,
            }

        if context.position_id is None:
            raise ValueError("demo close is missing a position")
        entry_price = context.entry_price or Decimal(0)
        if entry_price <= 0:
            raise ValueError("demo close is missing the entry price")
        direction = Decimal(1) if context.side == TradeSide.LONG else Decimal(-1)
        gross_pnl = (
            (fill_price - entry_price)
            / entry_price
            * context.notional_usd
            * direction
        )
        open_cost = context.open_cost_usd
        close_cost = fill_quote.estimated_close_cost_usd
        reason = "manual_close"
        crossed_liquidation = (
            context.liquidation_price is not None
            and (
                (context.side == TradeSide.LONG and fill_price <= context.liquidation_price)
                or (context.side == TradeSide.SHORT and fill_price >= context.liquidation_price)
            )
        )
        returned = max(
            Decimal(0),
            context.ticket_usd + gross_pnl - open_cost - close_cost,
        )
        if crossed_liquidation:
            reason = "liquidation"
            returned = Decimal(0)
        net_pnl = self._repository.mark_demo_close(
            context,
            exit_price=fill_price,
            gross_pnl_usd=gross_pnl,
            open_cost_usd=open_cost,
            close_cost_usd=close_cost,
            returned_usd=returned,
            reason=reason,
            quote_payload=fill_quote.payload,
            delay_ms=delay_ms,
        )
        return {
            "executionAttemptId": context.execution_id,
            "status": "liquidated" if reason == "liquidation" else "closed",
            "fillPrice": str(fill_price),
            "walletDeltaUsd": str(net_pnl),
            "delayMs": delay_ms,
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

    def _ensure_open_wallet_ready(self, context: ExecutionContext) -> None:
        if self._wallet_is_ready(context.user_id, context.ticket_usd):
            return
        self.prepare_user_wallet(context.user_id, context.ticket_usd)

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

    def _remember_wallet_ready(self, user_id: str, collateral_usd: Decimal) -> None:
        with self._balance_lock:
            current = self._wallet_ready_cache.get(user_id)
            ready_collateral = max(collateral_usd, current[1]) if current else collateral_usd
            self._wallet_ready_cache[user_id] = (time.monotonic(), ready_collateral)

    def _wallet_is_ready(self, user_id: str, collateral_usd: Decimal) -> bool:
        with self._balance_lock:
            cached = self._wallet_ready_cache.get(user_id)
        return bool(
            cached
            and time.monotonic() - cached[0] <= self.BALANCE_CACHE_SECONDS
            and cached[1] >= collateral_usd
        )

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


class WalletNotReady(RuntimeError):
    pass


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _demo_delay_ms(execution_id: str, action: TradeAction) -> int:
    digest = hashlib.sha256(execution_id.encode()).digest()
    spread = int.from_bytes(digest[:2], "big") % 401
    baseline = 1_250 if action == TradeAction.OPEN else 950
    return baseline + spread


def _demo_terminal_reason(position, price: Decimal) -> str | None:
    if position.side == TradeSide.LONG:
        if position.liquidation_price is not None and price <= position.liquidation_price:
            return "liquidation"
        if position.stop_loss_price is not None and price <= position.stop_loss_price:
            return "stop_loss"
        if position.take_profit_price is not None and price >= position.take_profit_price:
            return "take_profit"
        return None
    if position.liquidation_price is not None and price >= position.liquidation_price:
        return "liquidation"
    if position.stop_loss_price is not None and price >= position.stop_loss_price:
        return "stop_loss"
    if position.take_profit_price is not None and price <= position.take_profit_price:
        return "take_profit"
    return None
