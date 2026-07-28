from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from threading import RLock
from typing import Any, Callable

import requests

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.infrastructure.evm_nonce import EVM_NONCES
from tick_mvp.venues.base import TransactionPreparedHandler, VenueCloseResult, VenueOpenResult, VenueTxResult
from tick_mvp.venues.gtrade.broadcast import DualBroadcaster
from tick_mvp.venues.gtrade.constants import ERC20_ABI, MAX_UINT256, TRADING_ABI, ZERO_ADDRESS
from tick_mvp.venues.gtrade.events import GTradeEventStream
from tick_mvp.venues.gtrade.public import GTradeError, GTradePair, GTradePublicClient


REST_FALLBACK_DELAY_SECONDS = 0.65
FEE_CACHE_MAX_AGE_SECONDS = 3.0
DIRECT_SEQUENCER_URL = "https://arb1-sequencer.arbitrum.io/rpc"
SEQUENCER_KEEPALIVE_SECONDS = 10.0
LOGGER = logging.getLogger("tick.gtrade.wallet")


class GTradeWalletExecutor:
    def __init__(self, settings: Settings, public_client: GTradePublicClient | None = None) -> None:
        self._settings = settings
        self._public = public_client or GTradePublicClient(settings)
        self._read_web3 = None
        self._sequencer_web3 = None
        self._trading_contract = None
        self._usdc_contract = None
        self._cache_lock = RLock()
        self._fee_cache: tuple[float, dict[str, int]] | None = None
        self._allowance_cache: dict[str, Decimal] = {}
        self._delegate_cache: dict[str, tuple[str, float]] = {}
        self._rest_session = requests.Session()
        self._broadcaster = DualBroadcaster()
        self._events = GTradeEventStream(
            settings.gtrade_backend_ws_url,
            arb_wss_url=settings.arb_wss_url,
            diamond_address=settings.gtrade_diamond_address,
        )
        self._fee_stop = threading.Event()
        self._fee_thread: threading.Thread | None = None
        self._sequencer_stop = threading.Event()
        self._sequencer_thread: threading.Thread | None = None

    def start(self) -> None:
        self._events.start()
        if self._uses_platform_agent():
            self._warm_nonce(self._agent().address)
        self._warm_sequencer_connection()
        if not self._sequencer_thread or not self._sequencer_thread.is_alive():
            self._sequencer_stop.clear()
            self._sequencer_thread = threading.Thread(
                target=self._run_sequencer_keepalive,
                name="arbitrum-sequencer-keepalive",
                daemon=True,
            )
            self._sequencer_thread.start()
        if not self._fee_thread or not self._fee_thread.is_alive():
            self._fee_stop.clear()
            self._fee_thread = threading.Thread(target=self._run_fee_warmer, name="gtrade-fees", daemon=True)
            self._fee_thread.start()

    def stop(self) -> None:
        self._sequencer_stop.set()
        if self._sequencer_thread:
            self._sequencer_thread.join(timeout=2)
        self._fee_stop.set()
        if self._fee_thread:
            self._fee_thread.join(timeout=2)
        self._events.stop()
        self._broadcaster.close()
        self._rest_session.close()

    def prepare_wallet(
        self,
        private_key_hex: str,
        required_collateral_usd: Decimal,
        ensure_transaction_gas: Callable[[], Any] | None = None,
    ) -> dict[str, Any]:
        """Warm one user's trading state before the execution gesture."""
        started = time.perf_counter()
        account, address, web3 = self._account(private_key_hex)
        self._events.track_owner(address)
        self._events.start()
        agent_address = self.execution_agent_address()
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="gtrade-wallet-warm") as executor:
            allowance_future = executor.submit(self._usdc_allowance, web3, address)
            balance_future = executor.submit(self._usdc_balance, web3, address)
            delegate_future = (
                executor.submit(self._current_delegate, address)
                if agent_address is not None
                else None
            )
            allowance = allowance_future.result()
            collateral_balance = balance_future.result()
            current_delegate = delegate_future.result() if delegate_future else None

        delegate_ready = agent_address is None or current_delegate == agent_address
        approval_required = (
            self._settings.gtrade_auto_approve_usdc
            and allowance < required_collateral_usd
        )
        setup_required = not delegate_ready or approval_required
        if setup_required:
            if ensure_transaction_gas is None:
                raise GTradeError("user wallet setup requires transaction gas")
            ensure_transaction_gas()

        gas_transactions: list[VenueTxResult] = []
        delegation: VenueTxResult | None = None
        approval: VenueTxResult | None = None
        if setup_required:
            with self._wallet_lock(address):
                current_delegate = (
                    self._current_delegate(address)
                    if agent_address is not None
                    else None
                )
                delegate_ready = (
                    agent_address is None or current_delegate == agent_address
                )
                allowance = self._usdc_allowance(web3, address)
                approval_required = (
                    self._settings.gtrade_auto_approve_usdc
                    and allowance < required_collateral_usd
                )
                if not delegate_ready and agent_address is not None:
                    delegation = self._set_delegate(
                        account,
                        address,
                        agent_address,
                    )
                    if delegation.status != "confirmed":
                        raise GTradeError("gTrade delegation transaction did not confirm")
                    self._remember_delegate(address, agent_address)
                    delegate_ready = True
                    gas_transactions.append(delegation)

                if approval_required:
                    prepared = self._prepare_tx_params(web3, address)
                    approval = self._approve_usdc(account, address, prepared=prepared)
                    if approval.status != "confirmed":
                        raise GTradeError("USDC approval transaction did not confirm")
                    allowance = Decimal(MAX_UINT256) / Decimal(10**6)
                    gas_transactions.append(approval)

        with self._cache_lock:
            self._allowance_cache[_checksum(address)] = allowance

        if not self._uses_platform_agent():
            self._warm_nonce(address)

        return {
            "wallet": address,
            "allowanceReady": allowance >= required_collateral_usd,
            "approvalSubmitted": approval is not None,
            "delegationReady": delegate_ready,
            "delegationSubmitted": delegation is not None,
            "executionAgent": agent_address,
            "gasTransactions": [_gas_tx_payload(tx) for tx in gas_transactions],
            "collateralBalanceUsd": str(collateral_balance),
            "elapsedMs": _elapsed_ms(started, time.perf_counter()),
        }

    def open_position(
        self,
        *,
        private_key_hex: str,
        pair: GTradePair,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote_payload: dict[str, Any],
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueOpenResult:
        started = time.perf_counter()
        account, address, web3 = self._account(private_key_hex)
        self._events.track_owner(address)
        self._events.start()
        approvals, prepared_tx = self._prepare_open_wallet(account, address, ticket_usd)
        prepared_at = time.perf_counter()
        price = Decimal(str(quote_payload.get("price") or self._current_price(pair, side)))
        trade = (
            address,
            0,
            pair.pair_index,
            int((leverage * Decimal(1000)).to_integral_value(rounding=ROUND_DOWN)),
            side == TradeSide.LONG,
            True,
            3,
            0,
            _usdc_units(ticket_usd),
            _price_units(price),
            _price_units(take_profit_price) if take_profit_price and take_profit_price > 0 else 0,
            _price_units(stop_loss_price) if stop_loss_price and stop_loss_price > 0 else 0,
            False,
            0,
            0,
        )
        fn = self._trading(web3).functions.openTrade(trade, self._settings.gtrade_slippage_bps, ZERO_ADDRESS)
        listen_since = time.time()
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="gtrade-open-confirm") as executor:
            position_future = executor.submit(
                self._wait_for_position,
                address=address,
                pair_index=pair.pair_index,
                present=True,
                timeout_seconds=self._settings.gtrade_open_wait_seconds,
                since=listen_since,
            )
            tx = self._send_trading_action(
                trader_account=account,
                trader_address=address,
                fn=fn,
                label="open",
                gas=self._settings.gtrade_fixed_open_gas,
                prepared=prepared_tx,
                on_transaction_prepared=on_transaction_prepared,
            )
            balance_future = executor.submit(
                self._usdc_balance,
                web3,
                address,
                max(0, (tx.block_number or 1) - 1),
            )
            position_wait = position_future.result()
            try:
                account_balance_before = balance_future.result()
            except Exception:
                account_balance_before = None
        position = position_wait.get("position")
        venue_position_id = _venue_position_id(pair.pair_index, position)
        entry = _position_entry_price(position) or price
        confirmed_stop_loss = _position_stop_loss_price(position) or stop_loss_price
        confirmed_take_profit = _position_take_profit_price(position) or take_profit_price
        confirmed_liquidation = (
            _event_detail_price(position_wait, "liquidationPrice")
            or _decimal_or_none(quote_payload.get("liquidationPrice"))
        )
        opened_at = _position_opened_at(position) or datetime.now(UTC)
        return VenueOpenResult(
            status="open" if position else "pending_execution",
            tx=tx,
            venue_position_id=venue_position_id,
            entry_price=entry,
            liquidation_price=confirmed_liquidation,
            stop_loss_price=confirmed_stop_loss,
            take_profit_price=confirmed_take_profit,
            opened_at=opened_at if position else None,
            account_balance_before_usd=account_balance_before,
            payload={
                "approvals": [approval.payload for approval in approvals],
                "gasTransactions": [
                    _gas_tx_payload(approval) for approval in approvals
                ],
                "accountBalanceBeforeOpenUsd": str(account_balance_before),
                "positionWait": position_wait,
                "position": position,
                "quotePayload": quote_payload,
                "timingMs": {
                    "walletPreparation": _elapsed_ms(started, prepared_at),
                    "transaction": tx.payload.get("timingMs", {}).get("total"),
                    "venueConfirmation": position_wait.get("elapsedMs"),
                    "total": _elapsed_ms(started),
                },
            },
        )

    def close_position(
        self,
        *,
        private_key_hex: str,
        pair: GTradePair,
        side: TradeSide,
        venue_position_id: str | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueCloseResult:
        started = time.perf_counter()
        account, address, web3 = self._account(private_key_hex)
        self._events.track_owner(address)
        self._events.start()
        position_index = self._resolve_position_index(address, pair.pair_index, venue_position_id)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="gtrade-close-prepare") as executor:
            price_future = executor.submit(
                self._current_price,
                pair,
                TradeSide.SHORT if side == TradeSide.LONG else TradeSide.LONG,
            )
            tx_params_future = (
                None
                if self._uses_platform_agent()
                else executor.submit(self._prepare_tx_params_with_lock, web3, address)
            )
            price = price_future.result()
            prepared_tx = tx_params_future.result() if tx_params_future else None
        prepared_at = time.perf_counter()
        fn = self._trading(web3).functions.closeTradeMarket(position_index, _price_units(price))
        listen_since = time.time()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="gtrade-close-confirm") as executor:
            position_future = executor.submit(
                self._wait_for_position,
                address=address,
                pair_index=pair.pair_index,
                present=False,
                timeout_seconds=self._settings.gtrade_close_wait_seconds,
                position_index=position_index,
                since=listen_since,
            )
            tx = self._send_trading_action(
                trader_account=account,
                trader_address=address,
                fn=fn,
                label="close",
                gas=self._settings.gtrade_fixed_close_gas,
                prepared=prepared_tx,
                on_transaction_prepared=on_transaction_prepared,
            )
            position_wait = position_future.result()
        closed = position_wait.get("observedPresent") is False and not position_wait.get("timedOut")
        venue_realized_pnl_usd, close_cashflow_usd = _close_event_financials(position_wait)
        return VenueCloseResult(
            status="closed" if closed else "pending_execution",
            tx=tx,
            closed_at=datetime.now(UTC) if closed else None,
            venue_realized_pnl_usd=venue_realized_pnl_usd,
            account_balance_after_usd=None,
            close_cashflow_usd=close_cashflow_usd,
            payload={
                "positionWait": position_wait,
                "positionIndex": position_index,
                "expectedClosePrice": str(price),
                "venueRealizedPnlUsd": (
                    str(venue_realized_pnl_usd) if venue_realized_pnl_usd is not None else None
                ),
                "closeCashflowUsd": str(close_cashflow_usd) if close_cashflow_usd is not None else None,
                "timingMs": {
                    "preparation": _elapsed_ms(started, prepared_at),
                    "transaction": tx.payload.get("timingMs", {}).get("total"),
                    "venueConfirmation": position_wait.get("elapsedMs"),
                    "total": _elapsed_ms(started),
                },
            },
        )

    def collateral_balance_usd(self, private_key_hex: str) -> Decimal:
        _, address, web3 = self._account(private_key_hex)
        return self._usdc_balance(web3, address)

    def execution_agent_address(self) -> str | None:
        if not self._uses_platform_agent():
            return None
        return _checksum(self._agent().address)

    def _account(self, private_key_hex: str):
        Account, Web3 = _web3_imports()
        key = private_key_hex.strip()
        account = Account.from_key(key if key.startswith("0x") else f"0x{key}")
        address = Web3.to_checksum_address(account.address)
        return account, address, self._web3()

    def _agent(self):
        Account, _ = _web3_imports()
        key = self._settings.platform_gas_wallet_private_key.strip()
        if not key:
            raise GTradeError(
                "PLATFORM_GAS_WALLET_PRIVATE_KEY is required for platform-agent execution"
            )
        return Account.from_key(key if key.startswith("0x") else f"0x{key}")

    def _uses_platform_agent(self) -> bool:
        return self._settings.gas_payer_mode.strip().lower() == "platform_agent"

    def _web3(self):
        if self._read_web3 is not None:
            return self._read_web3
        _, Web3 = _web3_imports()
        if not self._settings.arb_rpc_url:
            raise GTradeError("ARB_RPC_URL is required for real gTrade execution")
        web3 = Web3(Web3.HTTPProvider(self._settings.arb_rpc_url, request_kwargs={"timeout": 20}))
        if not web3.is_connected():
            raise GTradeError("could not connect to ARB_RPC_URL")
        chain_id = int(web3.eth.chain_id)
        if chain_id != self._settings.arb_chain_id:
            raise GTradeError(f"RPC chain_id {chain_id}, expected {self._settings.arb_chain_id}")
        self._read_web3 = web3
        return web3

    def _sequencer(self):
        if self._sequencer_web3 is not None:
            return self._sequencer_web3
        _, Web3 = _web3_imports()
        self._sequencer_web3 = Web3(
            Web3.HTTPProvider(DIRECT_SEQUENCER_URL, request_kwargs={"timeout": 8})
        )
        return self._sequencer_web3

    def _trading(self, web3: Any) -> Any:
        if self._trading_contract is None:
            _, Web3 = _web3_imports()
            self._trading_contract = web3.eth.contract(
                address=Web3.to_checksum_address(self._settings.gtrade_diamond_address),
                abi=TRADING_ABI,
            )
        return self._trading_contract

    def _usdc(self, web3: Any) -> Any:
        if self._usdc_contract is None:
            _, Web3 = _web3_imports()
            self._usdc_contract = web3.eth.contract(
                address=Web3.to_checksum_address(self._settings.gtrade_usdc_address),
                abi=ERC20_ABI,
            )
        return self._usdc_contract

    def _prepare_open_wallet(
        self,
        account: Any,
        address: str,
        ticket_usd: Decimal,
    ) -> tuple[list[VenueTxResult], tuple[int, dict[str, int]] | None]:
        if self._uses_platform_agent():
            with self._cache_lock:
                known_allowance = self._allowance_cache.get(_checksum(address))
            if known_allowance is not None and known_allowance < ticket_usd:
                raise GTradeError(
                    "user wallet allowance is not prepared for delegated execution"
                )
            return [], None

        with self._wallet_lock(address):
            web3 = self._web3()
            cached_allowance = self._cached_allowance(address)
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="gtrade-wallet-read") as executor:
                allowance_future = (
                    executor.submit(self._usdc_allowance, web3, address)
                    if self._settings.gtrade_auto_approve_usdc and cached_allowance < ticket_usd
                    else None
                )
                tx_params_future = (
                    None
                    if self._uses_platform_agent()
                    else executor.submit(self._prepare_tx_params, web3, address)
                )
                allowance = allowance_future.result() if allowance_future is not None else cached_allowance
                prepared_tx = tx_params_future.result() if tx_params_future else None

            approvals: list[VenueTxResult] = []
            if self._settings.gtrade_auto_approve_usdc and allowance < ticket_usd:
                if self._uses_platform_agent():
                    raise GTradeError(
                        "user wallet allowance is not prepared for delegated execution"
                    )
                prepared_approval = prepared_tx or self._prepare_tx_params(web3, address)
                approval = self._approve_usdc(
                    account,
                    address,
                    prepared=prepared_approval,
                )
                if approval.status != "confirmed":
                    raise GTradeError("USDC approval transaction did not confirm")
                approvals.append(approval)
                self._remember_allowance(address, Decimal(MAX_UINT256) / Decimal(10**6))
                prepared_tx = None
            elif allowance > 0:
                self._remember_allowance(address, allowance)
            return approvals, prepared_tx

    def _approve_usdc(
        self,
        account: Any,
        address: str,
        *,
        prepared: tuple[int, dict[str, int]],
    ) -> VenueTxResult:
        _, Web3 = _web3_imports()
        web3 = self._web3()
        spender = Web3.to_checksum_address(self._settings.gtrade_diamond_address)
        fn = self._usdc(web3).functions.approve(spender, MAX_UINT256)
        return self._send(
            account,
            address,
            fn,
            label="approve",
            gas=self._settings.gtrade_fixed_approve_gas,
            prepared=prepared,
        )

    def _set_delegate(
        self,
        account: Any,
        address: str,
        agent_address: str,
    ) -> VenueTxResult:
        web3 = self._web3()
        fn = self._trading(web3).functions.setTradingDelegate(
            _checksum(agent_address)
        )
        return self._send(
            account,
            address,
            fn,
            label="set_delegate",
            gas=self._settings.gtrade_fixed_delegate_gas,
        )

    def _current_delegate(self, trader_address: str) -> str:
        cached = self._cached_delegate(trader_address)
        if cached is not None:
            return cached
        current = _checksum(
            self._trading(self._web3())
            .functions.getTradingDelegate(_checksum(trader_address))
            .call()
        )
        self._remember_delegate(trader_address, current)
        return current

    def _cached_delegate(self, trader_address: str) -> str | None:
        trader = _checksum(trader_address)
        with self._cache_lock:
            cached = self._delegate_cache.get(trader)
            if cached is None:
                return None
            delegate, expires_at = cached
            if time.monotonic() >= expires_at:
                self._delegate_cache.pop(trader, None)
                return None
            return delegate

    def _remember_delegate(
        self,
        trader_address: str,
        delegate_address: str,
    ) -> None:
        with self._cache_lock:
            self._delegate_cache[_checksum(trader_address)] = (
                _checksum(delegate_address),
                time.monotonic()
                + max(0.0, self._settings.gtrade_delegate_cache_seconds),
            )

    def _usdc_allowance(self, web3: Any, address: str) -> Decimal:
        _, Web3 = _web3_imports()
        spender = Web3.to_checksum_address(self._settings.gtrade_diamond_address)
        return Decimal(self._usdc(web3).functions.allowance(address, spender).call()) / Decimal(10**6)

    def _cached_allowance(self, address: str) -> Decimal:
        with self._cache_lock:
            return self._allowance_cache.get(_checksum(address), Decimal(0))

    def _remember_allowance(self, address: str, allowance: Decimal) -> None:
        with self._cache_lock:
            self._allowance_cache[_checksum(address)] = allowance

    def _wallet_lock(self, address: str) -> RLock:
        return EVM_NONCES.sender_lock(address)

    def _send_trading_action(
        self,
        *,
        trader_account: Any,
        trader_address: str,
        fn: Any,
        label: str,
        gas: int,
        prepared: tuple[int, dict[str, int]] | None,
        on_transaction_prepared: TransactionPreparedHandler | None,
    ) -> VenueTxResult:
        if not self._uses_platform_agent():
            return self._send(
                trader_account,
                trader_address,
                fn,
                label=label,
                gas=gas,
                prepared=prepared,
                on_transaction_prepared=on_transaction_prepared,
            )

        agent = self._agent()
        agent_address = _checksum(agent.address)
        known_delegate = self._cached_delegate(trader_address)
        if known_delegate is not None and known_delegate != agent_address:
            raise GTradeError("user wallet is not delegated to the TICK execution agent")
        call_data = bytes.fromhex(fn._encode_transaction_data().removeprefix("0x"))
        delegated_fn = self._trading(self._web3()).functions.delegatedTradingAction(
            _checksum(trader_address),
            call_data,
        )
        delegated_gas = (
            self._settings.gtrade_delegated_open_gas
            if label == "open"
            else self._settings.gtrade_delegated_close_gas
        )
        result = self._send(
            agent,
            agent_address,
            delegated_fn,
            label=label,
            gas=delegated_gas,
            prepared=None,
            on_transaction_prepared=on_transaction_prepared,
        )
        return VenueTxResult(
            status=result.status,
            tx_hash=result.tx_hash,
            nonce=result.nonce,
            block_number=result.block_number,
            gas_used=result.gas_used,
            effective_gas_price=result.effective_gas_price,
            payload={
                **result.payload,
                "delegated": True,
                "trader": _checksum(trader_address),
                "gasPayer": agent_address,
            },
        )

    def _send(
        self,
        account: Any,
        address: str,
        fn: Any,
        *,
        label: str,
        gas: int,
        prepared: tuple[int, dict[str, int]] | None = None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueTxResult:
        web3 = self._web3()
        started = time.perf_counter()
        with self._wallet_lock(address):
            lock_acquired_at = time.perf_counter()
            nonce, fee_params = prepared or self._prepare_tx_params(web3, address)
            tx = fn.build_transaction(
                {
                    "from": address,
                    "chainId": self._settings.arb_chain_id,
                    "nonce": nonce,
                    "gas": int(Decimal(gas) * Decimal("1.25")),
                    **fee_params,
                }
            )
            built_at = time.perf_counter()
            signed = account.sign_transaction(tx)
            raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
            _, Web3 = _web3_imports()
            precomputed_tx_hash = Web3.keccak(raw_tx).hex()
            signed_at = time.perf_counter()
            if on_transaction_prepared is not None:
                on_transaction_prepared(precomputed_tx_hash, int(tx["nonce"]))
            persisted_at = time.perf_counter()
            try:
                race = self._broadcaster.broadcast(
                    raw_transaction=raw_tx,
                    expected_tx_hash=precomputed_tx_hash,
                    primary_web3=web3,
                    sequencer_web3=self._sequencer(),
                )
            except Exception:
                self._invalidate_nonce(address)
                self._invalidate_fee_cache()
                raise
            broadcast_at = time.perf_counter()
        receipt = web3.eth.wait_for_transaction_receipt(
            precomputed_tx_hash,
            timeout=90,
            poll_latency=0.2,
        )
        receipt_at = time.perf_counter()
        race.wait_for_outcomes(timeout=0.02)
        status = int(receipt.status)
        return VenueTxResult(
            status="confirmed" if status == 1 else "reverted",
            tx_hash=precomputed_tx_hash,
            nonce=int(tx["nonce"]),
            block_number=int(receipt.blockNumber),
            gas_used=int(receipt.gasUsed),
            effective_gas_price=int(getattr(receipt, "effectiveGasPrice", 0) or receipt.get("effectiveGasPrice", 0) or 0),
            payload={
                "label": label,
                "status": status,
                "precomputedTxHash": precomputed_tx_hash,
                "gasPayer": _checksum(address),
                "writeTransport": race.winner,
                "broadcast": race.payload(),
                "timingMs": {
                    "senderQueue": _elapsed_ms(started, lock_acquired_at),
                    "build": _elapsed_ms(lock_acquired_at, built_at),
                    "sign": _elapsed_ms(built_at, signed_at),
                    "persistPrepared": _elapsed_ms(signed_at, persisted_at),
                    "broadcastToResponse": _elapsed_ms(persisted_at, broadcast_at),
                    "receipt": _elapsed_ms(broadcast_at, receipt_at),
                    "total": _elapsed_ms(started, receipt_at),
                },
            },
        )

    def _prepare_tx_params(self, web3: Any, address: str) -> tuple[int, dict[str, int]]:
        return self._next_nonce(web3, address), self._fee_params(web3)

    def _prepare_tx_params_with_lock(
        self,
        web3: Any,
        address: str,
    ) -> tuple[int, dict[str, int]]:
        with self._wallet_lock(address):
            return self._prepare_tx_params(web3, address)

    def _next_nonce(self, web3: Any, address: str) -> int:
        return EVM_NONCES.reserve(web3, _checksum(address))

    def _warm_nonce(self, address: str) -> None:
        EVM_NONCES.warm(self._web3(), _checksum(address))

    def _invalidate_nonce(self, address: str) -> None:
        EVM_NONCES.invalidate(_checksum(address))

    def _fee_params(self, web3: Any) -> dict[str, int]:
        now = time.monotonic()
        with self._cache_lock:
            if self._fee_cache and now - self._fee_cache[0] <= FEE_CACHE_MAX_AGE_SECONDS:
                return dict(self._fee_cache[1])
        params = _fee_params(web3)
        with self._cache_lock:
            self._fee_cache = (now, dict(params))
        return params

    def _invalidate_fee_cache(self) -> None:
        with self._cache_lock:
            self._fee_cache = None

    def _run_fee_warmer(self) -> None:
        while not self._fee_stop.is_set():
            try:
                web3 = self._web3()
                params = _fee_params(web3)
                with self._cache_lock:
                    self._fee_cache = (time.monotonic(), dict(params))
            except Exception as exc:
                LOGGER.warning("Could not refresh Arbitrum fee cache: %s", exc)
            self._fee_stop.wait(1.0)

    def _warm_sequencer_connection(self) -> None:
        started = time.perf_counter()
        try:
            # The write-only endpoint rejects this harmless read after transport
            # handling, which is enough to establish and retain its TLS session.
            self._sequencer().provider.make_request("eth_chainId", [])
            LOGGER.debug(
                "Arbitrum sequencer transport warmed elapsedMs=%.1f",
                _elapsed_ms(started, time.perf_counter()),
            )
        except Exception as exc:
            LOGGER.warning("Could not warm Arbitrum sequencer transport: %s", exc)

    def _run_sequencer_keepalive(self) -> None:
        while not self._sequencer_stop.wait(SEQUENCER_KEEPALIVE_SECONDS):
            self._warm_sequencer_connection()

    def _current_price(self, pair: GTradePair, side: TradeSide) -> Decimal:
        live = self._public.price(pair.pair)
        return Decimal(str(live["ask"] if side == TradeSide.LONG else live["bid"]))

    def _wait_for_position(
        self,
        *,
        address: str,
        pair_index: int,
        present: bool,
        timeout_seconds: float,
        since: float,
        position_index: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gtrade-confirm")
        futures = {
            executor.submit(
                self._events.wait_for_position_event,
                owner=address,
                pair_index=pair_index,
                present=present,
                since=since,
                timeout_seconds=timeout_seconds,
                position_index=position_index,
            ): "gtrade_event_stream",
            executor.submit(
                self._wait_for_position_rest,
                address=address,
                pair_index=pair_index,
                present=present,
                timeout_seconds=timeout_seconds,
                position_index=position_index,
                delay_seconds=REST_FALLBACK_DELAY_SECONDS,
            ): "gains_open_trades_rest",
        }
        results: dict[str, dict[str, Any]] = {}
        try:
            for future in as_completed(futures, timeout=timeout_seconds + 0.5):
                source = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    results[source] = {
                        "source": source,
                        "timedOut": True,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    continue
                results[source] = result
                if not result.get("timedOut"):
                    winner = str(result.get("source") or source)
                    return {
                        **result,
                        "race": {
                            "winner": winner,
                            "elapsedMs": _elapsed_ms(started),
                            "restFallbackDelayMs": REST_FALLBACK_DELAY_SECONDS * 1000,
                        },
                    }
        except TimeoutError:
            pass
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return {
            "source": "venue_confirmation_race",
            "position": None,
            "elapsedMs": _elapsed_ms(started),
            "targetPresent": present,
            "observedPresent": None,
            "timedOut": True,
            "race": {
                "winner": None,
                "elapsedMs": _elapsed_ms(started),
                "restFallbackDelayMs": REST_FALLBACK_DELAY_SECONDS * 1000,
                "results": results,
            },
        }

    def _wait_for_position_rest(
        self,
        *,
        address: str,
        pair_index: int,
        present: bool,
        timeout_seconds: float,
        position_index: int | None,
        delay_seconds: float,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        if delay_seconds:
            time.sleep(delay_seconds)
        deadline = time.monotonic() + timeout_seconds
        polls: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            poll_started = time.perf_counter()
            positions = [
                item
                for item in self._open_trades(address)
                if int(item.get("trade", {}).get("pairIndex", -1)) == pair_index
                and (position_index is None or int(item.get("trade", {}).get("index", -1)) == position_index)
            ]
            polls.append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "offsetMs": _elapsed_ms(started),
                    "readMs": _elapsed_ms(poll_started),
                    "positionCount": len(positions),
                }
            )
            if bool(positions) is present:
                return {
                    "source": "gains_open_trades_rest",
                    "position": positions[0] if positions else None,
                    "elapsedMs": _elapsed_ms(started),
                    "polls": polls,
                    "pollCount": len(polls),
                    "targetPresent": present,
                    "observedPresent": bool(positions),
                    "timedOut": False,
                }
            time.sleep(self._settings.gtrade_rest_poll_seconds)
        return {
            "source": "gains_open_trades_rest",
            "position": None,
            "elapsedMs": _elapsed_ms(started),
            "polls": polls,
            "pollCount": len(polls),
            "targetPresent": present,
            "observedPresent": None,
            "timedOut": True,
        }

    def _open_trades(self, address: str) -> list[dict[str, Any]]:
        response = self._rest_session.get(
            f"{self._settings.gtrade_backend_url}/open-trades/{address}",
            timeout=4,
            headers={"user-agent": "tick-mvp/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise GTradeError("open-trades returned non-list JSON")
        return payload

    def _resolve_position_index(self, address: str, pair_index: int, venue_position_id: str | None) -> int:
        parsed = _parse_venue_position_id(venue_position_id)
        if parsed is not None:
            return parsed
        positions = [
            item
            for item in self._open_trades(address)
            if int(item.get("trade", {}).get("pairIndex", -1)) == pair_index
        ]
        if not positions:
            raise GTradeError("no open position visible for close")
        return int(positions[0]["trade"]["index"])

    def _usdc_balance(
        self,
        web3: Any,
        address: str,
        block_identifier: int | str = "latest",
    ) -> Decimal:
        units = self._usdc(web3).functions.balanceOf(address).call(block_identifier=block_identifier)
        return Decimal(units) / Decimal(10**6)


def _web3_imports():
    from eth_account import Account
    from web3 import Web3

    return Account, Web3


def _fee_params(web3: Any) -> dict[str, int]:
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    priority = 10_000_000
    return {
        "maxFeePerGas": int(Decimal(base_fee) * Decimal("2.0")) + priority,
        "maxPriorityFeePerGas": priority,
    }


def _checksum(address: str) -> str:
    _, Web3 = _web3_imports()
    return Web3.to_checksum_address(address)


def _usdc_units(value: Decimal) -> int:
    return int((value * Decimal(10**6)).to_integral_value(rounding=ROUND_DOWN))


def _price_units(value: Decimal) -> int:
    return int((value * Decimal(10**10)).to_integral_value(rounding=ROUND_UP))


def _venue_position_id(pair_index: int, position: dict[str, Any] | None) -> str | None:
    if not position:
        return None
    raw_index = position.get("trade", {}).get("index")
    if raw_index is None:
        return None
    return f"{pair_index}:{int(raw_index)}"


def _parse_venue_position_id(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r":(\d+)$", value)
    if match:
        return int(match.group(1))
    try:
        return int(value)
    except ValueError:
        return None


def _position_entry_price(position: dict[str, Any] | None) -> Decimal | None:
    if not position:
        return None
    value = position.get("trade", {}).get("openPrice")
    if value is None:
        return None
    return Decimal(str(value)) / Decimal(10**10)


def _position_stop_loss_price(position: dict[str, Any] | None) -> Decimal | None:
    if not position:
        return None
    value = position.get("trade", {}).get("sl")
    if not value:
        return None
    return Decimal(str(value)) / Decimal(10**10)


def _position_take_profit_price(position: dict[str, Any] | None) -> Decimal | None:
    if not position:
        return None
    value = position.get("trade", {}).get("tp")
    if not value:
        return None
    return Decimal(str(value)) / Decimal(10**10)


def _event_detail_price(position_wait: dict[str, Any], field: str) -> Decimal | None:
    value = ((position_wait.get("event") or {}).get("details") or {}).get(field)
    if value is None:
        return None
    return Decimal(str(value)) / Decimal(10**10)


def _position_opened_at(position: dict[str, Any] | None) -> datetime | None:
    if not position:
        return None
    value = position.get("tradeInfo", {}).get("lastOiUpdateTs")
    if not value:
        return None
    return datetime.fromtimestamp(int(value), UTC)


def _close_event_financials(position_wait: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
    event = position_wait.get("event") or {}
    details = event.get("details") or {}
    trade = (event.get("position") or {}).get("trade") or {}
    amount_sent = details.get("amountSentToTrader")
    collateral_amount = trade.get("collateralAmount")
    collateral_index = trade.get("collateralIndex")
    if amount_sent is None or collateral_amount is None or int(collateral_index or -1) != 3:
        return None, None
    close_cashflow = Decimal(str(amount_sent)) / Decimal(10**6)
    opened_collateral = Decimal(str(collateral_amount)) / Decimal(10**6)
    return close_cashflow - opened_collateral, close_cashflow


def _gas_tx_payload(tx: VenueTxResult) -> dict[str, Any]:
    return {
        "txHash": tx.tx_hash,
        "gasUsed": tx.gas_used,
        "effectiveGasPrice": tx.effective_gas_price,
        "operation": tx.payload.get("label") or "wallet",
        "gasPayer": tx.payload.get("gasPayer"),
    }


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _elapsed_ms(started: float, finished: float | None = None) -> float:
    return round(((finished or time.perf_counter()) - started) * 1000, 1)
