from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

import avantis_trader_sdk
import websockets
from avantis_trader_sdk import TraderClient
from avantis_trader_sdk.types import LazerPriceFeedResponse, TradeInput
from eth_account import Account
from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import MismatchedABI, TransactionNotFound

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import PositionStatus, TradeSide
from tick_mvp.venues.avantis.catalog import AvantisPair, market_pair, parse_zfp_catalog
from tick_mvp.venues.base import (
    TerminalPositionEvent,
    TransactionPreparedHandler,
    VenueError,
    VenueTxResult,
)


LOGGER = logging.getLogger("tick.avantis")
MAX_UINT256 = 2**256 - 1
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


class AvantisError(VenueError):
    pass


class AvantisAmbiguousExecution(AvantisError):
    def __init__(self, message: str, *, tx_hash: str) -> None:
        super().__init__(message)
        self.tx_hash = tx_hash


@dataclass(frozen=True, slots=True)
class PriceObservation:
    price: Decimal
    source_timestamp_ms: int
    received_at: float


@dataclass(frozen=True, slots=True)
class AvantisExecution:
    tx: VenueTxResult
    callback: dict[str, Any]
    account_balance_before_usd: Decimal | None = None


@dataclass(frozen=True, slots=True)
class FeeEnvelope:
    execution_fee_wei: int
    max_priority_fee_per_gas: int
    max_fee_per_gas: int


