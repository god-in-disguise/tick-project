from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from threading import RLock
from typing import Any

import requests

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.base import VenueCloseResult, VenueOpenResult, VenueTxResult
from tick_mvp.venues.gtrade.constants import ERC20_ABI, MAX_UINT256, TRADING_ABI, ZERO_ADDRESS
from tick_mvp.venues.gtrade.public import GTradeError, GTradePair


class GTradeWalletExecutor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._read_web3 = None
        self._trading_contract = None
        self._usdc_contract = None
        self._cache_lock = RLock()
        self._nonce_cache: dict[str, int] = {}
        self._fee_cache: tuple[float, dict[str, int]] | None = None

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
    ) -> VenueOpenResult:
        account, address, web3 = self._account(private_key_hex)
        approvals: list[dict[str, Any]] = []
        if self._settings.gtrade_auto_approve_usdc:
            approval = self._ensure_usdc_allowance(account, address, ticket_usd)
            if approval is not None:
                if approval.status != "confirmed":
                    raise GTradeError("USDC approval transaction did not confirm")
                approvals.append(approval.payload)
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
            0,
            _price_units(stop_loss_price) if stop_loss_price and stop_loss_price > 0 else 0,
            False,
            0,
            0,
        )
        fn = self._trading(web3).functions.openTrade(trade, self._settings.gtrade_slippage_bps, ZERO_ADDRESS)
        tx = self._send(account, address, fn, label="open", gas=self._settings.gtrade_fixed_open_gas)
        position_wait = self._wait_for_position(
            address=address,
            pair_index=pair.pair_index,
            present=True,
            timeout_seconds=self._settings.gtrade_open_wait_seconds,
        )
        position = position_wait.get("position")
        venue_position_id = _venue_position_id(pair.pair_index, position)
        entry = _position_entry_price(position) or price
        opened_at = _position_opened_at(position) or datetime.now(UTC)
        return VenueOpenResult(
            status="open" if position else "pending_execution",
            tx=tx,
            venue_position_id=venue_position_id,
            entry_price=entry,
            liquidation_price=_decimal_or_none(quote_payload.get("liquidationPrice")),
            stop_loss_price=stop_loss_price,
            opened_at=opened_at if position else None,
            payload={
                "approvals": approvals,
                "positionWait": position_wait,
                "position": position,
                "quotePayload": quote_payload,
            },
        )

    def close_position(
        self,
        *,
        private_key_hex: str,
        pair: GTradePair,
        side: TradeSide,
        venue_position_id: str | None,
    ) -> VenueCloseResult:
        account, address, web3 = self._account(private_key_hex)
        before_usdc = self._usdc_balance(web3, address)
        position_index = self._resolve_position_index(address, pair.pair_index, venue_position_id)
        price = self._current_price(pair, TradeSide.SHORT if side == TradeSide.LONG else TradeSide.LONG)
        fn = self._trading(web3).functions.closeTradeMarket(position_index, _price_units(price))
        tx = self._send(account, address, fn, label="close", gas=self._settings.gtrade_fixed_close_gas)
        position_wait = self._wait_for_position(
            address=address,
            pair_index=pair.pair_index,
            present=False,
            timeout_seconds=self._settings.gtrade_close_wait_seconds,
            position_index=position_index,
        )
        closed = position_wait.get("observedPresent") is False and not position_wait.get("timedOut")
        after_usdc = self._usdc_balance(web3, address) if closed else None
        wallet_delta = after_usdc - before_usdc if after_usdc is not None else None
        return VenueCloseResult(
            status="closed" if closed else "pending_execution",
            tx=tx,
            closed_at=datetime.now(UTC) if closed else None,
            venue_realized_pnl_usd=None,
            wallet_delta_usd=wallet_delta,
            payload={
                "positionWait": position_wait,
                "positionIndex": position_index,
                "expectedClosePrice": str(price),
                "walletUsdcBefore": str(before_usdc),
                "walletUsdcAfter": str(after_usdc) if after_usdc is not None else None,
            },
        )

    def _account(self, private_key_hex: str):
        Account, Web3 = _web3_imports()
        key = private_key_hex.strip()
        account = Account.from_key(key if key.startswith("0x") else f"0x{key}")
        address = Web3.to_checksum_address(account.address)
        return account, address, self._web3()

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

    def _ensure_usdc_allowance(self, account: Any, address: str, ticket_usd: Decimal) -> VenueTxResult | None:
        _, Web3 = _web3_imports()
        web3 = self._web3()
        usdc = self._usdc(web3)
        spender = Web3.to_checksum_address(self._settings.gtrade_diamond_address)
        allowance = Decimal(usdc.functions.allowance(address, spender).call()) / Decimal(10**6)
        if allowance >= ticket_usd:
            return None
        fn = usdc.functions.approve(spender, MAX_UINT256)
        return self._send(account, address, fn, label="approve", gas=self._settings.gtrade_fixed_approve_gas)

    def _send(self, account: Any, address: str, fn: Any, *, label: str, gas: int) -> VenueTxResult:
        web3 = self._web3()
        started = time.perf_counter()
        tx = fn.build_transaction(
            {
                "from": address,
                "chainId": self._settings.arb_chain_id,
                "nonce": self._next_nonce(web3, address),
                "gas": int(Decimal(gas) * Decimal("1.25")),
                **self._fee_params(web3),
            }
        )
        built_at = time.perf_counter()
        signed = account.sign_transaction(tx)
        raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        _, Web3 = _web3_imports()
        precomputed_tx_hash = Web3.keccak(raw_tx).hex()
        signed_at = time.perf_counter()
        try:
            tx_hash = web3.eth.send_raw_transaction(raw_tx)
        except Exception:
            self._invalidate_nonce(address)
            self._invalidate_fee_cache()
            raise
        broadcast_at = time.perf_counter()
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=90, poll_latency=0.2)
        receipt_at = time.perf_counter()
        status = int(receipt.status)
        return VenueTxResult(
            status="confirmed" if status == 1 else "reverted",
            tx_hash=tx_hash.hex(),
            nonce=int(tx["nonce"]),
            block_number=int(receipt.blockNumber),
            gas_used=int(receipt.gasUsed),
            effective_gas_price=int(getattr(receipt, "effectiveGasPrice", 0) or receipt.get("effectiveGasPrice", 0) or 0),
            payload={
                "label": label,
                "status": status,
                "precomputedTxHash": precomputed_tx_hash,
                "writeTransport": "primary_rpc",
                "broadcast": {"method": "eth_sendRawTransaction"},
                "timingMs": {
                    "build": _elapsed_ms(started, built_at),
                    "sign": _elapsed_ms(built_at, signed_at),
                    "broadcastToResponse": _elapsed_ms(signed_at, broadcast_at),
                    "receipt": _elapsed_ms(broadcast_at, receipt_at),
                    "total": _elapsed_ms(started, receipt_at),
                },
            },
        )

    def _next_nonce(self, web3: Any, address: str) -> int:
        checksum = _checksum(address)
        with self._cache_lock:
            cached = self._nonce_cache.get(checksum)
            if cached is not None:
                self._nonce_cache[checksum] = cached + 1
                return cached
        nonce = int(web3.eth.get_transaction_count(checksum, "pending"))
        with self._cache_lock:
            self._nonce_cache[checksum] = nonce + 1
        return nonce

    def _invalidate_nonce(self, address: str) -> None:
        with self._cache_lock:
            self._nonce_cache.pop(_checksum(address), None)

    def _fee_params(self, web3: Any) -> dict[str, int]:
        now = time.monotonic()
        with self._cache_lock:
            if self._fee_cache and now - self._fee_cache[0] <= 1.0:
                return dict(self._fee_cache[1])
        params = _fee_params(web3)
        with self._cache_lock:
            self._fee_cache = (now, dict(params))
        return params

    def _invalidate_fee_cache(self) -> None:
        with self._cache_lock:
            self._fee_cache = None

    def _current_price(self, pair: GTradePair, side: TradeSide) -> Decimal:
        from tick_mvp.venues.gtrade.public import GTradePublicClient

        live = GTradePublicClient(self._settings).price(pair.pair)
        return Decimal(str(live["ask"] if side == TradeSide.LONG else live["bid"]))

    def _wait_for_position(
        self,
        *,
        address: str,
        pair_index: int,
        present: bool,
        timeout_seconds: float,
        position_index: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
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
        response = requests.get(
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

    def _usdc_balance(self, web3: Any, address: str) -> Decimal:
        return Decimal(self._usdc(web3).functions.balanceOf(address).call()) / Decimal(10**6)


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


def _position_opened_at(position: dict[str, Any] | None) -> datetime | None:
    if not position:
        return None
    value = position.get("tradeInfo", {}).get("lastOiUpdateTs")
    if not value:
        return None
    return datetime.fromtimestamp(int(value), UTC)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _elapsed_ms(started: float, finished: float | None = None) -> float:
    return round(((finished or time.perf_counter()) - started) * 1000, 1)
