from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_UP
from typing import Any

from sqlalchemy import func

from tick_mvp.core.config import Settings, get_settings
from tick_mvp.infrastructure.database import create_session_factory, session_scope
from tick_mvp.domain.accounting import net_wallet_delta
from tick_mvp.domain.states import ReconciliationStatus, TradeAction
from tick_mvp.infrastructure.models import (
    ExecutionAttempt,
    LedgerEvent,
    Position,
    Reconciliation,
    TradeIntent,
    Withdrawal,
)


CHAINLINK_AGGREGATOR_ABI = [
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "latestRoundData",
        "outputs": [
            {"name": "roundId", "type": "uint80"},
            {"name": "answer", "type": "int256"},
            {"name": "startedAt", "type": "uint256"},
            {"name": "updatedAt", "type": "uint256"},
            {"name": "answeredInRound", "type": "uint80"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass(frozen=True, slots=True)
class GasTransaction:
    tx_hash: str
    gas_used: int
    effective_gas_price: int
    operation: str
    gas_payer_address: str | None = None

    @property
    def native_cost(self) -> Decimal:
        return Decimal(self.gas_used * self.effective_gas_price) / Decimal(10**18)


@dataclass(frozen=True, slots=True)
class GasCharge:
    tx_hash: str
    operation: str
    native_cost: Decimal
    eth_usd_price: Decimal
    charge_usdc: Decimal
    oracle_updated_at: int


class EthUsdOracle:
    CACHE_SECONDS = 30.0

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._web3 = None
        self._contract = None
        self._cache: tuple[float, Decimal, int] | None = None
        self._lock = threading.Lock()

    def price(self) -> tuple[Decimal, int]:
        with self._lock:
            if self._cache and time.monotonic() - self._cache[0] <= self.CACHE_SECONDS:
                return self._cache[1], self._cache[2]
            contract = self._feed()
            decimals = int(contract.functions.decimals().call())
            round_data = contract.functions.latestRoundData().call()
            answer = int(round_data[1])
            updated_at = int(round_data[3])
            now = int(datetime.now(UTC).timestamp())
            if answer <= 0:
                raise GasAccountingUnavailable("ETH/USD oracle returned a non-positive price")
            if updated_at <= 0 or now - updated_at > self._settings.arb_eth_usd_max_age_seconds:
                raise GasAccountingUnavailable("ETH/USD oracle price is stale")
            price = Decimal(answer) / Decimal(10**decimals)
            self._cache = (time.monotonic(), price, updated_at)
            return price, updated_at

    def _feed(self):
        if self._contract is not None:
            return self._contract
        web3 = self._rpc()
        self._contract = web3.eth.contract(
            address=web3.to_checksum_address(
                self._settings.arb_eth_usd_feed_address
            ),
            abi=CHAINLINK_AGGREGATOR_ABI,
        )
        return self._contract

    def _rpc(self):
        if self._web3 is not None:
            return self._web3
        from web3 import Web3

        if not self._settings.arb_rpc_url:
            raise GasAccountingUnavailable("ARB_RPC_URL is required for gas accounting")
        self._web3 = Web3(
            Web3.HTTPProvider(
                self._settings.arb_rpc_url,
                request_kwargs={"timeout": 10},
            )
        )
        return self._web3


class GasAccountingRepository:
    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory or create_session_factory()

    def record_charge(
        self,
        *,
        user_id: str,
        charge: GasCharge,
        execution_attempt_id: str | None = None,
        withdrawal_id: str | None = None,
    ) -> Decimal:
        event_id = _event_id(charge.tx_hash)
        now = datetime.now(UTC)
        with session_scope(self._session_factory) as session:
            existing = session.get(LedgerEvent, event_id)
            if existing is not None:
                if existing.position_id:
                    _refresh_position_reconciliation(
                        session,
                        existing.position_id,
                        now=now,
                    )
                return -Decimal(existing.amount)
            position_id = None
            execution = None
            if execution_attempt_id:
                execution = session.get(ExecutionAttempt, execution_attempt_id)
                if execution is not None:
                    intent = session.get(TradeIntent, execution.trade_intent_id)
                    position_id = intent.position_id if intent is not None else None
            session.add(
                LedgerEvent(
                    id=event_id,
                    user_id=user_id,
                    position_id=position_id,
                    event_type="gas_charge",
                    asset="USDC",
                    amount=-charge.charge_usdc,
                    source="platform_gas",
                    execution_attempt_id=execution_attempt_id,
                    withdrawal_id=withdrawal_id,
                    payload={
                        "txHash": charge.tx_hash,
                        "operation": charge.operation,
                        "nativeGasCost": str(charge.native_cost),
                        "ethUsdPrice": str(charge.eth_usd_price),
                        "oracleUpdatedAt": charge.oracle_updated_at,
                    },
                    created_at=now,
                )
            )
            if execution is not None:
                execution.gas_cost_usd = Decimal(
                    execution.gas_cost_usd or 0
                ) + charge.charge_usdc
                execution.gas_charge_asset = "USDC"
                execution.gas_charge_amount = Decimal(
                    execution.gas_charge_amount or 0
                ) + charge.charge_usdc
                execution.updated_at = now
            if withdrawal_id:
                withdrawal = session.get(Withdrawal, withdrawal_id)
                if withdrawal is not None:
                    withdrawal.gas_cost_usd = Decimal(
                        withdrawal.gas_cost_usd or 0
                    ) + charge.charge_usdc
                    withdrawal.gas_charge_asset = "USDC"
                    withdrawal.gas_charge_amount = Decimal(
                        withdrawal.gas_charge_amount or 0
                    ) + charge.charge_usdc
                    withdrawal.updated_at = now
            session.flush()
            if position_id:
                _refresh_position_reconciliation(session, position_id, now=now)
        return charge.charge_usdc

    def total_charges_usdc(self, user_id: str) -> Decimal:
        with session_scope(self._session_factory) as session:
            total = (
                session.query(func.coalesce(func.sum(LedgerEvent.amount), 0))
                .filter(
                    LedgerEvent.user_id == user_id,
                    LedgerEvent.event_type == "gas_charge",
                    LedgerEvent.asset == "USDC",
                )
                .scalar()
            )
        return max(Decimal(0), -Decimal(total or 0))


class GasAccountingService:
    def __init__(
        self,
        settings: Settings | None = None,
        repository: GasAccountingRepository | None = None,
        oracle: EthUsdOracle | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._repository = repository or GasAccountingRepository()
        self._oracle = oracle or EthUsdOracle(self._settings)

    def charge(
        self,
        *,
        user_id: str,
        transaction: GasTransaction,
        execution_attempt_id: str | None = None,
        withdrawal_id: str | None = None,
    ) -> GasCharge:
        eth_usd, oracle_updated_at = self._oracle.price()
        amount = (transaction.native_cost * eth_usd).quantize(
            Decimal("0.000001"),
            rounding=ROUND_UP,
        )
        charge = GasCharge(
            tx_hash=_normalize_hash(transaction.tx_hash),
            operation=transaction.operation,
            native_cost=transaction.native_cost,
            eth_usd_price=eth_usd,
            charge_usdc=amount,
            oracle_updated_at=oracle_updated_at,
        )
        self._repository.record_charge(
            user_id=user_id,
            charge=charge,
            execution_attempt_id=execution_attempt_id,
            withdrawal_id=withdrawal_id,
        )
        return charge

    def total_charges_usdc(self, user_id: str) -> Decimal:
        return self._repository.total_charges_usdc(user_id)


class GasAccountingUnavailable(RuntimeError):
    pass


def gas_transaction(
    *,
    tx_hash: str | None,
    gas_used: int | None,
    effective_gas_price: int | None,
    operation: str,
    gas_payer_address: str | None = None,
) -> GasTransaction | None:
    if not tx_hash or gas_used is None or effective_gas_price is None:
        return None
    return GasTransaction(
        tx_hash=tx_hash,
        gas_used=int(gas_used),
        effective_gas_price=int(effective_gas_price),
        operation=operation,
        gas_payer_address=gas_payer_address,
    )


def gas_transactions_from_payload(payload: object) -> list[GasTransaction]:
    if not isinstance(payload, list):
        return []
    transactions: list[GasTransaction] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        transaction = gas_transaction(
            tx_hash=str(item.get("txHash") or ""),
            gas_used=_int_or_none(item.get("gasUsed")),
            effective_gas_price=_int_or_none(item.get("effectiveGasPrice")),
            operation=str(item.get("operation") or item.get("label") or "wallet"),
            gas_payer_address=(
                str(item["gasPayer"]) if item.get("gasPayer") else None
            ),
        )
        if transaction is not None:
            transactions.append(transaction)
    return transactions


def spendable_usdc(onchain_usdc: Decimal, gas_charges_usdc: Decimal) -> Decimal:
    return max(Decimal(0), onchain_usdc - gas_charges_usdc)


def _event_id(tx_hash: str) -> str:
    return f"gas_charge_{_normalize_hash(tx_hash).removeprefix('0x')}"


def _normalize_hash(value: str) -> str:
    normalized = value.lower()
    return normalized if normalized.startswith("0x") else f"0x{normalized}"


def _refresh_position_reconciliation(
    session,
    position_id: str,
    *,
    now: datetime,
) -> None:
    position = session.get(Position, position_id)
    if position is None:
        return
    reconciliation = (
        session.query(Reconciliation)
        .filter(Reconciliation.position_id == position_id)
        .order_by(Reconciliation.created_at.desc())
        .first()
    )
    if reconciliation is None:
        return
    payload = reconciliation.payload or {}
    raw_balance_after = (
        payload.get("accountBalanceAfterTerminalUsd")
        or payload.get("accountBalanceAfterCloseUsd")
    )
    if raw_balance_after is None:
        return
    gas_ledger_total = (
        session.query(func.coalesce(func.sum(LedgerEvent.amount), 0))
        .filter(
            LedgerEvent.position_id == position_id,
            LedgerEvent.event_type == "gas_charge",
            LedgerEvent.asset == "USDC",
        )
        .scalar()
    )
    wallet_delta = net_wallet_delta(
        position.payload,
        Decimal(str(raw_balance_after)),
        Decimal(gas_ledger_total or 0),
    )
    if wallet_delta is None:
        return
    reconciliation.wallet_delta_usd = wallet_delta
    reconciliation.status = (
        ReconciliationStatus.WALLET_RECONCILED.value
        if platform_gas_complete(session, position)
        else ReconciliationStatus.VENUE_ACCOUNTED.value
    )
    reconciliation.updated_at = now


def platform_gas_complete(session, position: Position) -> bool:
    terminal_reason = str((position.payload or {}).get("terminalReason") or "")
    expected_action = (
        TradeAction.CLOSE.value
        if terminal_reason == "manual_close"
        else TradeAction.OPEN.value
    )
    return (
        session.query(LedgerEvent.id)
        .join(
            ExecutionAttempt,
            ExecutionAttempt.id == LedgerEvent.execution_attempt_id,
        )
        .filter(
            LedgerEvent.position_id == position.id,
            LedgerEvent.event_type == "gas_charge",
            LedgerEvent.asset == "USDC",
            ExecutionAttempt.action == expected_action,
        )
        .first()
        is not None
    )


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)