class AvantisRuntime:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_lock = threading.Lock()
        self._start_error: BaseException | None = None
        self._client: TraderClient | None = None
        self._catalog: dict[str, AvantisPair] = {}
        self._prices: dict[int, PriceObservation] = {}
        self._price_task: asyncio.Task[Any] | None = None
        self._fee_task: asyncio.Task[Any] | None = None
        self._callback_task: asyncio.Task[Any] | None = None
        self._callback_ready: asyncio.Event | None = None
        self._callback_contract: Any = None
        self._callback_address: str | None = None
        self._callback_waiters: list[
            tuple[Callable[[dict[str, Any]], bool], float, asyncio.Future[dict[str, Any]]]
        ] = []
        self._callback_history: deque[dict[str, Any]] = deque(maxlen=512)
        self._terminal_events: queue.Queue[TerminalPositionEvent] = queue.Queue()
        self._service_lock: asyncio.Lock | None = None
        self._wallet_locks: dict[str, asyncio.Lock] = {}
        self._service_next_nonce: int | None = None
        self._fee_envelope: FeeEnvelope | None = None
        self._last_catalog_at = 0.0
        self._last_callback_at: float | None = None
        self._callback_error: str | None = None

    def start(self) -> None:
        with self._start_lock:
            if self._thread and self._thread.is_alive():
                return
            self._ready.clear()
            self._start_error = None
            self._thread = threading.Thread(
                target=self._run_loop,
                name="avantis-runtime",
                daemon=True,
            )
            self._thread.start()
        if not self._ready.wait(timeout=30):
            raise AvantisError("Avantis runtime did not start")
        if self._start_error is not None:
            raise AvantisError(f"Avantis runtime failed: {self._start_error}")

    def stop(self) -> None:
        loop = self._loop
        if loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), loop).result(timeout=5)
        except Exception:
            LOGGER.exception("Avantis runtime shutdown failed")
        loop.call_soon_threadsafe(loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._thread = None
        self._loop = None

    def health(self) -> dict[str, Any]:
        self.start()
        return self._call(self._health())

    def catalog(self, *, force: bool = False) -> dict[str, AvantisPair]:
        self.start()
        return self._call(self._catalog_snapshot(force=force))

    def prices(self) -> dict[int, PriceObservation]:
        self.start()
        return self._call(self._price_snapshot())

    def price(self, pair: AvantisPair, *, max_age_seconds: float = 3.0) -> Decimal:
        self.start()
        return self._call(self._fresh_price(pair, max_age_seconds=max_age_seconds))

    def balance(self, private_key_hex: str) -> Decimal:
        self.start()
        return self._call(self._balance(private_key_hex))

    def wallet_status(
        self,
        private_key_hex: str,
        required_collateral_usd: Decimal,
    ) -> dict[str, Any]:
        self.start()
        return self._call(
            self._wallet_status(private_key_hex, required_collateral_usd)
        )

    def prepare_wallet(
        self,
        private_key_hex: str,
        required_collateral_usd: Decimal,
    ) -> dict[str, Any]:
        self.start()
        return self._call(
            self._prepare_wallet(private_key_hex, required_collateral_usd),
            timeout=120,
        )

    def open_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None,
    ) -> AvantisExecution:
        self.start()
        return self._call(
            self._open_position(
                private_key_hex=private_key_hex,
                market=market,
                side=side,
                ticket_usd=ticket_usd,
                leverage=leverage,
                stop_loss_price=stop_loss_price,
                take_profit_price=take_profit_price,
                on_transaction_prepared=on_transaction_prepared,
            ),
            timeout=max(60, self._settings.avantis_open_wait_seconds + 20),
        )

    def close_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        venue_position_id: str | None,
        on_transaction_prepared: TransactionPreparedHandler | None,
    ) -> AvantisExecution:
        self.start()
        return self._call(
            self._close_position(
                private_key_hex=private_key_hex,
                market=market,
                venue_position_id=venue_position_id,
                on_transaction_prepared=on_transaction_prepared,
            ),
            timeout=max(60, self._settings.avantis_close_wait_seconds + 20),
        )

    def recover(
        self,
        *,
        private_key_hex: str,
        market: str,
        venue_position_id: str | None,
        tx_hash: str,
        signed_raw_transaction: str | None,
    ) -> dict[str, Any]:
        self.start()
        return self._call(
            self._recover(
                private_key_hex=private_key_hex,
                market=market,
                venue_position_id=venue_position_id,
                tx_hash=tx_hash,
                signed_raw_transaction=signed_raw_transaction,
            ),
            timeout=30,
        )

    def next_terminal_event(
        self,
        timeout: float = 0.25,
    ) -> TerminalPositionEvent | None:
        try:
            return self._terminal_events.get(timeout=timeout)
        except queue.Empty:
            return None

    def collateral_balance_for_owner(self, owner: str) -> Decimal:
        self.start()
        return self._call(self._balance_for_owner(owner))

    def latest_block(self) -> int:
        self.start()
        return self._call(self._latest_block())

    def recover_terminal_events(self, *, from_block: int) -> list[TerminalPositionEvent]:
        self.start()
        return self._call(self._recover_terminal_events(from_block=from_block), timeout=90)

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._initialize())
        except BaseException as exc:
            self._start_error = exc
        finally:
            self._ready.set()
        if self._start_error is None:
            loop.run_forever()
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    async def _initialize(self) -> None:
        if not self._settings.base_rpc_url:
            raise AvantisError("BASE_RPC_URL is not configured")
        self._client = TraderClient(self._settings.base_rpc_url)
        if await self._client.get_chain_id() != self._settings.base_chain_id:
            raise AvantisError("BASE_RPC_URL is not Base mainnet")
        if self._settings.platform_gas_wallet_private_key:
            self._client.set_local_signer(
                self._settings.platform_gas_wallet_private_key
            )
        self._service_lock = asyncio.Lock()
        self._callback_ready = asyncio.Event()
        await self._refresh_catalog()
        await self._seed_prices()
        storage = self._client.contracts["TradingStorage"]
        self._callback_address = Web3.to_checksum_address(
            await storage.functions.callbacks().call()
        )
        self._callback_contract = self._client.async_web3.eth.contract(
            address=self._callback_address,
            abi=_callbacks_abi(),
        )
        self._price_task = asyncio.create_task(self._listen_prices())
        self._fee_task = asyncio.create_task(self._warm_fees_forever())
        if self._settings.base_wss_url:
            self._callback_task = asyncio.create_task(self._listen_callbacks())
            try:
                await asyncio.wait_for(self._callback_ready.wait(), timeout=8)
            except TimeoutError:
                LOGGER.warning("Avantis callback WSS did not become ready during startup")

    async def _shutdown(self) -> None:
        tasks = [self._price_task, self._fee_task, self._callback_task]
        for task in tasks:
            if task:
                task.cancel()
        await asyncio.gather(*(task for task in tasks if task), return_exceptions=True)

    def _call(self, coroutine, *, timeout: float = 45):
        loop = self._loop
        if loop is None:
            raise AvantisError("Avantis runtime is not running")
        return asyncio.run_coroutine_threadsafe(coroutine, loop).result(timeout=timeout)

    @property
    def _sdk(self) -> TraderClient:
        if self._client is None:
            raise AvantisError("Avantis client is not initialized")
        return self._client

    async def _health(self) -> dict[str, Any]:
        now = time.time()
        prices = list(self._prices.values())
        newest = max((item.received_at for item in prices), default=None)
        return {
            "venue": "avantis",
            "chainId": self._settings.base_chain_id,
            "markets": len(self._catalog),
            "priceAgeMs": (now - newest) * 1000 if newest is not None else None,
            "callbackAddress": self._callback_address,
            "callbackConnected": bool(self._callback_ready and self._callback_ready.is_set()),
            "lastCallbackAgeMs": (
                (now - self._last_callback_at) * 1000
                if self._last_callback_at is not None
                else None
            ),
            "callbackError": self._callback_error,
            "serviceWallet": self._service_address_or_none(),
        }

    async def _catalog_snapshot(self, *, force: bool) -> dict[str, AvantisPair]:
        if force or time.monotonic() - self._last_catalog_at > self._settings.avantis_catalog_ttl_seconds:
            await self._refresh_catalog()
        return dict(self._catalog)

    async def _refresh_catalog(self) -> None:
        payload = await self._sdk.pairs_cache.get_info_from_socket(force_update=True)
        catalog = parse_zfp_catalog(payload)
        if not catalog:
            raise AvantisError("Avantis returned no zero-fee-loss markets")
        self._catalog = catalog
        self._last_catalog_at = time.monotonic()

    async def _seed_prices(self) -> None:
        feed_ids = sorted({pair.lazer_feed_id for pair in self._catalog.values()})
        response = await self._sdk.feed_client.get_latest_lazer_price(feed_ids)
        self._record_prices(response)

    async def _listen_prices(self) -> None:
        while True:
            try:
                feed_ids = sorted({pair.lazer_feed_id for pair in self._catalog.values()})
                await self._sdk.feed_client.listen_for_lazer_price_updates(
                    feed_ids,
                    self._record_prices,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Avantis price stream disconnected")
                await asyncio.sleep(1)

    def _record_prices(self, response: LazerPriceFeedResponse) -> None:
        received_at = time.time()
        for feed in response.price_feeds:
            self._prices[int(feed.price_feed_id)] = PriceObservation(
                price=Decimal(str(feed.converted_price)),
                source_timestamp_ms=int(response.timestamp_ms),
                received_at=received_at,
            )

    async def _price_snapshot(self) -> dict[int, PriceObservation]:
        return dict(self._prices)

    async def _fresh_price(
        self,
        pair: AvantisPair,
        *,
        max_age_seconds: float,
    ) -> Decimal:
        observation = self._prices.get(pair.lazer_feed_id)
        if observation is None or time.time() - observation.received_at > max_age_seconds:
            response = await self._sdk.feed_client.get_latest_lazer_price(
                [pair.lazer_feed_id]
            )
            self._record_prices(response)
            observation = self._prices.get(pair.lazer_feed_id)
        if observation is None:
            raise AvantisError(f"no Avantis price for {pair.market}")
        return observation.price

    async def _warm_fees_forever(self) -> None:
        while True:
            try:
                self._fee_envelope = await self._read_fee_envelope()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Avantis fee warmup failed")
            await asyncio.sleep(5)

    async def _read_fee_envelope(self) -> FeeEnvelope:
        block, execution_fee = await asyncio.gather(
            self._sdk.async_web3.eth.get_block("latest"),
            self._sdk.trade.get_trade_execution_fee(),
        )
        try:
            tip = int(await self._sdk.async_web3.eth.max_priority_fee)
        except Exception:
            tip = 1_000_000
        base_fee = int(block.get("baseFeePerGas") or 0)
        return FeeEnvelope(
            execution_fee_wei=int(execution_fee),
            max_priority_fee_per_gas=tip,
            max_fee_per_gas=base_fee * 2 + tip,
        )

    async def _fees(self) -> FeeEnvelope:
        if self._fee_envelope is None:
            self._fee_envelope = await self._read_fee_envelope()
        return self._fee_envelope

    async def _listen_callbacks(self) -> None:
        while True:
            try:
                await self._callback_connection()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._callback_error = f"{type(exc).__name__}: {exc}"
                if self._callback_ready:
                    self._callback_ready.clear()
                await asyncio.sleep(1)

    async def _callback_connection(self) -> None:
        if not self._callback_address:
            raise AvantisError("Avantis callback address is unavailable")
        websocket = await websockets.connect(
            self._settings.base_wss_url,
            ping_interval=20,
            ping_timeout=20,
            max_size=2**20,
        )
        try:
            selected = None
            for subscription_type in ("pendingLogs", "logs"):
                await websocket.send(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "eth_subscribe",
                            "params": [
                                subscription_type,
                                {"address": self._callback_address},
                            ],
                        }
                    )
                )
                response = json.loads(await asyncio.wait_for(websocket.recv(), timeout=8))
                if response.get("result"):
                    selected = subscription_type
                    break
            if selected is None:
                raise AvantisError("Base WSS rejected Avantis log subscriptions")
            self._callback_error = None
            if self._callback_ready:
                self._callback_ready.set()
            async for raw_message in websocket:
                message = json.loads(raw_message)
                if message.get("method") != "eth_subscription":
                    continue
                event = self._decode_callback(message["params"]["result"], selected)
                if event is not None:
                    self._publish_callback(event)
        finally:
            await websocket.close()

    def _decode_callback(
        self,
        raw_log: dict[str, Any],
        subscription_type: str,
    ) -> dict[str, Any] | None:
        log = _web3_log(raw_log)
        for name in ("MarketExecuted", "LimitExecuted", "MarketOpenCanceled"):
            try:
                decoded = getattr(self._callback_contract.events, name)().process_log(log)
            except (MismatchedABI, KeyError, TypeError, ValueError):
                continue
            return {
                "event": name,
                "args": _normalize(decoded["args"]),
                "transactionHash": _hex(decoded.get("transactionHash")),
                "blockNumber": decoded.get("blockNumber"),
                "blockHash": _hex(decoded.get("blockHash")),
                "logIndex": decoded.get("logIndex"),
                "receivedAt": time.time(),
                "receivedUtc": datetime.now(UTC).isoformat(),
                "source": f"base_{subscription_type}",
            }
        return None

    def _publish_callback(self, event: dict[str, Any]) -> None:
        self._callback_history.append(event)
        self._last_callback_at = float(event["receivedAt"])
        terminal = _terminal_event(event)
        if terminal is not None:
            self._terminal_events.put(terminal)
        remaining = []
        for predicate, after, future in self._callback_waiters:
            if future.done():
                continue
            try:
                matches = float(event["receivedAt"]) >= after and predicate(event)
            except Exception:
                matches = False
            if matches:
                future.set_result(event)
            else:
                remaining.append((predicate, after, future))
        self._callback_waiters = remaining

    async def _wait_callback(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        after: float,
        timeout: float,
    ) -> dict[str, Any]:
        for event in reversed(self._callback_history):
            if float(event["receivedAt"]) >= after and predicate(event):
                return event
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        waiter = (predicate, after, future)
        self._callback_waiters.append(waiter)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            if waiter in self._callback_waiters:
                self._callback_waiters.remove(waiter)

    async def _balance(self, private_key_hex: str) -> Decimal:
        owner = Account.from_key(private_key_hex).address
        return await self._balance_for_owner(owner)

    async def _balance_for_owner(self, owner: str) -> Decimal:
        return Decimal(str(await self._sdk.get_usdc_balance(owner)))

    async def _latest_block(self) -> int:
        return int(await self._sdk.async_web3.eth.block_number)

    async def _recover_terminal_events(
        self,
        *,
        from_block: int,
    ) -> list[TerminalPositionEvent]:
        if not self._callback_address:
            raise AvantisError("Avantis callback address is unavailable")
        latest = await self._latest_block()
        recovered: list[TerminalPositionEvent] = []
        block_timestamps: dict[int, float] = {}
        for start in range(max(0, from_block), latest + 1, 2_000):
            end = min(latest, start + 1_999)
            logs = await self._sdk.async_web3.eth.get_logs(
                {
                    "fromBlock": start,
                    "toBlock": end,
                    "address": self._callback_address,
                }
            )
            for row in logs:
                block_number = int(row["blockNumber"])
                observed = block_timestamps.get(block_number)
                if observed is None:
                    block = await self._sdk.async_web3.eth.get_block(block_number)
                    observed = float(block["timestamp"])
                    block_timestamps[block_number] = observed
                event = self._decode_callback(
                    _rpc_log(row),
                    "recovery",
                )
                if event is None:
                    continue
                event["receivedAt"] = observed
                event["receivedUtc"] = datetime.fromtimestamp(observed, UTC).isoformat()
                terminal = _terminal_event(event)
                if terminal is not None:
                    recovered.append(terminal)
        return recovered

    async def _wallet_status(
        self,
        private_key_hex: str,
        required_collateral_usd: Decimal,
    ) -> dict[str, Any]:
        owner = Account.from_key(private_key_hex).address
        service = self._require_service_address()
        balance, allowance, delegate, native = await asyncio.gather(
            self._sdk.get_usdc_balance(owner),
            self._sdk.get_usdc_allowance_for_trading(owner),
            self._sdk.trade.get_delegate(owner),
            self._sdk.get_balance(owner),
        )
        return {
            "owner": owner,
            "serviceWallet": service,
            "collateralBalanceUsd": str(balance),
            "nativeEth": str(native),
            "allowanceUsd": str(allowance),
            "allowanceReady": Decimal(str(allowance)) >= required_collateral_usd,
            "delegationReady": str(delegate).lower() == service.lower(),
            "delegate": delegate,
            "gasTransactions": [],
        }

    async def _prepare_wallet(
        self,
        private_key_hex: str,
        required_collateral_usd: Decimal,
    ) -> dict[str, Any]:
        owner = Account.from_key(private_key_hex).address
        lock = self._wallet_locks.setdefault(owner.lower(), asyncio.Lock())
        async with lock:
            state = await self._wallet_status(private_key_hex, required_collateral_usd)
            transactions: list[dict[str, Any]] = []
            needs_allowance = not bool(state["allowanceReady"])
            needs_delegate = not bool(state["delegationReady"])
            if not needs_allowance and not needs_delegate:
                return state
            native = Decimal(str(state["nativeEth"]))
            target = self._settings.avantis_setup_target_eth
            if native < target:
                topup = await self._send_service_transfer(owner, target - native)
                transactions.append(_gas_record(topup, "avantis_setup_topup"))
            nonce = int(await self._sdk.async_web3.eth.get_transaction_count(owner, "pending"))
            if needs_allowance:
                usdc = self._sdk.contracts["USDC"]
                storage = self._sdk.contracts["TradingStorage"]
                data = usdc.encodeABI(
                    fn_name="approve",
                    args=[storage.address, MAX_UINT256],
                )
                result = await self._send_user_transaction(
                    private_key_hex,
                    nonce=nonce,
                    to=usdc.address,
                    data=data,
                    operation="avantis_approve",
                )
                transactions.append(_gas_record(result, "avantis_approve"))
                nonce += 1
            if needs_delegate:
                trading = self._sdk.contracts["Trading"]
                data = trading.encodeABI(
                    fn_name="setDelegate",
                    args=[self._require_service_address()],
                )
                result = await self._send_user_transaction(
                    private_key_hex,
                    nonce=nonce,
                    to=trading.address,
                    data=data,
                    operation="avantis_delegate",
                )
                transactions.append(_gas_record(result, "avantis_delegate"))
            final = await self._wallet_status(private_key_hex, required_collateral_usd)
            return {**final, "gasTransactions": transactions}

    async def _open_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        stop_loss_price: Decimal | None,
        take_profit_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None,
    ) -> AvantisExecution:
        owner = Account.from_key(private_key_hex).address
        catalog = await self._catalog_snapshot(force=False)
        pair = market_pair(catalog, market)
        price = await self._fresh_price(pair, max_age_seconds=1.5)
        storage = self._sdk.contracts["TradingStorage"]
        open_count, pending_open, pending_close, trade_index, balance = await asyncio.gather(
            storage.functions.openTradesCount(owner, pair.pair_index).call(),
            storage.functions.pendingMarketOpenCount(owner, pair.pair_index).call(),
            storage.functions.pendingMarketCloseCount(owner, pair.pair_index).call(),
            storage.functions.firstEmptyTradeIndex(owner, pair.pair_index).call(),
            self._sdk.get_usdc_balance(owner),
        )
        if int(open_count) or int(pending_open) or int(pending_close):
            raise AvantisError("Avantis wallet already has an active or pending trade")
        trade = TradeInput(
            trader=owner,
            pair_index=pair.pair_index,
            trade_index=int(trade_index),
            collateral_in_trade=float(ticket_usd),
            is_long=side == TradeSide.LONG,
            leverage=int(leverage),
            tp=float(take_profit_price or 0),
            sl=float(stop_loss_price or 0),
            timestamp=0,
        )
        trade.openPrice = int(price * Decimal(10**10))
        trading = self._sdk.contracts["Trading"]
        inner = trading.encodeABI(
            fn_name="openTrade",
            args=[
                trade.model_dump(),
                3,
                self._settings.avantis_slippage_percentage * 10**10,
            ],
        )
        data = trading.encodeABI(
            fn_name="delegatedAction",
            args=[owner, inner],
        )
        started = time.time()
        execution = await self._send_service_action(
            data=data,
            gas=self._settings.avantis_open_gas,
            callback_predicate=lambda event: _callback_matches(
                event,
                owner=owner,
                pair_index=pair.pair_index,
                trade_index=None,
                opening=True,
            ),
            callback_timeout=self._settings.avantis_open_wait_seconds,
            on_transaction_prepared=on_transaction_prepared,
            started=started,
        )
        callback = execution.callback
        if callback["event"] != "MarketExecuted":
            raise AvantisError(f"Avantis canceled the open: {callback['event']}")
        return AvantisExecution(
            tx=execution.tx,
            callback=callback,
            account_balance_before_usd=Decimal(str(balance)),
        )

    async def _close_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        venue_position_id: str | None,
        on_transaction_prepared: TransactionPreparedHandler | None,
    ) -> AvantisExecution:
        owner = Account.from_key(private_key_hex).address
        catalog = await self._catalog_snapshot(force=False)
        pair = market_pair(catalog, market)
        trade_index = _position_index(venue_position_id)
        trade = await self._find_trade(owner, pair.pair_index, trade_index)
        if trade is None or trade.trade is None:
            raise AvantisError("Avantis position is no longer open")
        authoritative_index = int(trade.trade.trade_index)
        collateral = Decimal(str(trade.trade.open_collateral))
        trading = self._sdk.contracts["Trading"]
        inner = trading.encodeABI(
            fn_name="closeTradeMarket",
            args=[pair.pair_index, authoritative_index, int(collateral * Decimal(10**6))],
        )
        data = trading.encodeABI(
            fn_name="delegatedAction",
            args=[owner, inner],
        )
        started = time.time()
        return await self._send_service_action(
            data=data,
            gas=self._settings.avantis_close_gas,
            callback_predicate=lambda event: _callback_matches(
                event,
                owner=owner,
                pair_index=pair.pair_index,
                trade_index=authoritative_index,
                opening=False,
            ),
            callback_timeout=self._settings.avantis_close_wait_seconds,
            on_transaction_prepared=on_transaction_prepared,
            started=started,
        )

    async def _send_service_action(
        self,
        *,
        data: str,
        gas: int,
        callback_predicate: Callable[[dict[str, Any]], bool],
        callback_timeout: float,
        on_transaction_prepared: TransactionPreparedHandler | None,
        started: float,
    ) -> AvantisExecution:
        service = self._require_service_address()
        fees = await self._fees()
        trading = self._sdk.contracts["Trading"]
        callback_task = asyncio.create_task(
            self._wait_callback(
                callback_predicate,
                after=started,
                timeout=callback_timeout,
            )
        )
        try:
            tx, raw, tx_hash, nonce = await self._submit_service_transaction(
                to=trading.address,
                data=data,
                gas=gas,
                value=fees.execution_fee_wei,
                on_transaction_prepared=on_transaction_prepared,
            )
            receipt_task = asyncio.create_task(
                self._sdk.async_web3.eth.wait_for_transaction_receipt(
                    tx_hash,
                    timeout=45,
                    poll_latency=0.05,
                )
            )
            try:
                receipt, callback = await asyncio.gather(receipt_task, callback_task)
            except TimeoutError as exc:
                raise AvantisAmbiguousExecution(
                    "Avantis initiation landed but callback is not yet resolved",
                    tx_hash=tx_hash,
                ) from exc
            if int(receipt["status"]) != 1:
                raise AvantisError("Avantis initiation transaction reverted")
            tx_result = _tx_result(
                receipt,
                tx_hash=tx_hash,
                nonce=nonce,
                value_wei=int(tx["value"]),
                gas_payer=service,
                callback=callback,
            )
            return AvantisExecution(tx=tx_result, callback=callback)
        except BaseException:
            if not callback_task.done():
                callback_task.cancel()
            raise

    async def _submit_service_transaction(
        self,
        *,
        to: str,
        data: str,
        gas: int,
        value: int,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> tuple[dict[str, Any], bytes, str, int]:
        if self._service_lock is None:
            raise AvantisError("Avantis service nonce lock is unavailable")
        async with self._service_lock:
            service = self._require_service_address()
            chain_nonce = int(
                await self._sdk.async_web3.eth.get_transaction_count(service, "pending")
            )
            nonce = max(chain_nonce, self._service_next_nonce or chain_nonce)
            self._service_next_nonce = nonce + 1
            fees = await self._fees()
            tx = {
                "type": 2,
                "chainId": self._settings.base_chain_id,
                "from": service,
                "to": Web3.to_checksum_address(to),
                "nonce": nonce,
                "gas": gas,
                "value": value,
                "data": data,
                "maxPriorityFeePerGas": fees.max_priority_fee_per_gas,
                "maxFeePerGas": fees.max_fee_per_gas,
            }
            signed = Account.sign_transaction(
                tx,
                self._settings.platform_gas_wallet_private_key,
            )
            raw = bytes(getattr(signed, "raw_transaction", None) or signed.rawTransaction)
            tx_hash = _normalize_hash(Web3.keccak(raw).hex())
            if on_transaction_prepared:
                on_transaction_prepared(tx_hash, nonce, f"0x{raw.hex()}")
            try:
                await self._sdk.async_web3.eth.send_raw_transaction(raw)
            except Exception as exc:
                if not await self._transaction_exists(tx_hash):
                    raise AvantisAmbiguousExecution(
                        f"Avantis broadcast is ambiguous: {exc}",
                        tx_hash=tx_hash,
                    ) from exc
            return tx, raw, tx_hash, nonce

    async def _send_service_transfer(
        self,
        recipient: str,
        amount: Decimal,
    ) -> VenueTxResult:
        tx, raw, tx_hash, nonce = await self._submit_service_transaction(
            to=recipient,
            data="0x",
            gas=30_000,
            value=int(amount * Decimal(10**18)),
        )
        receipt = await self._sdk.async_web3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=45,
            poll_latency=0.05,
        )
        if int(receipt["status"]) != 1:
            raise AvantisError("Base setup funding transaction reverted")
        return _tx_result(
            receipt,
            tx_hash=tx_hash,
            nonce=nonce,
            value_wei=int(tx["value"]),
            gas_payer=self._require_service_address(),
            callback=None,
        )

    async def _send_user_transaction(
        self,
        private_key_hex: str,
        *,
        nonce: int,
        to: str,
        data: str,
        operation: str,
    ) -> VenueTxResult:
        account = Account.from_key(private_key_hex)
        fees = await self._fees()
        tx = {
            "type": 2,
            "chainId": self._settings.base_chain_id,
            "from": account.address,
            "to": Web3.to_checksum_address(to),
            "nonce": nonce,
            "gas": self._settings.avantis_setup_gas,
            "value": 0,
            "data": data,
            "maxPriorityFeePerGas": fees.max_priority_fee_per_gas,
            "maxFeePerGas": fees.max_fee_per_gas,
        }
        signed = Account.sign_transaction(tx, private_key_hex)
        raw = bytes(getattr(signed, "raw_transaction", None) or signed.rawTransaction)
        tx_hash = _normalize_hash(Web3.keccak(raw).hex())
        await self._sdk.async_web3.eth.send_raw_transaction(raw)
        receipt = await self._sdk.async_web3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=45,
            poll_latency=0.05,
        )
        if int(receipt["status"]) != 1:
            raise AvantisError(f"{operation} transaction reverted")
        return _tx_result(
            receipt,
            tx_hash=tx_hash,
            nonce=nonce,
            value_wei=0,
            gas_payer=account.address,
            callback=None,
        )

    async def _find_trade(
        self,
        owner: str,
        pair_index: int,
        trade_index: int | None,
    ):
        # The Avantis API can lag the contract immediately after MarketExecuted.
        # Close decisions must use on-chain storage first so a stale indexer
        # cannot make a live position appear absent.
        trades, _ = await self._sdk.trade.get_trades(owner, use_api=False)
        if not trades:
            trades, _ = await self._sdk.trade.get_trades(owner, use_api=True)
        for candidate in trades:
            trade = candidate.trade
            if trade is None or int(trade.pair_index) != pair_index:
                continue
            if trade_index is None or int(trade.trade_index) == trade_index:
                return candidate
        return None

    async def _recover(
        self,
        *,
        private_key_hex: str,
        market: str,
        venue_position_id: str | None,
        tx_hash: str,
        signed_raw_transaction: str | None,
    ) -> dict[str, Any]:
        if signed_raw_transaction and not await self._transaction_exists(tx_hash):
            try:
                await self._sdk.async_web3.eth.send_raw_transaction(
                    bytes.fromhex(signed_raw_transaction.removeprefix("0x"))
                )
            except Exception:
                pass
        try:
            receipt = await self._sdk.async_web3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return {"tx": None, "position": None, "source": "base_rpc"}
        transaction = await self._sdk.async_web3.eth.get_transaction(tx_hash)
        tx = _tx_result(
            receipt,
            tx_hash=tx_hash,
            nonce=int(transaction["nonce"]),
            value_wei=int(transaction.get("value") or 0),
            gas_payer=str(transaction.get("from") or ""),
            callback=None,
        )
        if int(receipt["status"]) != 1:
            return {"tx": tx, "position": None, "source": "base_receipt"}
        owner = Account.from_key(private_key_hex).address
        pair = market_pair(await self._catalog_snapshot(force=False), market)
        index = _position_index(venue_position_id)
        trade = await self._find_trade(owner, pair.pair_index, index)
        if trade is None or trade.trade is None:
            return {"tx": tx, "position": None, "source": "avantis_snapshot"}
        row = trade.trade
        return {
            "tx": tx,
            "position": row.model_dump(),
            "venuePositionId": f"{pair.pair_index}:{row.trade_index}",
            "entryPrice": str(row.open_price),
            "stopLossPrice": str(row.sl) if row.sl else None,
            "takeProfitPrice": str(row.tp) if row.tp else None,
            "openedAt": datetime.fromtimestamp(int(row.timestamp), UTC),
            "source": "avantis_snapshot",
        }

    async def _transaction_exists(self, tx_hash: str) -> bool:
        try:
            await self._sdk.async_web3.eth.get_transaction(tx_hash)
            return True
        except Exception:
            return False

    def _service_address_or_none(self) -> str | None:
        key = self._settings.platform_gas_wallet_private_key
        return Account.from_key(key).address if key else None

    def _require_service_address(self) -> str:
        address = self._service_address_or_none()
        if address is None:
            raise AvantisError("PLATFORM_GAS_WALLET_PRIVATE_KEY is not configured")
        return address


