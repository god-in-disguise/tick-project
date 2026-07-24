from __future__ import annotations

import time
from decimal import Decimal
from time import perf_counter
from typing import Any

from web3 import Web3

from .ostium_client import (
    CLOSE_MAX_ATTEMPTS,
    DEFAULT_COLLATERAL,
    DEFAULT_LEVERAGE,
    DEFAULT_PAIR,
    DEFAULT_SLIPPAGE_BPS,
    ERC20_ABI,
    EXECUTION_LOCK,
    LOGGER,
    MAX_UINT256,
    OPEN_MAX_ATTEMPTS,
    TRADING_STORAGE,
    USDC,
    OstiumError,
    _balances,
    _cancel_reason,
    _close_fn,
    _dec,
    _execution_status,
    _find_pair,
    _load,
    _max_leverage,
    _normalize_pair,
    _open_fn,
    _open_trades,
    _pair_key,
    _parse_usdc,
    _position_public,
    _prices,
    _public_orders,
    _send,
    _wait_for_order,
    _wait_for_position,
    _wait_until_closed,
)
from .ostium_rpc import wait_for_close_callback, wait_for_open_callback


def open_trade(
    side: str,
    leverage_value: float | None = None,
    pair_name: str | None = None,
    collateral_value: Decimal | float | None = None,
    *,
    execution_price: Decimal | None = None,
    preflighted: bool = False,
    wait: bool = False,
) -> dict[str, Any]:
    if side not in {"long", "short"}:
        raise OstiumError("side must be long or short")
    leverage = Decimal(str(leverage_value)) if leverage_value is not None else DEFAULT_LEVERAGE
    if leverage not in {Decimal("25"), Decimal("50"), Decimal("100")}:
        raise OstiumError("leverage must be one of 25, 50, or 100")
    collateral = _dec(collateral_value) if collateral_value is not None else DEFAULT_COLLATERAL
    if collateral <= 0:
        raise OstiumError("collateral must be positive")
    requested_pair = _normalize_pair(pair_name or DEFAULT_PAIR)
    with EXECUTION_LOCK:
        account, address, web3 = _load()
        pair = _find_pair(requested_pair)
        pair_name = _pair_key(pair)
        max_leverage = _max_leverage(pair)
        if max_leverage > 0 and leverage > max_leverage:
            raise OstiumError(f"{pair_name} max leverage is {max_leverage}x")

        price_data = _price_payload(execution_price) if execution_price is not None else _prices(fresh=True)[pair_name]
        existing = None if preflighted else next(
            (pos for pos in _open_trades(address) if _pair_key(pos["pair"]) == pair_name),
            None,
        )
        if existing:
            return {
                "action": "open",
                "status": "already_open",
                "side": side,
                "pair": pair_name,
                "price": float(price_data["mid"]),
                "leverage": float(leverage),
                "approval": None,
                "tx": None,
                "orders": [],
                "position": _position_public(existing, price_data),
            }

        if not price_data.get("isMarketOpen", True):
            raise OstiumError(f"{pair_name} market is closed")
        approval_tx = None
        if not preflighted:
            balances = _balances(web3, address)
            if balances["usdc"] < _parse_usdc(collateral):
                raise OstiumError("USDC balance too low")
            min_allowance = _parse_usdc(collateral + Decimal("1"))
            if balances["allowance"] < min_allowance:
                usdc = web3.eth.contract(address=Web3.to_checksum_address(USDC), abi=ERC20_ABI)
                approve_fn = usdc.functions.approve(Web3.to_checksum_address(TRADING_STORAGE), MAX_UINT256)
                approval_tx = _send(web3, account, address, approve_fn, "approveBeforeOpen", wait_receipt=True)
                balances = _balances(web3, address)
                if balances["allowance"] < min_allowance:
                    raise OstiumError("allowance approval did not settle")

        attempts: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        for attempt in range(1, OPEN_MAX_ATTEMPTS + 1):
            if attempt > 1 or execution_price is None:
                price_data = _prices(fresh=True)[pair_name]
            if not price_data.get("isMarketOpen", True):
                raise OstiumError(f"{pair_name} market is closed")
            price = execution_price if attempt == 1 and execution_price is not None else Decimal(
                str(price_data["ask" if side == "long" else "bid"])
            )
            fn = _open_fn(web3, address, pair, price, collateral, leverage, side)
            started = perf_counter()
            LOGGER.info("open attempt %s/%s %s %s %sx price=%s", attempt, OPEN_MAX_ATTEMPTS, pair_name, side, leverage, price)
            tx = _send(web3, account, address, fn, "openTrade", wait_receipt=True)
            confirmation = None
            if wait:
                orders = _wait_for_order(tx["txHash"])
                indexed_position = _wait_for_position(address, pair_name)
                status = _execution_status(orders, indexed_position)
                tx["totalWithIndexing"] = round(perf_counter() - started, 3)
            else:
                orders = []
                callback = wait_for_open_callback(web3, tx["txHash"], pair_name)
                indexed_position = callback.get("position")
                status = str(callback["status"])
                confirmation = callback.get("confirmation")
                tx["totalWithConfirmation"] = round(perf_counter() - started, 3)
            public_orders = _public_orders(orders)
            cancel_reason = str((callback if not wait else {}).get("cancelReason") or _cancel_reason(orders))
            result = {
                "action": "open",
                "status": status,
                "attempt": attempt,
                "side": side,
                "pair": pair_name,
                "price": float(price),
                "ticketUsd": float(collateral),
                "leverage": float(leverage),
                "slippageBps": DEFAULT_SLIPPAGE_BPS,
                "approval": approval_tx,
                "tx": tx,
                "orders": public_orders,
                "position": (
                    _position_public(indexed_position, price_data)
                    if wait and indexed_position
                    else indexed_position
                ),
                "confirmation": confirmation,
            }
            attempts.append(
                {
                    "attempt": attempt,
                    "status": status,
                    "txHash": tx.get("txHash"),
                    "cancelReason": cancel_reason,
                    "timing": tx.get("timing"),
                }
            )
            result["attempts"] = attempts
            last_result = result
            LOGGER.info("open attempt result %s %s tx=%s reason=%s", pair_name, status, tx.get("txHash"), cancel_reason)
            if indexed_position is not None:
                return result
            if status == "cancelled" and attempt < OPEN_MAX_ATTEMPTS:
                time.sleep(0.8)
                continue
            if status in {"pending_execution", "pending_index"}:
                return result

        reason = cancel_reason if "cancel_reason" in locals() else _cancel_reason(orders if "orders" in locals() else [])
        if last_result and last_result.get("status") in {"pending_execution", "pending_index"}:
            return last_result
        raise OstiumError(f"open did not create a position after {OPEN_MAX_ATTEMPTS} attempts: {reason or 'not indexed'}")


