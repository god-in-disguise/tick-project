from __future__ import annotations

import logging

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import WithdrawalStatus
from tick_mvp.wallets.arbitrum import (
    ArbitrumUSDCTransferExecutor,
    WithdrawalRejected,
    WithdrawalRetryable,
)
from tick_mvp.wallets.accounting import GasAccountingService, gas_transaction
from tick_mvp.wallets.gas import GasFundingService
from tick_mvp.wallets.repository import (
    WithdrawalBlocked,
    WithdrawalRepository,
)


LOGGER = logging.getLogger("tick.withdrawals")
TERMINAL_STATUSES = {
    WithdrawalStatus.CONFIRMED,
    WithdrawalStatus.FAILED,
    WithdrawalStatus.CANCELED,
}


class WithdrawalService:
    def __init__(
        self,
        settings: Settings | None = None,
        repository: WithdrawalRepository | None = None,
        executor: ArbitrumUSDCTransferExecutor | None = None,
        gas_funding: GasFundingService | None = None,
        gas_accounting: GasAccountingService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or WithdrawalRepository(self._settings)
        self._executor = executor or ArbitrumUSDCTransferExecutor(self._settings)
        self._gas_funding = gas_funding or GasFundingService(self._settings)
        self._gas_accounting = gas_accounting or GasAccountingService(self._settings)

    def stop(self) -> None:
        self._executor.close()

    def execute(self, withdrawal_id: str) -> dict[str, object]:
        if not self._settings.tick_real_execution_enabled:
            return {
                "withdrawalId": withdrawal_id,
                "status": "dry_run",
                "reason": "TICK_REAL_EXECUTION_ENABLED=false",
            }
        try:
            context = self._repository.load(withdrawal_id)
        except WithdrawalBlocked as exc:
            self._repository.mark_failed(withdrawal_id, str(exc))
            return {
                "withdrawalId": withdrawal_id,
                "status": WithdrawalStatus.FAILED.value,
                "error": str(exc),
            }

        if context.status in TERMINAL_STATUSES:
            return {
                "withdrawalId": withdrawal_id,
                "status": context.status.value,
                "txHash": context.tx_hash,
                "alreadyTerminal": True,
            }

        try:
            self._gas_funding.ensure_funded(
                user_id=context.user_id,
                wallet_id=context.wallet_id,
                wallet_address=context.wallet_address,
            )
            result = self._executor.transfer(
                context,
                on_prepared=lambda tx_hash, nonce, signed_raw: self._repository.mark_signed(
                    withdrawal_id,
                    tx_hash=tx_hash,
                    nonce=nonce,
                    signed_raw_transaction=signed_raw,
                ),
                on_broadcast=lambda tx_hash, payload: self._repository.mark_broadcast(
                    withdrawal_id,
                    tx_hash=tx_hash,
                    payload=payload,
                ),
            )
        except WithdrawalRejected as exc:
            self._repository.mark_failed(withdrawal_id, str(exc))
            return {
                "withdrawalId": withdrawal_id,
                "status": WithdrawalStatus.FAILED.value,
                "error": str(exc),
            }
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._repository.mark_retryable_error(withdrawal_id, error)
            LOGGER.warning(
                "withdrawal execution is retryable withdrawalId=%s error=%s",
                withdrawal_id,
                error,
            )
            raise WithdrawalRetryable(error) from exc

        if result.status == "confirmed":
            self._repository.mark_confirmed(
                withdrawal_id,
                tx_hash=result.tx_hash,
                gas_cost_native=result.gas_cost_native,
                payload={
                    **result.payload,
                    "blockNumber": result.block_number,
                    "gasUsed": result.gas_used,
                    "effectiveGasPrice": result.effective_gas_price,
                },
            )
        else:
            self._repository.mark_reverted(
                withdrawal_id,
                tx_hash=result.tx_hash,
                payload={
                    **result.payload,
                    "blockNumber": result.block_number,
                    "gasUsed": result.gas_used,
                    "effectiveGasPrice": result.effective_gas_price,
                },
            )
        transaction = gas_transaction(
            tx_hash=result.tx_hash,
            gas_used=result.gas_used,
            effective_gas_price=result.effective_gas_price,
            operation="withdrawal",
        )
        if transaction is not None:
            self._gas_funding.note_spent(
                context.wallet_address,
                transaction.native_cost,
            )
            try:
                self._gas_accounting.charge(
                    user_id=context.user_id,
                    transaction=transaction,
                    withdrawal_id=withdrawal_id,
                )
            except Exception:
                LOGGER.exception(
                    "withdrawal gas accounting deferred withdrawalId=%s txHash=%s",
                    withdrawal_id,
                    result.tx_hash,
                )
        return {
            "withdrawalId": withdrawal_id,
            "status": result.status,
            "txHash": result.tx_hash,
            "blockNumber": result.block_number,
            "gasCostNative": str(result.gas_cost_native),
        }