def _callbacks_abi() -> list[dict[str, Any]]:
    path = (
        Path(avantis_trader_sdk.__file__).resolve().parent
        / "abis"
        / "TradingCallbacks.sol"
        / "TradingCallbacks.json"
    )
    return json.loads(path.read_text())["abi"]


def _web3_log(raw: dict[str, Any]) -> dict[str, Any]:
    def optional_int(value: Any) -> int | None:
        return int(value, 16) if isinstance(value, str) else value

    return {
        "address": Web3.to_checksum_address(raw["address"]),
        "topics": [HexBytes(topic) for topic in raw["topics"]],
        "data": HexBytes(raw["data"]),
        "blockNumber": optional_int(raw.get("blockNumber")),
        "transactionHash": HexBytes(raw["transactionHash"]) if raw.get("transactionHash") else None,
        "transactionIndex": optional_int(raw.get("transactionIndex")),
        "blockHash": HexBytes(raw["blockHash"]) if raw.get("blockHash") else None,
        "logIndex": optional_int(raw.get("logIndex")),
        "removed": bool(raw.get("removed", False)),
    }


def _rpc_log(row: Any) -> dict[str, Any]:
    return {
        "address": str(row["address"]),
        "topics": [_hex(value) for value in row["topics"]],
        "data": _hex(row["data"]),
        "blockNumber": hex(int(row["blockNumber"])),
        "transactionHash": _hex(row["transactionHash"]),
        "transactionIndex": hex(int(row["transactionIndex"])),
        "blockHash": _hex(row["blockHash"]),
        "logIndex": hex(int(row["logIndex"])),
        "removed": bool(row.get("removed", False)),
    }