def close_trade(
    pair_name: str = DEFAULT_PAIR,
    *,
    position: dict[str, Any] | None = None,
    execution_price: Decimal | None = None,
    preflighted: bool = False,
    wait: bool = False,
) -> dict[str, Any]:
    requested_pair = _normalize_pair(pair_name)
    with EXECUTION_LOCK:
        account, address, web3 = _load()
        pair = _find_pair(requested_pair)
        pair_name = _pair_key(pair)
        price_data = _price_payload(execution_price) if execution_price is not None else _prices(fresh=True)[pair_name]
        known_position = _contract_position(position, pair_name)
        matching = [known_position] if known_position else [
            pos for pos in _open_trades(address) if _pair_key(pos["pair"]) == pair_name
        ]
        if not matching:
            return {
                "action": "close",
                "status": "already_closed",
                "pair": pair_name,
                "price": float(price_data["mid"]),
                "approval": None,
                "tx": None,
                "orders": [],
                "closed": True,
            }
        approval_tx = None
        if not preflighted:
            balances = _balances(web3, address)
            if balances["allowance"] < _parse_usdc(Decimal("1")):
                usdc = web3.eth.contract(address=Web3.to_checksum_address(USDC), abi=ERC20_ABI)
                approve_fn = usdc.functions.approve(Web3.to_checksum_address(TRADING_STORAGE), MAX_UINT256)
                approval_tx = _send(web3, account, address, approve_fn, "approveBeforeClose", wait_receipt=True)
                balances = _balances(web3, address)
                if balances["allowance"] < _parse_usdc(Decimal("1")):
                    raise OstiumError("allowance approval did not settle")

        attempts: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        for attempt in range(1, CLOSE_MAX_ATTEMPTS + 1):
            if attempt > 1 or execution_price is None:
                price_data = _prices(fresh=True)[pair_name]
            matching = [known_position] if known_position else [
                pos for pos in _open_trades(address) if _pair_key(pos["pair"]) == pair_name
            ]
            if not matching:
                return {
                    "action": "close",
                    "status": "already_closed",
                    "pair": pair_name,
                    "price": float(price_data["mid"]),
                    "approval": approval_tx,
                    "tx": None,
                    "orders": [],
                    "closed": True,
                    "attempts": attempts,
                }
            position = matching[0]
            price = execution_price if attempt == 1 and execution_price is not None else Decimal(
                str(price_data["bid" if position["isBuy"] else "ask"])
            )
            fn = _close_fn(web3, position, price)
            started = perf_counter()
            LOGGER.info("close attempt %s/%s %s price=%s", attempt, CLOSE_MAX_ATTEMPTS, pair_name, price)
            tx = _send(web3, account, address, fn, "closeTradeMarket", wait_receipt=True)
            confirmation = None
            fill_price = None
            if wait:
                orders = _wait_for_order(tx["txHash"])
                closed = _wait_until_closed(address, pair_name)
                status = _execution_status(orders, None, closed)
                tx["totalWithIndexing"] = round(perf_counter() - started, 3)
            else:
                orders = []
                callback = wait_for_close_callback(web3, tx["txHash"])
                closed = bool(callback.get("closed"))
                status = str(callback["status"])
                confirmation = callback.get("confirmation")
                fill_price = callback.get("price")
                tx["totalWithConfirmation"] = round(perf_counter() - started, 3)
            public_orders = _public_orders(orders)
            cancel_reason = str((callback if not wait else {}).get("cancelReason") or _cancel_reason(orders))
            result = {
                "action": "close",
                "status": status,
                "pair": pair_name,
                "price": float(price),
                "slippageBps": DEFAULT_SLIPPAGE_BPS,
                "approval": approval_tx,
                "tx": tx,
                "orders": public_orders,
                "closed": closed,
                "fillPrice": fill_price,
                "confirmation": confirmation,
                "settlement": callback if not wait else None,
            }
            attempts.append(
                {
                    "attempt": attempt,
                    "status": status,
                    "txHash": tx.get("txHash"),
                    "cancelReason": cancel_reason,
                    "timing": tx.get("timing"),
                }
            )
            result["attempts"] = attempts
            last_result = result
            LOGGER.info("close attempt result %s %s tx=%s reason=%s", pair_name, status, tx.get("txHash"), cancel_reason)
            if closed:
                return result
            if status == "cancelled" and attempt < CLOSE_MAX_ATTEMPTS:
                time.sleep(0.8)
                continue
            if status in {"pending_execution", "pending_index"}:
                return result

        reason = cancel_reason if "cancel_reason" in locals() else _cancel_reason(orders if "orders" in locals() else [])
        if last_result and last_result.get("status") in {"pending_execution", "pending_index"}:
            return last_result
        raise OstiumError(f"close did not confirm after {CLOSE_MAX_ATTEMPTS} attempts: {reason or 'not indexed'}")


def _contract_position(position: dict[str, Any] | None, pair_name: str) -> dict[str, Any] | None:
    if not position or position.get("pair") != pair_name:
        return None
    pair_id = position.get("pairId")
    index = position.get("idx")
    if pair_id is None or index is None:
        return None
    base, quote = pair_name.split("-", 1)
    return {
        "pair": {"id": str(pair_id), "from": base, "to": quote},
        "index": str(index),
        "isBuy": position.get("side") == "long",
    }


def _price_payload(price: Decimal) -> dict[str, Any]:
    value = float(price)
    return {"mid": value, "bid": value, "ask": value, "isMarketOpen": True}
