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


DIRECT_SEQUENCER_URL = "https://arb1-sequencer.arbitrum.io/rpc"
PreparedHandler = Callable[[str, int, str], None]
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
            except Exception:
                EVM_NONCES.invalidate(sender)
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

    def _account(self):
        from eth_account import Account

        key = self._settings.platform_gas_wallet_private_key.strip()
        if not key:
            raise GasFundingError("PLATFORM_GAS_WALLET_PRIVATE_KEY is not configured")
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
        executor: ArbitrumGasTopupExecutor | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or GasTopupRepository(self._settings)
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
    ) -> dict[str, object]:
        cached = self._cached_balance(wallet_address)
        if cached is not None and cached >= self._settings.user_gas_min_eth:
            return {
                "status": "ready",
                "nativeEth": str(cached),
                "source": "warm_cache",
            }
        current = self._executor.native_balance(wallet_address)
        self._remember(wallet_address, current)
        if current >= self._settings.user_gas_min_eth:
            return {
                "status": "ready",
                "nativeEth": str(current),
                "source": "arbitrum_rpc",
            }

        amount = self._settings.user_gas_target_eth - current
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
        except Exception as exc:
            self._repository.mark_retryable_error(
                context.topup_id,
                f"{type(exc).__name__}: {exc}",
            )
            raise
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
            "amountEth": str(context.amount_native),
            "txHash": result.tx_hash,
            "source": "platform_gas_wallet",
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


def _fee_params(web3: Any) -> dict[str, int]:
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    priority = 10_000_000
    return {
        "maxFeePerGas": int(Decimal(base_fee) * Decimal("2.0")) + priority,
        "maxPriorityFeePerGas": priority,
    }


def _normalize_hash(value: str) -> str:
    normalized = value.lower()
    return normalized if normalized.startswith("0x") else f"0x{normalized}"


def _elapsed_ms(started_at: float, finished_at: float) -> float:
    return round((finished_at - started_at) * 1000, 1)