def _normalize(value: Any) -> Any:
    if isinstance(value, bytes):
        return _hex(value)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _hex(value: Any) -> str | None:
    if value is None:
        return None
    encoded = value.hex() if hasattr(value, "hex") else str(value)
    return encoded if encoded.startswith("0x") else f"0x{encoded}"


def _normalize_hash(value: str) -> str:
    normalized = value.lower()
    return normalized if normalized.startswith("0x") else f"0x{normalized}"


def _position_index(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.rsplit(":", 1)[-1])
    except ValueError as exc:
        raise AvantisError(f"invalid Avantis position id: {value}") from exc


def _callback_matches(
    event: dict[str, Any],
    *,
    owner: str,
    pair_index: int,
    trade_index: int | None,
    opening: bool,
) -> bool:
    args = event.get("args") or {}
    trade = args.get("t") or {}
    trader = str(trade.get("trader") or args.get("trader") or "")
    if trader.lower() != owner.lower():
        return False
    if event.get("event") == "MarketOpenCanceled":
        return opening
    if event.get("event") != "MarketExecuted":
        return False
    if bool(args.get("open")) != opening:
        return False
    if int(trade.get("pairIndex", -1)) != pair_index:
        return False
    return trade_index is None or int(trade.get("index", -1)) == trade_index


