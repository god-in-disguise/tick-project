from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.domain.states import GasTopupStatus
from tick_mvp.infrastructure.arbitrum_broadcast import DualBroadcaster
from tick_mvp.infrastructure.evm_nonce import EVM_NONCES
from tick_mvp.wallets.gas_repository import GasTopupContext, GasTopupRepository
from tick_mvp.wallets.gas_sweep_repository import (
    GasSweepContext,
    GasSweepRepository,
)


DIRECT_SEQUENCER_URL = "https://arb1-sequencer.arbitrum.io/rpc"
PreparedHandler = Callable[[str, int, str], None]
SweepPreparedHandler = Callable[[str, int, str, Decimal], None]
BroadcastHandler = Callable[[str, dict[str, Any]], None]
LOGGER = logging.getLogger("tick.gas")


@dataclass(frozen=True, slots=True)
class GasTopupResult:
    status: str
    tx_hash: str
    nonce: int
    block_number: int
    gas_used: int
    effective_gas_price: int
    gas_cost_native: Decimal
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GasSweepResult:
    status: str
    tx_hash: str
    nonce: int
    block_number: int
    gas_used: int
    effective_gas_price: int
    amount_native: Decimal
    gas_cost_native: Decimal
    payload: dict[str, Any]


class ArbitrumGasTopupExecutor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._read_web3 = None
        self._sequencer_web3 = None
        self._broadcaster = DualBroadcaster()

    @property
    def platform_address(self) -> str:
        return self._account().address

    def close(self) -> None:
        self._broadcaster.close()

    def native_balance(self, address: str) -> Decimal:
        web3 = self._web3()
        return Decimal(web3.eth.get_balance(web3.to_checksum_address(address))) / Decimal(
            10**18
        )

    def required_native(self, gas_units: int) -> Decimal:
        if gas_units <= 0:
            return Decimal(0)
        fee_params = _fee_params(self._web3())
        return Decimal(gas_units * fee_params["maxFeePerGas"]) / Decimal(10**18)

    def sweep_plan(
        self,
        address: str,
        recoverable_native: Decimal,
    ) -> tuple[Decimal, Decimal]:
        web3 = self._web3()
        balance_wei = int(web3.eth.get_balance(web3.to_checksum_address(address)))
        fee_params = _fee_params(web3)
        max_gas_wei = (
            self._settings.gas_sweep_transfer_gas * fee_params["maxFeePerGas"]
        )
        recoverable_wei = int(recoverable_native * Decimal(10**18))
        amount_wei = max(0, min(balance_wei, recoverable_wei) - max_gas_wei)
        return (
            Decimal(balance_wei) / Decimal(10**18),
            Decimal(amount_wei) / Decimal(10**18),
        )

    def transfer(
        self,
        context: GasTopupContext,
        *,
        on_prepared: PreparedHandler,
        on_broadcast: BroadcastHandler,
    ) -> GasTopupResult:
        web3 = self._web3()
        started = time.perf_counter()
        sender = web3.to_checksum_address(self.platform_address)
        with EVM_NONCES.sender_lock(sender):
            try:
                if context.signed_raw_transaction:
                    raw_transaction = bytes.fromhex(
                        context.signed_raw_transaction.removeprefix("0x")
                    )
                    tx_hash = _normalize_hash(web3.keccak(raw_transaction).hex())
                    if context.tx_hash and tx_hash != _normalize_hash(context.tx_hash):
                        raise GasFundingError("stored gas top-up transaction hash does not match")
                    if context.nonce is None:
                        raise GasFundingError("stored gas top-up transaction has no nonce")
                    nonce = context.nonce
                    EVM_NONCES.observe(sender, nonce)
                else:
                    raw_transaction, tx_hash, nonce = self._prepare(context, web3)
                    on_prepared(tx_hash, nonce, f"0x{raw_transaction.hex()}")

                race = self._broadcaster.broadcast(
                    raw_transaction=raw_transaction,
                    expected_tx_hash=tx_hash,
                    primary_web3=web3,
                    sequencer_web3=self._sequencer(),
                )
                broadcast_at = time.perf_counter()
                race.wait_for_outcomes(timeout=0.02)
                on_broadcast(tx_hash, race.payload())
            except Exception as exc:
                EVM_NONCES.invalidate(sender)
                if (
                    "nonce" in locals()
                    and "tx_hash" in locals()
                    and _is_nonce_too_low_error(exc)
                    and _chain_nonce_is_past(web3, sender, nonce)
                ):
                    raise StaleGasTopupTransaction(tx_hash=tx_hash, nonce=nonce)
                raise

        receipt = web3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=90,
            poll_latency=0.2,
        )
        receipt_at = time.perf_counter()
        gas_used = int(receipt.gasUsed)
        gas_price = int(
            getattr(receipt, "effectiveGasPrice", 0)
            or receipt.get("effectiveGasPrice", 0)
            or 0
        )
        status = int(receipt.status)
        return GasTopupResult(
            status="confirmed" if status == 1 else "reverted",
            tx_hash=tx_hash,
            nonce=nonce,
            block_number=int(receipt.blockNumber),
            gas_used=gas_used,
            effective_gas_price=gas_price,
            gas_cost_native=Decimal(gas_used * gas_price) / Decimal(10**18),
            payload={
                "status": status,
                "writeTransport": race.winner,
                "broadcast": race.payload(),
                "timingMs": {
                    "broadcastToResponse": _elapsed_ms(started, broadcast_at),
                    "receipt": _elapsed_ms(broadcast_at, receipt_at),
                    "total": _elapsed_ms(started, receipt_at),
                },
            },
        )

    def sweep(
        self,
        context: GasSweepContext,
        *,
        private_key_hex: str,
        on_prepared: SweepPreparedHandler,
        on_broadcast: BroadcastHandler,
    ) -> GasSweepResult:
        web3 = self._web3()
        started = time.perf_counter()
        account = self._user_account(private_key_hex)
        sender = web3.to_checksum_address(account.address)
        if sender.lower() != context.wallet_address.lower():
            raise GasFundingError("custody key does not match gas sweep wallet")
        if context.tx_hash:
            recovered_receipt = _receipt_or_none(web3, context.tx_hash)
            if recovered_receipt is not None:
                return self._sweep_result(
                    context,
                    recovered_receipt,
                    payload={"recoveredByHash": True},
                )
        with EVM_NONCES.sender_lock(sender):
            try:
                if context.signed_raw_transaction:
                    raw_transaction = bytes.fromhex(
                        context.signed_raw_transaction.removeprefix("0x")
                    )
                    tx_hash = _normalize_hash(web3.keccak(raw_transaction).hex())
                    if context.tx_hash and tx_hash != _normalize_hash(context.tx_hash):
                        raise GasFundingError("stored gas sweep transaction hash does not match")
                    if context.nonce is None:
                        raise GasFundingError("stored gas sweep transaction has no nonce")
                    nonce = context.nonce
                    signed_amount_native = context.amount_native
                    EVM_NONCES.observe(sender, nonce)
                else:
                    (
                        raw_transaction,
                        tx_hash,
                        nonce,
                        signed_amount_native,
                    ) = self._prepare_sweep(context, account, web3)
                    on_prepared(
                        tx_hash,
                        nonce,
                        f"0x{raw_transaction.hex()}",
                        signed_amount_native,
                    )

                race = self._broadcaster.broadcast(
                    raw_transaction=raw_transaction,
                    expected_tx_hash=tx_hash,
                    primary_web3=web3,
                    sequencer_web3=self._sequencer(),
                )
                broadcast_at = time.perf_counter()
                race.wait_for_outcomes(timeout=0.02)
                on_broadcast(tx_hash, race.payload())
            except Exception as exc:
                EVM_NONCES.invalidate(sender)
                if "tx_hash" in locals():
                    recovered_receipt = _receipt_or_none(web3, tx_hash)
                    if recovered_receipt is not None:
                        return self._sweep_result(
                            context,
                            recovered_receipt,
                            payload={"recoveredAfterBroadcastError": True},
                        )
                if (
                    "nonce" in locals()
                    and "tx_hash" in locals()
                    and _is_nonce_too_low_error(exc)
                    and _chain_nonce_is_past(web3, sender, nonce)
                ):
                    raise StaleGasSweepTransaction(tx_hash=tx_hash, nonce=nonce)
                raise

        receipt = web3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=90,
            poll_latency=0.2,
        )
        receipt_at = time.perf_counter()
        return self._sweep_result(
            context,
            receipt,
            amount_native=signed_amount_native,
            payload={
                "txHash": tx_hash,
                "nonce": nonce,
                "writeTransport": race.winner,
                "broadcast": race.payload(),
                "timingMs": {
                    "broadcastToResponse": _elapsed_ms(started, broadcast_at),
                    "receipt": _elapsed_ms(broadcast_at, receipt_at),
                    "total": _elapsed_ms(started, receipt_at),
                },
            },
        )

    @staticmethod
    def _sweep_result(
        context: GasSweepContext,
        receipt: Any,
        *,
        amount_native: Decimal | None = None,
        payload: dict[str, Any],
    ) -> GasSweepResult:
        gas_used = int(receipt.gasUsed)
        gas_price = int(
            getattr(receipt, "effectiveGasPrice", 0)
            or receipt.get("effectiveGasPrice", 0)
            or 0
        )
        status = int(receipt.status)
        tx_hash = _normalize_hash(
            getattr(receipt, "transactionHash", None)
            or receipt.get("transactionHash")
            or context.tx_hash
            or ""
        )
        return GasSweepResult(
            status="confirmed" if status == 1 else "reverted",
            tx_hash=tx_hash,
            nonce=int(payload.get("nonce") or context.nonce or 0),
            block_number=int(receipt.blockNumber),
            gas_used=gas_used,
            effective_gas_price=gas_price,
            amount_native=amount_native or context.amount_native,
            gas_cost_native=Decimal(gas_used * gas_price) / Decimal(10**18),
            payload={**payload, "status": status},
        )

    def _prepare(
        self,
        context: GasTopupContext,
        web3: Any,
    ) -> tuple[bytes, str, int]:
        account = self._account()
        recipient = web3.to_checksum_address(context.wallet_address)
        amount_wei = int(context.amount_native * Decimal(10**18))
        if amount_wei <= 0:
            raise GasFundingError("gas top-up amount must be positive")
        nonce = EVM_NONCES.reserve(web3, account.address)
        fee_params = _fee_params(web3)
        max_cost = amount_wei + (
            self._settings.gas_topup_transfer_gas * fee_params["maxFeePerGas"]
        )
        if int(web3.eth.get_balance(account.address)) < max_cost:
            raise GasFundingError("platform gas wallet has insufficient ETH")
        signed = account.sign_transaction(
            {
                "from": account.address,
                "to": recipient,
                "value": amount_wei,
                "chainId": self._settings.arb_chain_id,
                "nonce": nonce,
                "gas": self._settings.gas_topup_transfer_gas,
                **fee_params,
            }
        )
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = _normalize_hash(web3.keccak(raw).hex())
        return bytes(raw), tx_hash, nonce

    def _prepare_sweep(
        self,
        context: GasSweepContext,
        account: Any,
        web3: Any,
    ) -> tuple[bytes, str, int, Decimal]:
        requested_amount_wei = int(context.amount_native * Decimal(10**18))
        if requested_amount_wei <= 0:
            raise GasFundingError("gas sweep amount must be positive")
        nonce = EVM_NONCES.reserve(web3, account.address)
        fee_params = _fee_params(web3)
        balance_wei = int(web3.eth.get_balance(account.address))
        max_gas_wei = (
            self._settings.gas_sweep_transfer_gas
            * fee_params["maxFeePerGas"]
        )
        amount_wei = min(requested_amount_wei, balance_wei - max_gas_wei)
        if amount_wei <= 0:
            raise GasFundingError("user wallet has insufficient ETH for gas sweep")
        signed = account.sign_transaction(
            {
                "from": account.address,
                "to": self.platform_address,
                "value": amount_wei,
                "chainId": self._settings.arb_chain_id,
                "nonce": nonce,
                "gas": self._settings.gas_sweep_transfer_gas,
                **fee_params,
            }
        )
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = _normalize_hash(web3.keccak(raw).hex())
        return (
            bytes(raw),
            tx_hash,
            nonce,
            Decimal(amount_wei) / Decimal(10**18),
        )

    def _account(self):
        from eth_account import Account

        key = self._settings.platform_gas_wallet_private_key.strip()
        if not key:
            raise GasFundingError("PLATFORM_GAS_WALLET_PRIVATE_KEY is not configured")
        return Account.from_key(key if key.startswith("0x") else f"0x{key}")

    @staticmethod
    def _user_account(private_key_hex: str):
        from eth_account import Account

        key = private_key_hex.strip()
        return Account.from_key(key if key.startswith("0x") else f"0x{key}")

    def _web3(self):
        if self._read_web3 is not None:
            return self._read_web3
        from web3 import Web3

        if not self._settings.arb_rpc_url:
            raise GasFundingError("ARB_RPC_URL is required for platform gas funding")
        web3 = Web3(
            Web3.HTTPProvider(
                self._settings.arb_rpc_url,
                request_kwargs={"timeout": 20},
            )
        )
        if not web3.is_connected():
            raise GasFundingError("could not connect to ARB_RPC_URL")
        if int(web3.eth.chain_id) != self._settings.arb_chain_id:
            raise GasFundingError("platform gas RPC is on the wrong chain")
        self._read_web3 = web3
        return web3

    def _sequencer(self):
        if self._sequencer_web3 is not None:
            return self._sequencer_web3
        from web3 import Web3

        self._sequencer_web3 = Web3(
            Web3.HTTPProvider(DIRECT_SEQUENCER_URL, request_kwargs={"timeout": 8})
        )
        return self._sequencer_web3


