from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from tick_mvp.core.config import Settings
from tick_mvp.infrastructure.arbitrum_broadcast import DualBroadcaster
from tick_mvp.wallets.repository import WithdrawalContext


DIRECT_SEQUENCER_URL = "https://arb1-sequencer.arbitrum.io/rpc"
USDC_DECIMALS = 6
USDC_SCALE = 10**USDC_DECIMALS
ERC20_TRANSFER_ABI = [
    {
        "inputs": [
            {"name": "recipient", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

PreparedHandler = Callable[[str, int, str], None]
BroadcastHandler = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class WalletTransferResult:
    status: str
    tx_hash: str
    nonce: int
    block_number: int
    gas_used: int
    effective_gas_price: int
    gas_cost_native: Decimal
    payload: dict[str, Any]


class ArbitrumUSDCTransferExecutor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._read_web3 = None
        self._sequencer_web3 = None
        self._usdc_contract = None
        self._broadcaster = DualBroadcaster()

    def close(self) -> None:
        self._broadcaster.close()

    def transfer(
        self,
        context: WithdrawalContext,
        *,
        on_prepared: PreparedHandler,
        on_broadcast: BroadcastHandler,
    ) -> WalletTransferResult:
        if context.asset.upper() != "USDC":
            raise WithdrawalRejected(f"unsupported withdrawal asset: {context.asset}")
        web3 = self._web3()
        raw_transaction: bytes
        expected_tx_hash: str
        nonce: int

        if context.signed_raw_transaction:
            raw_transaction = bytes.fromhex(
                context.signed_raw_transaction.removeprefix("0x")
            )
            expected_tx_hash = _normalize_hash(web3.keccak(raw_transaction).hex())
            if context.tx_hash and expected_tx_hash != _normalize_hash(context.tx_hash):
                raise WithdrawalAmbiguous("stored signed transaction hash does not match")
            if context.nonce is None:
                raise WithdrawalAmbiguous("stored signed transaction has no nonce")
            nonce = context.nonce
        else:
            raw_transaction, expected_tx_hash, nonce = self._prepare(context, web3)
            on_prepared(
                expected_tx_hash,
                nonce,
                f"0x{raw_transaction.hex()}",
            )

        started = time.perf_counter()
        race = self._broadcaster.broadcast(
            raw_transaction=raw_transaction,
            expected_tx_hash=expected_tx_hash,
            primary_web3=web3,
            sequencer_web3=self._sequencer(),
        )
        broadcast_at = time.perf_counter()
        race.wait_for_outcomes(timeout=0.02)
        on_broadcast(expected_tx_hash, race.payload())
        receipt = web3.eth.wait_for_transaction_receipt(
            expected_tx_hash,
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
        payload = {
            "status": status,
            "writeTransport": race.winner,
            "broadcast": race.payload(),
            "timingMs": {
                "broadcastToResponse": _elapsed_ms(started, broadcast_at),
                "receipt": _elapsed_ms(broadcast_at, receipt_at),
                "total": _elapsed_ms(started, receipt_at),
            },
        }
        return WalletTransferResult(
            status="confirmed" if status == 1 else "reverted",
            tx_hash=expected_tx_hash,
            nonce=nonce,
            block_number=int(receipt.blockNumber),
            gas_used=gas_used,
            effective_gas_price=gas_price,
            gas_cost_native=Decimal(gas_used * gas_price) / Decimal(10**18),
            payload=payload,
        )

    def _prepare(
        self,
        context: WithdrawalContext,
        web3: Any,
    ) -> tuple[bytes, str, int]:
        account = _account(context.private_key_hex)
        address = web3.to_checksum_address(account.address)
        if address.lower() != context.wallet_address.lower():
            raise WithdrawalRejected("custody key does not match withdrawal wallet")
        if not web3.is_address(context.destination_address):
            raise WithdrawalRejected("destination is not a valid EVM address")
        destination = web3.to_checksum_address(context.destination_address)
        amount_units = _amount_units(context.amount)
        contract = self._usdc(web3)

        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="withdrawal-read") as executor:
            nonce_future = executor.submit(
                web3.eth.get_transaction_count,
                address,
                "pending",
            )
            fee_future = executor.submit(_fee_params, web3)
            usdc_future = executor.submit(
                contract.functions.balanceOf(address).call,
            )
            native_future = executor.submit(web3.eth.get_balance, address)
            nonce = int(nonce_future.result())
            fee_params = fee_future.result()
            usdc_balance = int(usdc_future.result())
            native_balance = int(native_future.result())

        if usdc_balance < amount_units:
            raise WithdrawalRejected("insufficient USDC balance")
        max_gas_cost = self._settings.arb_usdc_transfer_gas * int(
            fee_params["maxFeePerGas"]
        )
        if native_balance < max_gas_cost:
            raise WithdrawalRejected("insufficient ETH for withdrawal gas")

        tx = contract.functions.transfer(destination, amount_units).build_transaction(
            {
                "from": address,
                "chainId": self._settings.arb_chain_id,
                "nonce": nonce,
                "gas": self._settings.arb_usdc_transfer_gas,
                **fee_params,
            }
        )
        signed = account.sign_transaction(tx)
        raw_transaction = (
            getattr(signed, "raw_transaction", None) or signed.rawTransaction
        )
        expected_tx_hash = _normalize_hash(web3.keccak(raw_transaction).hex())
        return bytes(raw_transaction), expected_tx_hash, nonce

    def _web3(self):
        if self._read_web3 is not None:
            return self._read_web3
        from web3 import Web3

        if not self._settings.arb_rpc_url:
            raise WithdrawalRetryable("ARB_RPC_URL is required for withdrawals")
        web3 = Web3(
            Web3.HTTPProvider(
                self._settings.arb_rpc_url,
                request_kwargs={"timeout": 20},
            )
        )
        if not web3.is_connected():
            raise WithdrawalRetryable("could not connect to ARB_RPC_URL")
        chain_id = int(web3.eth.chain_id)
        if chain_id != self._settings.arb_chain_id:
            raise WithdrawalRejected(
                f"RPC chain_id {chain_id}, expected {self._settings.arb_chain_id}"
            )
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

    def _usdc(self, web3: Any):
        if self._usdc_contract is None:
            self._usdc_contract = web3.eth.contract(
                address=web3.to_checksum_address(self._settings.arb_usdc_address),
                abi=ERC20_TRANSFER_ABI,
            )
        return self._usdc_contract


class WithdrawalRejected(RuntimeError):
    pass


class WithdrawalRetryable(RuntimeError):
    pass


class WithdrawalAmbiguous(WithdrawalRetryable):
    pass


def _account(private_key_hex: str):
    from eth_account import Account

    key = private_key_hex.strip()
    return Account.from_key(key if key.startswith("0x") else f"0x{key}")


def _amount_units(amount: Decimal) -> int:
    scaled = amount * Decimal(USDC_SCALE)
    if scaled != scaled.to_integral_value():
        raise WithdrawalRejected("USDC amount supports at most 6 decimal places")
    units = int(scaled)
    if units <= 0:
        raise WithdrawalRejected("withdrawal amount must be positive")
    return units


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