def _terminal_event(event: dict[str, Any]) -> TerminalPositionEvent | None:
    args = event.get("args") or {}
    trade = args.get("t") or {}
    owner = str(trade.get("trader") or "").lower()
    pair_index = _int_or_none(trade.get("pairIndex"))
    trade_index = _int_or_none(trade.get("index"))
    if not owner or pair_index is None or trade_index is None:
        return None

    name = str(event.get("event") or "")
    if name == "MarketExecuted":
        if bool(args.get("open")):
            return None
        reason = "manual_close"
    elif name == "LimitExecuted":
        order_type = _int_or_none(args.get("orderType"))
        reason = {0: "take_profit", 1: "stop_loss", 2: "liquidation"}.get(
            order_type
        )
        if reason is None:
            return None
    else:
        return None

    received_at = float(event.get("receivedAt") or time.time())
    returned = _scaled_usdc(args.get("usdcSentToTrader"))
    return TerminalPositionEvent(
        venue="avantis",
        owner=owner,
        venue_position_id=f"{pair_index}:{trade_index}",
        status=(
            PositionStatus.LIQUIDATED
            if reason == "liquidation"
            else PositionStatus.CLOSED
        ),
        reason=reason,
        source=str(event.get("source") or "base_logs"),
        observed_at=datetime.fromtimestamp(received_at, UTC),
        transaction_hash=_string_or_none(event.get("transactionHash")),
        block_number=_int_or_none(event.get("blockNumber")),
        log_index=_int_or_none(event.get("logIndex")),
        returned_collateral_usd=returned,
        payload=event,
    )