class GasFundingService:
    CACHE_SECONDS = 30.0

    def __init__(
        self,
        settings: Settings | None = None,
        repository: GasTopupRepository | None = None,
        sweep_repository: GasSweepRepository | None = None,
        executor: ArbitrumGasTopupExecutor | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or GasTopupRepository(self._settings)
        self._sweep_repository = sweep_repository or GasSweepRepository(self._settings)
        self._executor = executor or ArbitrumGasTopupExecutor(self._settings)
        self._cache: dict[str, tuple[float, Decimal]] = {}
        self._cache_lock = threading.Lock()

    @property
    def platform_address(self) -> str:
        return self._executor.platform_address

    def close(self) -> None:
        self._executor.close()

    def ensure_funded(
        self,
        *,
        user_id: str,
        wallet_id: str,
        wallet_address: str,
        required_gas_units: int | None = None,
    ) -> dict[str, object]:
        target = (
            self._settings.user_gas_target_eth
            if required_gas_units is None
            else self._executor.required_native(required_gas_units)
            + self._settings.user_gas_buffer_eth
        )
        ready_at = (
            self._settings.user_gas_min_eth
            if required_gas_units is None
            else target
        )
        cached = self._cached_balance(wallet_address)
        if cached is not None and cached >= ready_at:
            return {
                "status": "ready",
                "nativeEth": str(cached),
                "requiredEth": str(target),
                "source": "warm_cache",
            }
        current = self._executor.native_balance(wallet_address)
        self._remember(wallet_address, current)
        if current >= ready_at:
            return {
                "status": "ready",
                "nativeEth": str(current),
                "requiredEth": str(target),
                "source": "arbitrum_rpc",
            }

        amount = target - current
        context = self._repository.create_or_load(
            user_id=user_id,
            wallet_id=wallet_id,
            wallet_address=wallet_address,
            amount_native=amount,
        )
        if context.status == GasTopupStatus.CONFIRMED:
            refreshed = self._executor.native_balance(wallet_address)
            self._remember(wallet_address, refreshed)
            return {
                "status": "ready",
                "nativeEth": str(refreshed),
                "source": "confirmed_topup",
            }
        result = None
        for attempt in range(2):
            try:
                result = self._executor.transfer(
                    context,
                    on_prepared=lambda tx_hash, nonce, signed_raw: self._repository.mark_signed(
                        context.topup_id,
                        tx_hash=tx_hash,
                        nonce=nonce,
                        signed_raw_transaction=signed_raw,
                    ),
                    on_broadcast=lambda tx_hash, payload: self._repository.mark_broadcast(
                        context.topup_id,
                        tx_hash=tx_hash,
                        payload=payload,
                    ),
                )
                break
            except StaleGasTopupTransaction as exc:
                self._repository.mark_superseded(
                    context.topup_id,
                    tx_hash=exc.tx_hash,
                    nonce=exc.nonce,
                )
                current = self._executor.native_balance(wallet_address)
                self._remember(wallet_address, current)
                if current >= ready_at:
                    return {
                        "status": "ready",
                        "nativeEth": str(current),
                        "requiredEth": str(target),
                        "source": "recovered_topup",
                    }
                if attempt > 0:
                    raise
                context = self._repository.create_or_load(
                    user_id=user_id,
                    wallet_id=wallet_id,
                    wallet_address=wallet_address,
                    amount_native=target - current,
                )
            except Exception as exc:
                self._repository.mark_retryable_error(
                    context.topup_id,
                    f"{type(exc).__name__}: {exc}",
                )
                raise
        if result is None:
            raise GasFundingError("platform gas top-up did not produce a result")
        confirmation = {
            **result.payload,
            "blockNumber": result.block_number,
            "gasUsed": result.gas_used,
            "effectiveGasPrice": result.effective_gas_price,
        }
        if result.status != "confirmed":
            self._repository.mark_reverted(
                context.topup_id,
                tx_hash=result.tx_hash,
                payload=confirmation,
            )
            raise GasFundingError("platform gas top-up transaction reverted")
        self._repository.mark_confirmed(
            context.topup_id,
            tx_hash=result.tx_hash,
            gas_cost_native=result.gas_cost_native,
            payload=confirmation,
        )
        funded = current + context.amount_native
        self._remember(wallet_address, funded)
        LOGGER.info(
            "Funded user gas wallet userId=%s wallet=%s amountEth=%s txHash=%s",
            user_id,
            wallet_address,
            context.amount_native,
            result.tx_hash,
        )
        return {
            "status": "funded",
            "nativeEth": str(funded),
            "requiredEth": str(target),
            "amountEth": str(context.amount_native),
            "txHash": result.tx_hash,
            "source": "platform_gas_wallet",
        }

    def reclaim_excess(
        self,
        *,
        user_id: str,
        wallet_id: str,
        wallet_address: str,
        private_key_hex: str,
    ) -> dict[str, object]:
        context = self._sweep_repository.load_active(
            user_id=user_id,
            wallet_id=wallet_id,
            wallet_address=wallet_address,
        )
        balance = self._executor.native_balance(wallet_address)
        if context is None:
            recoverable = self._sweep_repository.recoverable_native(
                user_id=user_id,
                wallet_id=wallet_id,
                wallet_address=wallet_address,
            )
            balance, amount = self._executor.sweep_plan(
                wallet_address,
                recoverable,
            )
            if amount < self._settings.user_gas_sweep_min_eth:
                self._remember(wallet_address, balance)
                return {
                    "status": "retained",
                    "nativeEth": str(balance),
                    "recoverableEth": str(recoverable),
                }
            context = self._sweep_repository.create_or_load(
                user_id=user_id,
                wallet_id=wallet_id,
                wallet_address=wallet_address,
                amount_native=amount,
            )

        result = None
        for attempt in range(2):
            try:
                result = self._executor.sweep(
                    context,
                    private_key_hex=private_key_hex,
                    on_prepared=(
                        lambda tx_hash, nonce, signed_raw, amount_native: (
                            self._sweep_repository.mark_signed(
                                context.sweep_id,
                                tx_hash=tx_hash,
                                nonce=nonce,
                                signed_raw_transaction=signed_raw,
                                amount_native=amount_native,
                            )
                        )
                    ),
                    on_broadcast=lambda tx_hash, payload: self._sweep_repository.mark_broadcast(
                        context.sweep_id,
                        tx_hash=tx_hash,
                        payload=payload,
                    ),
                )
                break
            except StaleGasSweepTransaction as exc:
                self._sweep_repository.mark_superseded(
                    context.sweep_id,
                    tx_hash=exc.tx_hash,
                    nonce=exc.nonce,
                )
                if attempt > 0:
                    raise
                recoverable = self._sweep_repository.recoverable_native(
                    user_id=user_id,
                    wallet_id=wallet_id,
                    wallet_address=wallet_address,
                )
                balance, amount = self._executor.sweep_plan(
                    wallet_address,
                    recoverable,
                )
                if amount < self._settings.user_gas_sweep_min_eth:
                    self._remember(wallet_address, balance)
                    return {
                        "status": "recovered",
                        "nativeEth": str(balance),
                    }
                context = self._sweep_repository.create_or_load(
                    user_id=user_id,
                    wallet_id=wallet_id,
                    wallet_address=wallet_address,
                    amount_native=amount,
                )
            except Exception as exc:
                self._sweep_repository.mark_retryable_error(
                    context.sweep_id,
                    f"{type(exc).__name__}: {exc}",
                )
                raise
        if result is None:
            raise GasFundingError("platform gas sweep did not produce a result")
        confirmation = {
            **result.payload,
            "blockNumber": result.block_number,
            "gasUsed": result.gas_used,
            "effectiveGasPrice": result.effective_gas_price,
        }
        if result.status != "confirmed":
            self._sweep_repository.mark_reverted(
                context.sweep_id,
                tx_hash=result.tx_hash,
                payload=confirmation,
            )
            raise GasFundingError("platform gas sweep transaction reverted")
        self._sweep_repository.mark_confirmed(
            context.sweep_id,
            tx_hash=result.tx_hash,
            gas_cost_native=result.gas_cost_native,
            payload=confirmation,
        )
        remaining = max(
            Decimal(0),
            balance - result.amount_native - result.gas_cost_native,
        )
        self._remember(wallet_address, remaining)
        LOGGER.info(
            "Reclaimed user gas reserve userId=%s wallet=%s amountEth=%s txHash=%s",
            user_id,
            wallet_address,
            result.amount_native,
            result.tx_hash,
        )
        return {
            "status": "reclaimed",
            "amountEth": str(result.amount_native),
            "nativeEth": str(remaining),
            "txHash": result.tx_hash,
        }

    def note_spent(self, wallet_address: str, amount_native: Decimal | None) -> None:
        if amount_native is None:
            return
        with self._cache_lock:
            current = self._cache.get(wallet_address.lower())
            if current is None:
                return
            self._cache[wallet_address.lower()] = (
                time.monotonic(),
                max(Decimal(0), current[1] - amount_native),
            )

    def _cached_balance(self, wallet_address: str) -> Decimal | None:
        with self._cache_lock:
            cached = self._cache.get(wallet_address.lower())
        if cached is None or time.monotonic() - cached[0] > self.CACHE_SECONDS:
            return None
        return cached[1]

    def _remember(self, wallet_address: str, balance: Decimal) -> None:
        with self._cache_lock:
            self._cache[wallet_address.lower()] = (time.monotonic(), balance)


class GasFundingError(RuntimeError):
    pass


class StaleGasTopupTransaction(GasFundingError):
    def __init__(self, *, tx_hash: str, nonce: int) -> None:
        super().__init__(f"gas top-up nonce {nonce} was already consumed")
        self.tx_hash = tx_hash
        self.nonce = nonce


class StaleGasSweepTransaction(GasFundingError):
    def __init__(self, *, tx_hash: str, nonce: int) -> None:
        super().__init__(f"gas sweep nonce {nonce} was already consumed")
        self.tx_hash = tx_hash
        self.nonce = nonce


def _is_nonce_too_low_error(exc: Exception) -> bool:
    return "nonce too low" in str(exc).lower()


def _chain_nonce_is_past(web3: Any, sender: str, nonce: int) -> bool:
    try:
        return int(web3.eth.get_transaction_count(sender, "latest")) > nonce
    except Exception:
        return False


def _receipt_or_none(web3: Any, tx_hash: str) -> Any | None:
    try:
        return web3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        return None


def _fee_params(web3: Any) -> dict[str, int]:
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    priority = 10_000_000
    return {
        "maxFeePerGas": int(Decimal(base_fee) * Decimal("2.0")) + priority,
        "maxPriorityFeePerGas": priority,
    }


def _normalize_hash(value: Any) -> str:
    if hasattr(value, "hex"):
        value = value.hex()
    normalized = str(value).lower()
    return normalized if normalized.startswith("0x") else f"0x{normalized}"


def _elapsed_ms(started_at: float, finished_at: float) -> float:
    return round((finished_at - started_at) * 1000, 1)