def _scaled_usdc(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) / Decimal(10**6)
    except (ValueError, TypeError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _string_or_none(value: Any) -> str | None:
    return str(value) if value else None


def _tx_result(
    receipt: Any,
    *,
    tx_hash: str,
    nonce: int,
    value_wei: int,
    gas_payer: str,
    callback: dict[str, Any] | None,
) -> VenueTxResult:
    status = int(receipt["status"])
    payload = {
        "receiptStatus": status,
        "gasPayer": gas_payer,
        "valueWei": value_wei,
    }
    if callback is not None:
        payload["callback"] = callback
        payload["callbackTxHash"] = callback.get("transactionHash")
        payload["callbackBlockNumber"] = callback.get("blockNumber")
        payload["callbackLogIndex"] = callback.get("logIndex")
        payload["detectionSource"] = callback.get("source")
    return VenueTxResult(
        status="confirmed" if status == 1 else "reverted",
        tx_hash=_normalize_hash(tx_hash),
        nonce=nonce,
        block_number=int(receipt["blockNumber"]),
        gas_used=int(receipt["gasUsed"]),
        effective_gas_price=int(receipt.get("effectiveGasPrice") or 0),
        payload=payload,
    )


def _gas_record(result: VenueTxResult, operation: str) -> dict[str, Any]:
    return {
        "txHash": result.tx_hash,
        "gasUsed": result.gas_used,
        "effectiveGasPrice": result.effective_gas_price,
        "operation": operation,
        "gasPayer": result.payload.get("gasPayer"),
    }
