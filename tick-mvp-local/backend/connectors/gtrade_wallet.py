from __future__ import annotations

import os
import queue
import re
import threading
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

from .base import ConnectorError
from .gtrade_constants import (
    ARBITRUM_BACKEND,
    ARBITRUM_CHAIN_ID,
    DELEGATE_ABI,
    DIAMOND_ARBITRUM,
    ERC20_ABI,
    MARKET_EXECUTED_ABI,
    MAX_UINT256,
    TRADE_FIELDS,
    TRADING_ABI,
    USDC_ARBITRUM,
    ZERO_ADDRESS,
)
from .gtrade_events import GTradeEventStream
from .gtrade_latency import latency_log_enabled, latency_log_path, write_latency_event
from .gtrade_public import GTradePair, normalize_pair


ROOT = Path(__file__).resolve().parents[3]
MARKET_EXECUTED_TOPIC = "0x" + Web3.keccak(
    text=(
        "MarketExecuted("
        "(address,uint32),"
        "address,"
        "uint32,"
        "(address,uint32,uint16,uint24,bool,bool,uint8,uint8,uint120,uint64,uint64,uint64,bool,uint160,uint24),"
        "bool,"
        "uint256,"
        "uint256,"
        "uint256,"
        "uint256,"
        "int256,"
        "uint256,"
        "uint256"
        ")"
    )
).hex().removeprefix("0x")


class GTradeWalletError(ConnectorError):
    pass


class GTradeWallet:
    def __init__(self) -> None:
        self._connection: tuple[Any, str, Web3] | None = None
        self._delegate_cache: tuple[str, str, float] | None = None
        self._event_stream: GTradeEventStream | None = None
        self._tx_cache_lock = threading.RLock()
        self._nonce_cache: dict[str, int] = {}
        self._fee_cache: tuple[float, dict[str, int]] | None = None
        self._prewarm_stop = threading.Event()
        self._prewarm_thread: threading.Thread | None = None
        self._prewarm_last_at = 0.0
        self._prewarm_last_elapsed_ms: float | None = None
        self._prewarm_last_error: str | None = None
        self._trading_contract: Any | None = None
        self._usdc_contract: Any | None = None
        self._direct_log_connection: tuple[str, Web3] | None = None

    def start(self) -> None:
        if self._prewarm_thread and self._prewarm_thread.is_alive():
            return
        self._prewarm_stop.clear()
        self._prewarm_thread = threading.Thread(target=self._run_prewarm, name="gtrade-prewarm", daemon=True)
        self._prewarm_thread.start()

    def stop(self) -> None:
        self._prewarm_stop.set()
        if self._prewarm_thread:
            self._prewarm_thread.join(timeout=2)

    def address(self) -> str:
        _, address, _ = self._load()
        return address

    def account(self, pair_names: dict[int, str], prices: dict[str, dict[str, Any]]) -> dict[str, Any]:
        _, address, web3 = self._load()
        self._prewarm_execution_cache(web3, address)
        balances = self.balances()
        return {
            "address": address,
            "balances": balances,
            "positions": [
                _position_public(item, pair_names, prices)
                for item in self.open_trades()
            ],
        }

    def balances(self) -> dict[str, Any]:
        _, address, web3 = self._load()
        usdc = self._usdc_token(web3)
        allowance = Decimal(usdc.functions.allowance(address, Web3.to_checksum_address(DIAMOND_ARBITRUM)).call()) / Decimal(10**6)
        return {
            "eth": float(Decimal(web3.eth.get_balance(address)) / Decimal(10**18)),
            "usdc": float(Decimal(usdc.functions.balanceOf(address).call()) / Decimal(10**6)),
            "allowance": "max" if allowance > Decimal("100000000") else float(allowance),
        }

    def usdc_balance(self) -> float:
        _, address, web3 = self._load()
        balance = self._usdc_token(web3).functions.balanceOf(address).call()
        return float(Decimal(balance) / Decimal(10**6))

    def approve(self, amount: Decimal | None = None) -> dict[str, Any]:
        account, address, web3 = self._load()
        approval_amount = MAX_UINT256 if amount is None else _usdc_units(amount)
        fn = self._usdc_token(web3).functions.approve(Web3.to_checksum_address(DIAMOND_ARBITRUM), approval_amount)
        result = self._send(web3, account, address, fn, "approve")
        result["allowanceUsdc"] = "max" if amount is None else float(amount)
        return result

    def execution_health(self) -> dict[str, Any]:
        _, address, web3 = self._load()
        self._prewarm_execution_cache(web3, address)
        event_health = self._event_stream.health() if self._event_stream else None
        agent = None
        if os.getenv("GTRADE_DELEGATED", "0") == "1":
            try:
                agent = Web3.to_checksum_address(self._agent().address)
            except Exception as exc:
                agent = {"error": f"{type(exc).__name__}: {exc}"}
        return {
            "delegated": os.getenv("GTRADE_DELEGATED", "0") == "1",
            "skipGasEstimate": os.getenv("GTRADE_SKIP_GAS_ESTIMATE", "0") == "1",
            "nonceCache": os.getenv("GTRADE_NONCE_CACHE", "1") == "1",
            "feeCache": os.getenv("GTRADE_FEE_CACHE", "1") == "1",
            "agent": agent,
            "eventStream": event_health,
            "prewarm": {
                "running": bool(self._prewarm_thread and self._prewarm_thread.is_alive()),
                "lastAt": self._prewarm_last_at or None,
                "lastElapsedMs": self._prewarm_last_elapsed_ms,
                "error": self._prewarm_last_error,
                "intervalSeconds": float(os.getenv("GTRADE_PREWARM_INTERVAL_SECONDS", "1.5")),
            },
            "fastWait": {
                "raceRestFallback": os.getenv("GTRADE_RACE_REST_FALLBACK", "1") == "1",
                "restFallbackDelaySeconds": float(os.getenv("GTRADE_REST_FALLBACK_DELAY_SECONDS", "0.8")),
                "eventWaitSeconds": float(os.getenv("GTRADE_EVENT_WAIT_SECONDS", "4")),
                "directLogWaitSeconds": float(os.getenv("GTRADE_DIRECT_LOG_WAIT_SECONDS", "4")),
                "directLogPollSeconds": float(os.getenv("GTRADE_DIRECT_LOG_POLL_INTERVAL_SECONDS", "0.12")),
                "directLogTransport": self._direct_log_transport_name(),
                "latencyLogEnabled": latency_log_enabled(),
                "latencyLogPath": str(latency_log_path()),
            },
        }

    def latest_position_event(
        self,
        pair_index: int,
        *,
        present: bool,
        since: float,
        position_index: int | None = None,
    ) -> dict[str, Any] | None:
        _, address, _ = self._load()
        events = self._events(address)
        events.start()
        return events.latest_position_event(
            pair_index,
            present=present,
            since=since,
            position_index=position_index,
        )

    def open_position(
        self,
        pair: GTradePair,
        side: str,
        ticket_usd: Decimal,
        leverage: Decimal,
        price: Decimal,
        *,
        slippage_bps: int,
        wait_seconds: float = 9,
    ) -> dict[str, Any]:
        account, address, web3 = self._load()
        events = self._events(address)
        listen_since = time.time()
        events.start()
        trade = (
            address,
            0,
            pair.pair_index,
            int((leverage * Decimal(1000)).to_integral_value(rounding=ROUND_DOWN)),
            side == "long",
            True,
            3,
            0,
            _usdc_units(ticket_usd),
            _price_units(price),
            0,
            0,
            False,
            0,
            0,
        )
        trading = self._trading(web3)
        fn = trading.functions.openTrade(trade, slippage_bps, ZERO_ADDRESS)
        tx = self._send_trading_action(web3, account, address, trading, fn, "open")
        if not _tx_succeeded(tx):
            return {
                "status": "failed",
                "tx": tx,
                "wait": None,
                "position": None,
                "rawPosition": None,
                "error": "open initiation transaction reverted",
            }
        wait = self._wait_for_position_with_events(
            pair.pair_index,
            present=True,
            since=listen_since,
            timeout_seconds=wait_seconds,
            web3=web3,
            owner=address,
            execution_open=True,
            since_block=int(tx["blockNumber"]),
            initiation_tx_hash=tx["txHash"],
        )
        position = wait["position"]
        return {
            "status": "open" if position else "pending_execution",
            "tx": tx,
            "wait": {key: value for key, value in wait.items() if key != "position"},
            "position": _position_public(position, {pair.pair_index: pair.pair}, {pair.pair: {"mid": float(price)}}) if position else None,
            "rawPosition": position,
        }

    def close_position(
        self,
        pair: GTradePair,
        position: dict[str, Any],
        price: Decimal,
        *,
        wait_seconds: float = 9,
    ) -> dict[str, Any]:
        account, address, web3 = self._load()
        events = self._events(address)
        listen_since = time.time()
        events.start()
        idx = int(position.get("idx") if position.get("idx") is not None else position.get("index"))
        trading = self._trading(web3)
        fn = trading.functions.closeTradeMarket(idx, _price_units(price))
        tx = self._send_trading_action(web3, account, address, trading, fn, "close")
        if not _tx_succeeded(tx):
            try:
                status_wait = self.wait_for_position_status(
                    pair.pair_index,
                    present=True,
                    timeout_seconds=float(os.getenv("GTRADE_FAILED_CLOSE_RECHECK_SECONDS", "1.5")),
                    poll_interval=0.20,
                    position_index=idx,
                )
                still_visible = (
                    not status_wait["timedOut"]
                    and status_wait["observedPresent"] is True
                )
            except Exception as exc:
                status_wait = {
                    "source": "failed_close_recheck",
                    "timedOut": True,
                    "observedPresent": None,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                still_visible = None
            return {
                "status": "failed" if still_visible is not False else "external_closed",
                "closed": still_visible is False,
                "closeTxFailed": True,
                "tx": tx,
                "wait": status_wait,
                "position": position,
                "error": (
                    "close initiation transaction reverted; position is no longer visible"
                    if still_visible is False
                    else "close initiation transaction reverted"
                ),
                "finalizationSource": (
                    "position_absent_after_failed_close"
                    if still_visible is False
                    else "failed_close_receipt"
                ),
            }
        wait = self._wait_for_position_with_events(
            pair.pair_index,
            present=False,
            since=listen_since,
            timeout_seconds=wait_seconds,
            position_index=idx,
            web3=web3,
            owner=address,
            execution_open=False,
            since_block=int(tx["blockNumber"]),
            initiation_tx_hash=tx["txHash"],
        )
        closed = not wait["timedOut"] and wait["observedPresent"] is False
        return {
            "status": "closed" if closed else "pending_execution",
            "closed": closed,
            "tx": tx,
            "wait": {key: value for key, value in wait.items() if key != "position"},
            "position": position,
        }

    def _wait_for_position_with_events(
        self,
        pair_index: int,
        *,
        present: bool,
        since: float,
        timeout_seconds: float,
        position_index: int | None = None,
        web3: Web3 | None = None,
        owner: str | None = None,
        execution_open: bool | None = None,
        since_block: int | None = None,
        initiation_tx_hash: str | None = None,
    ) -> dict[str, Any]:
        if os.getenv("GTRADE_RACE_REST_FALLBACK", "1") == "1":
            return self._race_position_wait(
                pair_index,
                present=present,
                since=since,
                timeout_seconds=timeout_seconds,
                position_index=position_index,
                web3=web3,
                owner=owner,
                execution_open=execution_open,
                since_block=since_block,
                initiation_tx_hash=initiation_tx_hash,
            )

        event_timeout = min(timeout_seconds, float(os.getenv("GTRADE_EVENT_WAIT_SECONDS", "4")))
        event_wait = (
            self._event_stream.wait_for_position_event(
                pair_index,
                present=present,
                since=since,
                timeout_seconds=event_timeout,
                position_index=position_index,
            )
            if self._event_stream
            else None
        )
        if event_wait and not event_wait["timedOut"]:
            return {
                **event_wait,
                "fallback": None,
            }
        log_wait = (
            self._wait_for_market_executed(
                web3,
                owner,
                pair_index,
                execution_open,
                since_block,
                timeout_seconds=min(timeout_seconds, float(os.getenv("GTRADE_DIRECT_LOG_WAIT_SECONDS", "4"))),
                position_index=position_index,
                initiation_tx_hash=initiation_tx_hash,
            )
            if web3 is not None and owner and execution_open is not None and since_block is not None
            else None
        )
        if log_wait and not log_wait["timedOut"] and not (present and log_wait.get("positionUsable") is False):
            return {
                **log_wait,
                "eventWait": event_wait,
                "fallback": None,
            }
        fallback_timeout = max(0.5, timeout_seconds - (event_wait or {}).get("elapsedMs", 0) / 1000)
        fallback = self.wait_for_position_status(
            pair_index,
            present=present,
            timeout_seconds=fallback_timeout,
            poll_interval=0.20,
            position_index=position_index,
        )
        return {
            **fallback,
            "source": "open_trades_rest",
            "eventWait": event_wait,
        }

    def _race_position_wait(
        self,
        pair_index: int,
        *,
        present: bool,
        since: float,
        timeout_seconds: float,
        position_index: int | None = None,
        web3: Web3 | None = None,
        owner: str | None = None,
        execution_open: bool | None = None,
        since_block: int | None = None,
        initiation_tx_hash: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        result_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        event_timeout = min(timeout_seconds, float(os.getenv("GTRADE_EVENT_WAIT_SECONDS", "4")))
        log_timeout = min(timeout_seconds, float(os.getenv("GTRADE_DIRECT_LOG_WAIT_SECONDS", "4")))
        rest_delay = max(0.0, float(os.getenv("GTRADE_REST_FALLBACK_DELAY_SECONDS", "0.8")))
        rest_poll = max(0.05, float(os.getenv("GTRADE_REST_POLL_INTERVAL_SECONDS", "0.18")))
        deadline = time.monotonic() + timeout_seconds

        def publish(label: str, result: dict[str, Any]) -> None:
            result_queue.put((label, result))

        if self._event_stream:
            threading.Thread(
                target=lambda: publish(
                    "event",
                    self._event_stream.wait_for_position_event(
                        pair_index,
                        present=present,
                        since=since,
                        timeout_seconds=event_timeout,
                        position_index=position_index,
                    ),
                ),
                name="gtrade-event-wait",
                daemon=True,
            ).start()

        if web3 is not None and owner and execution_open is not None and since_block is not None:
            threading.Thread(
                target=lambda: publish(
                    "direct_log",
                    self._wait_for_market_executed(
                        web3,
                        owner,
                        pair_index,
                        execution_open,
                        since_block,
                        timeout_seconds=log_timeout,
                        position_index=position_index,
                        initiation_tx_hash=initiation_tx_hash,
                    ),
                ),
                name="gtrade-direct-log-wait",
                daemon=True,
            ).start()

        def rest_worker() -> None:
            if rest_delay:
                time.sleep(rest_delay)
            remaining = max(0.05, deadline - time.monotonic())
            publish(
                "rest",
                self.wait_for_position_status(
                    pair_index,
                    present=present,
                    timeout_seconds=remaining,
                    poll_interval=rest_poll,
                    position_index=position_index,
                ),
            )

        threading.Thread(target=rest_worker, name="gtrade-rest-race", daemon=True).start()

        event_wait: dict[str, Any] | None = None
        rest_wait: dict[str, Any] | None = None
        direct_log_wait: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                label, result = result_queue.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty:
                break
            if label == "event":
                event_wait = result
            elif label == "direct_log":
                direct_log_wait = result
            else:
                rest_wait = result
            if not result.get("timedOut"):
                if label == "direct_log" and present and result.get("positionUsable") is False:
                    continue
                race = {
                    "elapsedMs": _elapsed_ms(started),
                    "winner": label,
                    "restFallbackDelayMs": round(rest_delay * 1000, 1),
                }
                if label == "event":
                    return {
                        **result,
                        "fallback": None,
                        "directLogWait": direct_log_wait,
                        "restWait": rest_wait,
                        "race": race,
                    }
                if label == "direct_log":
                    return {
                        **result,
                        "fallback": None,
                        "eventWait": event_wait,
                        "restWait": rest_wait,
                        "race": race,
                    }
                return {**result, "source": "open_trades_rest", "eventWait": event_wait, "race": race}

        if rest_wait is not None:
            return {
                **rest_wait,
                "source": "open_trades_rest",
                "eventWait": event_wait,
                "directLogWait": direct_log_wait,
                "race": {"elapsedMs": _elapsed_ms(started), "winner": None},
            }
        if direct_log_wait is not None:
            return {
                **direct_log_wait,
                "eventWait": event_wait,
                "fallback": None,
                "race": {"elapsedMs": _elapsed_ms(started), "winner": None},
            }
        if event_wait is not None:
            return {
                **event_wait,
                "fallback": None,
                "directLogWait": direct_log_wait,
                "race": {"elapsedMs": _elapsed_ms(started), "winner": None},
            }
        return {
            "source": "position_wait",
            "position": None,
            "startedAt": time.time() - (time.perf_counter() - started),
            "finishedAt": time.time(),
            "elapsedMs": _elapsed_ms(started),
            "targetPresent": present,
            "observedPresent": None,
            "timedOut": True,
            "race": {"elapsedMs": _elapsed_ms(started), "winner": None},
        }

    def _wait_for_market_executed(
        self,
        web3: Web3,
        owner: str,
        pair_index: int,
        execution_open: bool,
        since_block: int,
        *,
        timeout_seconds: float,
        position_index: int | None = None,
        initiation_tx_hash: str | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        started_at = time.time()
        deadline = time.monotonic() + timeout_seconds
        scan_from = max(0, int(since_block))
        poll_interval = max(0.05, float(os.getenv("GTRADE_DIRECT_LOG_POLL_INTERVAL_SECONDS", "0.12")))
        log_web3, transport = self._direct_log_web3(web3)
        source = "direct_wss_log" if transport == "wss" else "direct_http_log"
        contract = log_web3.eth.contract(
            address=Web3.to_checksum_address(DIAMOND_ARBITRUM),
            abi=MARKET_EXECUTED_ABI,
        )
        polls = 0
        errors: list[str] = []
        write_latency_event(
            "direct_callback_log_wait_started",
            {
                "source": source,
                "owner": Web3.to_checksum_address(owner),
                "pairIndex": pair_index,
                "tradeIndex": position_index,
                "executionOpen": execution_open,
                "fromBlock": since_block,
                "pollIntervalMs": round(poll_interval * 1000, 1),
                "timeoutSeconds": timeout_seconds,
                "initiationTxHash": initiation_tx_hash,
            },
        )

        while time.monotonic() < deadline:
            polls += 1
            try:
                latest = int(log_web3.eth.block_number)
                if latest >= scan_from:
                    logs = log_web3.eth.get_logs(
                        {
                            "address": Web3.to_checksum_address(DIAMOND_ARBITRUM),
                            "fromBlock": scan_from,
                            "toBlock": latest,
                        }
                    )
                    for log in logs:
                        event = self._decode_market_executed(contract, log)
                        position_usable = False
                        if event:
                            trade = event.get("trade") or {}
                            if str(event.get("user", "")).lower() != owner.lower():
                                continue
                            if bool(event.get("open")) != bool(execution_open):
                                continue
                            if int(trade.get("pairIndex", -1)) != int(pair_index):
                                continue
                            raw_index = trade.get("index")
                            if position_index is not None and raw_index is not None and int(raw_index) != position_index:
                                continue
                            position_usable = execution_open
                            event["matchKind"] = "market_executed_abi"
                        else:
                            event = self._raw_trade_topic_match(
                                log,
                                owner=owner,
                                pair_index=pair_index,
                                position_index=position_index,
                                initiation_tx_hash=initiation_tx_hash,
                                execution_open=execution_open,
                            )
                            if not event:
                                continue
                            trade = event.get("trade") or {}

                        self._annotate_callback_timing(
                            log_web3,
                            event,
                            initiation_block=since_block,
                        )
                        write_latency_event(
                            "direct_callback_log_seen",
                            {
                                "source": source,
                                "matchKind": event.get("matchKind"),
                                "owner": Web3.to_checksum_address(owner),
                                "pairIndex": pair_index,
                                "tradeIndex": position_index,
                                "executionOpen": execution_open,
                                "initiationTxHash": initiation_tx_hash,
                                "callbackTxHash": event.get("transactionHash"),
                                "callbackBlock": event.get("blockNumber"),
                                "callbackLogIndex": event.get("logIndex"),
                                "initiationBlock": since_block,
                                "blocksAfterInitiation": event.get("blocksAfterInitiation"),
                                "initiationBlockTimestamp": event.get("initiationBlockTimestamp"),
                                "callbackBlockTimestamp": event.get("blockTimestamp"),
                                "secondsAfterInitiationBlock": event.get("secondsAfterInitiationBlock"),
                                "pollCount": polls,
                                "elapsedMs": _elapsed_ms(started),
                            },
                        )
                        return {
                            "source": source,
                            "event": event,
                            "position": {"trade": trade, "raw": event} if execution_open and position_usable else None,
                            "positionUsable": position_usable,
                            "startedAt": started_at,
                            "finishedAt": time.time(),
                            "elapsedMs": _elapsed_ms(started),
                            "targetPresent": execution_open,
                            "observedPresent": execution_open,
                            "timedOut": False,
                            "pollCount": polls,
                            "fromBlock": since_block,
                            "toBlock": latest,
                        }
                    scan_from = latest + 1
            except Exception as exc:
                if len(errors) < 3:
                    errors.append(f"{type(exc).__name__}: {exc}")
            time.sleep(poll_interval)

        write_latency_event(
            "direct_callback_log_wait_timeout",
            {
                "source": source,
                "owner": Web3.to_checksum_address(owner),
                "pairIndex": pair_index,
                "tradeIndex": position_index,
                "executionOpen": execution_open,
                "fromBlock": since_block,
                "lastScannedBlock": scan_from - 1,
                "pollCount": polls,
                "elapsedMs": _elapsed_ms(started),
                "errors": errors,
                "initiationTxHash": initiation_tx_hash,
            },
        )
        return {
            "source": source,
            "event": None,
            "position": None,
            "positionUsable": False,
            "startedAt": started_at,
            "finishedAt": time.time(),
            "elapsedMs": _elapsed_ms(started),
            "targetPresent": execution_open,
            "observedPresent": None,
            "timedOut": True,
            "pollCount": polls,
            "fromBlock": since_block,
            "lastScannedBlock": scan_from - 1,
            "errors": errors,
        }

    def _raw_trade_topic_match(
        self,
        log: Any,
        *,
        owner: str,
        pair_index: int,
        position_index: int | None,
        initiation_tx_hash: str | None,
        execution_open: bool,
    ) -> dict[str, Any] | None:
        tx_hash = _normalize_tx_hash(_hex(log.get("transactionHash")))
        if initiation_tx_hash and tx_hash == _normalize_tx_hash(initiation_tx_hash):
            return None
        topics = [_hex(topic).lower() for topic in (log.get("topics") or [])]
        data = _hex(log.get("data")).lower()
        haystack = "".join(topic.removeprefix("0x") for topic in topics) + data.removeprefix("0x")
        owner_word = _topic_address(owner).removeprefix("0x")
        pair_word = _topic_u256(pair_index).removeprefix("0x")
        index_word = _topic_u256(position_index).removeprefix("0x") if position_index is not None else None
        owner_matches = owner_word in haystack
        pair_matches = pair_word in haystack
        index_matches = bool(index_word and index_word in haystack)
        if not owner_matches:
            return None
        if position_index is not None:
            if not (index_matches or pair_matches):
                return None
        elif not pair_matches:
            return None
        trade: dict[str, Any] = {
            "user": Web3.to_checksum_address(owner),
            "pairIndex": pair_index,
        }
        if position_index is not None:
            trade["index"] = position_index
        return {
            "name": "RawTradeTopicLog",
            "matchKind": "raw_topic",
            "receivedAt": time.time(),
            "transactionHash": _hex(log.get("transactionHash")),
            "blockNumber": int(log.get("blockNumber")),
            "logIndex": int(log.get("logIndex")),
            "topics": topics,
            "topicMatches": {
                "owner": owner_matches,
                "pairIndex": pair_matches,
                "tradeIndex": index_matches,
            },
            "user": Web3.to_checksum_address(owner),
            "trade": trade,
            "open": execution_open,
        }

    def _annotate_callback_timing(
        self,
        web3: Web3,
        event: dict[str, Any],
        *,
        initiation_block: int,
    ) -> None:
        callback_block = int(event.get("blockNumber") or 0)
        if not callback_block:
            return
        event["blocksAfterInitiation"] = callback_block - int(initiation_block)
        try:
            callback_timestamp = int(web3.eth.get_block(callback_block).timestamp)
            initiation_timestamp = int(web3.eth.get_block(int(initiation_block)).timestamp)
        except Exception:
            return
        event["blockTimestamp"] = callback_timestamp
        event["initiationBlockTimestamp"] = initiation_timestamp
        event["secondsAfterInitiationBlock"] = callback_timestamp - initiation_timestamp

    @staticmethod
    def _decode_market_executed(contract: Any, log: Any) -> dict[str, Any] | None:
        try:
            decoded = contract.events.MarketExecuted().process_log(log)
        except Exception:
            return None
        args = decoded.get("args") or {}
        trade = _trade_from_event_args(args.get("t"))
        return {
            "name": "MarketExecuted",
            "receivedAt": time.time(),
            "transactionHash": _hex(decoded.get("transactionHash") or log.get("transactionHash")),
            "blockNumber": int(decoded.get("blockNumber") or log.get("blockNumber")),
            "logIndex": int(decoded.get("logIndex") or log.get("logIndex")),
            "user": Web3.to_checksum_address(str(args.get("user"))),
            "index": int(args.get("index")),
            "trade": trade,
            "open": bool(args.get("open")),
            "oraclePrice": str(args.get("oraclePrice")),
            "marketPrice": str(args.get("marketPrice")),
            "liqPrice": str(args.get("liqPrice")),
            "priceImpactP": str(args.get("priceImpactP")),
            "percentProfit": str(args.get("percentProfit")),
            "amountSentToTrader": str(args.get("amountSentToTrader")),
            "collateralPriceUsd": str(args.get("collateralPriceUsd")),
        }

    def open_trades(self) -> list[dict[str, Any]]:
        _, address, _ = self._load()
        response = requests.get(
            f"{ARBITRUM_BACKEND}/open-trades/{address}",
            timeout=float(os.getenv("GTRADE_BACKEND_TIMEOUT_SECONDS", "4")),
            headers={"user-agent": "tick-gtrade-mvp/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise GTradeWalletError("open-trades returned non-list JSON")
        return payload

    def wait_for_position(
        self,
        pair_index: int,
        *,
        present: bool,
        timeout_seconds: float,
        poll_interval: float = 0.35,
    ) -> dict[str, Any] | None:
        return self.wait_for_position_status(
            pair_index,
            present=present,
            timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        )["position"]

    def wait_for_position_status(
        self,
        pair_index: int,
        *,
        present: bool,
        timeout_seconds: float,
        poll_interval: float = 0.20,
        position_index: int | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        started_at = time.time()
        deadline = time.monotonic() + timeout_seconds
        polls: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            poll_started = time.perf_counter()
            positions = [
                item
                for item in self.open_trades()
                if int(item.get("trade", {}).get("pairIndex", -1)) == pair_index
                and (
                    position_index is None
                    or int(item.get("trade", {}).get("index", -1)) == position_index
                )
            ]
            poll = {
                "at": time.time(),
                "offsetMs": _elapsed_ms(started),
                "readMs": _elapsed_ms(poll_started),
                "positionCount": len(positions),
            }
            polls.append(poll)
            if bool(positions) is present:
                return {
                    "position": positions[0] if positions else None,
                    "startedAt": started_at,
                    "finishedAt": time.time(),
                    "elapsedMs": _elapsed_ms(started),
                    "pollIntervalMs": round(poll_interval * 1000, 1),
                    "timeoutSeconds": timeout_seconds,
                    "polls": polls,
                    "pollCount": len(polls),
                    "targetPresent": present,
                    "observedPresent": bool(positions),
                    "timedOut": False,
                }
            time.sleep(poll_interval)
        return {
            "position": None,
            "startedAt": started_at,
            "finishedAt": time.time(),
            "elapsedMs": _elapsed_ms(started),
            "pollIntervalMs": round(poll_interval * 1000, 1),
            "timeoutSeconds": timeout_seconds,
            "polls": polls,
            "pollCount": len(polls),
            "targetPresent": present,
            "observedPresent": False,
            "timedOut": True,
        }

    def _load(self) -> tuple[Any, str, Web3]:
        if self._connection:
            return self._connection
        load_dotenv(ROOT / ".env")
        wallet_pk = os.getenv("WALLET_PK")
        rpc_url = os.getenv("ARB_RPC_URL")
        if not wallet_pk:
            raise GTradeWalletError("WALLET_PK missing in root .env")
        if not rpc_url:
            raise GTradeWalletError("ARB_RPC_URL missing in root .env")
        key = wallet_pk.strip()
        account = Account.from_key(key if key.startswith("0x") else f"0x{key}")
        address = Web3.to_checksum_address(account.address)
        web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
        if not web3.is_connected():
            raise GTradeWalletError("could not connect to ARB_RPC_URL")
        if web3.eth.chain_id != ARBITRUM_CHAIN_ID:
            raise GTradeWalletError(f"RPC chain_id {web3.eth.chain_id}, expected {ARBITRUM_CHAIN_ID}")
        self._connection = (account, address, web3)
        return self._connection

    def _direct_log_transport_name(self) -> str:
        load_dotenv(ROOT / ".env")
        return "wss" if os.getenv("ARB_WSS_URL") else "http"

    def _direct_log_web3(self, fallback_web3: Web3) -> tuple[Web3, str]:
        load_dotenv(ROOT / ".env")
        wss_url = os.getenv("ARB_WSS_URL")
        if not wss_url:
            return fallback_web3, "http"
        if self._direct_log_connection is not None:
            return self._direct_log_connection[1], self._direct_log_connection[0]
        try:
            web3 = Web3(
                Web3.LegacyWebSocketProvider(
                    wss_url,
                    websocket_timeout=int(float(os.getenv("ARB_WSS_TIMEOUT_SECONDS", "10"))),
                )
            )
            if not web3.is_connected():
                raise GTradeWalletError("ARB_WSS_URL websocket is not connected")
            chain_id = int(web3.eth.chain_id)
            if chain_id != ARBITRUM_CHAIN_ID:
                raise GTradeWalletError(f"ARB_WSS_URL chain_id {chain_id}, expected {ARBITRUM_CHAIN_ID}")
            self._direct_log_connection = ("wss", web3)
            return web3, "wss"
        except Exception as exc:
            write_latency_event(
                "direct_callback_wss_unavailable",
                {"error": f"{type(exc).__name__}: {exc}"},
            )
            return fallback_web3, "http"

    def _run_prewarm(self) -> None:
        while not self._prewarm_stop.is_set():
            started = time.perf_counter()
            try:
                _, address, web3 = self._load()
                self._prewarm_execution_cache(web3, address)
                self._prewarm_last_at = time.time()
                self._prewarm_last_elapsed_ms = _elapsed_ms(started)
                self._prewarm_last_error = None
            except Exception as exc:
                self._prewarm_last_at = time.time()
                self._prewarm_last_elapsed_ms = _elapsed_ms(started)
                self._prewarm_last_error = f"{type(exc).__name__}: {exc}"
            self._prewarm_stop.wait(max(0.25, float(os.getenv("GTRADE_PREWARM_INTERVAL_SECONDS", "1.5"))))

    def _trading(self, web3: Web3) -> Any:
        if self._trading_contract is None:
            self._trading_contract = web3.eth.contract(
                address=Web3.to_checksum_address(DIAMOND_ARBITRUM),
                abi=TRADING_ABI + DELEGATE_ABI,
            )
        return self._trading_contract

    def _usdc_token(self, web3: Web3) -> Any:
        if self._usdc_contract is None:
            self._usdc_contract = web3.eth.contract(address=Web3.to_checksum_address(USDC_ARBITRUM), abi=ERC20_ABI)
        return self._usdc_contract

    def _send(self, web3: Web3, account: Any, address: str, fn: Any, label: str) -> dict[str, Any]:
        started_at = time.time()
        started = time.perf_counter()
        skip_gas_estimate = os.getenv("GTRADE_SKIP_GAS_ESTIMATE", "0") == "1"
        gas_started = time.perf_counter()
        gas = _fixed_gas(label) if skip_gas_estimate else int(fn.estimate_gas({"from": address}))
        gas_ms = 0.0 if skip_gas_estimate else _elapsed_ms(gas_started)
        gas_ready_at = time.time()
        tx, build_timing = self._build_transaction(web3, address, fn, gas)
        built_at = time.time()
        sign_started = time.perf_counter()
        signed = account.sign_transaction(tx)
        raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        precomputed_tx_hash = Web3.keccak(raw_tx).hex()
        sign_ms = _elapsed_ms(sign_started)
        signed_at = time.time()
        write_latency_event(
            "tx_signed",
            {
                "label": label,
                "txHash": precomputed_tx_hash,
                "sender": Web3.to_checksum_address(address),
                "nonce": build_timing.get("nonce"),
                "gas": gas,
                "buildTiming": build_timing,
                "gasEstimateMs": gas_ms,
                "signMs": sign_ms,
                "signedAt": signed_at,
            },
        )
        send_started = time.perf_counter()
        retried_for_base_fee = False
        write_latency_event(
            "broadcast_started",
            {
                "label": label,
                "txHash": precomputed_tx_hash,
                "sender": Web3.to_checksum_address(address),
                "nonce": build_timing.get("nonce"),
                "startedAt": time.time(),
            },
        )
        try:
            tx_hash = web3.eth.send_raw_transaction(raw_tx)
        except Exception as exc:
            if _is_base_fee_error(exc):
                self._invalidate_fee_cache()
                retried_for_base_fee = True
                tx, retry_build_timing = self._build_transaction(
                    web3,
                    address,
                    fn,
                    gas,
                    aggressive=True,
                    nonce_override=int(build_timing["nonce"]),
                )
                build_timing = {**build_timing, "retry": retry_build_timing}
                built_at = time.time()
                sign_started = time.perf_counter()
                signed = account.sign_transaction(tx)
                raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
                precomputed_tx_hash = Web3.keccak(raw_tx).hex()
                sign_ms = _elapsed_ms(sign_started)
                signed_at = time.time()
                write_latency_event(
                    "tx_resigned",
                    {
                        "label": label,
                        "reason": "base_fee",
                        "txHash": precomputed_tx_hash,
                        "sender": Web3.to_checksum_address(address),
                        "nonce": build_timing.get("nonce"),
                        "buildTiming": build_timing,
                        "signMs": sign_ms,
                        "signedAt": signed_at,
                    },
                )
                tx_hash = web3.eth.send_raw_transaction(raw_tx)
            elif _is_known_transaction_error(exc):
                tx_hash = Web3.to_bytes(hexstr=_normalize_tx_hash(precomputed_tx_hash))
                write_latency_event(
                    "broadcast_already_known",
                    {
                        "label": label,
                        "txHash": precomputed_tx_hash,
                        "sender": Web3.to_checksum_address(address),
                        "nonce": build_timing.get("nonce"),
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsedMs": _elapsed_ms(send_started),
                    },
                )
            elif _is_nonce_error(exc):
                self._invalidate_nonce(address)
                tx, retry_build_timing = self._build_transaction(web3, address, fn, gas, fresh_nonce=True)
                build_timing = {**build_timing, "retry": retry_build_timing}
                built_at = time.time()
                sign_started = time.perf_counter()
                signed = account.sign_transaction(tx)
                raw_tx = getattr(signed, "raw_transaction", None) or signed.rawTransaction
                precomputed_tx_hash = Web3.keccak(raw_tx).hex()
                sign_ms = _elapsed_ms(sign_started)
                signed_at = time.time()
                write_latency_event(
                    "tx_resigned",
                    {
                        "label": label,
                        "reason": "nonce",
                        "txHash": precomputed_tx_hash,
                        "sender": Web3.to_checksum_address(address),
                        "nonce": build_timing.get("nonce"),
                        "buildTiming": build_timing,
                        "signMs": sign_ms,
                        "signedAt": signed_at,
                    },
                )
                tx_hash = web3.eth.send_raw_transaction(raw_tx)
            else:
                self._invalidate_nonce(address)
                write_latency_event(
                    "broadcast_failed",
                    {
                        "label": label,
                        "txHash": precomputed_tx_hash,
                        "sender": Web3.to_checksum_address(address),
                        "nonce": build_timing.get("nonce"),
                        "error": f"{type(exc).__name__}: {exc}",
                        "elapsedMs": _elapsed_ms(send_started),
                    },
                )
                raise
        send_ms = _elapsed_ms(send_started)
        sent_at = time.time()
        write_latency_event(
            "broadcast_returned",
            {
                "label": label,
                "txHash": tx_hash.hex(),
                "precomputedTxHash": precomputed_tx_hash,
                "sender": Web3.to_checksum_address(address),
                "nonce": build_timing.get("nonce"),
                "sendMs": send_ms,
                "sentAt": sent_at,
                "retriedForBaseFee": retried_for_base_fee,
            },
        )
        receipt_started = time.perf_counter()
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=90, poll_latency=0.2)
        receipt_at = time.time()
        block_timestamp = None
        block_started = time.perf_counter()
        if os.getenv("GTRADE_READ_RECEIPT_BLOCK", "0") == "1":
            try:
                block_timestamp = int(web3.eth.get_block(receipt.blockNumber).timestamp)
            except Exception:
                pass
        block_ms = _elapsed_ms(block_started)
        write_latency_event(
            "receipt_seen",
            {
                "label": label,
                "txHash": tx_hash.hex(),
                "precomputedTxHash": precomputed_tx_hash,
                "sender": Web3.to_checksum_address(address),
                "nonce": build_timing.get("nonce"),
                "receiptMs": _elapsed_ms(receipt_started),
                "receiptAt": receipt_at,
                "blockNumber": int(receipt.blockNumber),
                "blockTimestamp": block_timestamp,
                "status": int(receipt.status),
                "gasUsed": int(receipt.gasUsed),
                "effectiveGasPrice": int(getattr(receipt, "effectiveGasPrice", 0) or receipt.get("effectiveGasPrice", 0) or 0),
            },
        )
        return {
            "label": label,
            "txHash": tx_hash.hex(),
            "precomputedTxHash": precomputed_tx_hash,
            "estimateGas": gas,
            "gasEstimateMs": gas_ms,
            "gasEstimateSkipped": skip_gas_estimate,
            "buildMs": round((built_at - gas_ready_at) * 1000, 1),
            "buildTiming": build_timing,
            "signMs": sign_ms,
            "sendMs": send_ms,
            "receiptMs": _elapsed_ms(receipt_started),
            "blockReadMs": block_ms,
            "elapsedMs": _elapsed_ms(started),
            "status": int(receipt.status),
            "blockNumber": int(receipt.blockNumber),
            "gasUsed": int(receipt.gasUsed),
            "effectiveGasPrice": int(getattr(receipt, "effectiveGasPrice", 0) or receipt.get("effectiveGasPrice", 0) or 0),
            "retriedForBaseFee": retried_for_base_fee,
            "timestamps": {
                "startedAt": started_at,
                "gasReadyAt": gas_ready_at,
                "builtAt": built_at,
                "signedAt": signed_at,
                "sentAt": sent_at,
                "receiptAt": receipt_at,
                "blockTimestamp": block_timestamp,
            },
        }

    def _send_trading_action(self, web3: Web3, trader_account: Any, trader_address: str, trading: Any, fn: Any, label: str) -> dict[str, Any]:
        if os.getenv("GTRADE_DELEGATED", "0") != "1":
            return self._send(web3, trader_account, trader_address, fn, label)

        delegated_started = time.perf_counter()
        delegated_started_at = time.time()
        agent = self._agent()
        agent_address = Web3.to_checksum_address(agent.address)
        delegate_check_started = time.perf_counter()
        delegate_cache_hit = self._delegate_is_cached(trader_address, agent_address)
        if delegate_cache_hit:
            delegate_check_ms = 0.0
        else:
            current_delegate = Web3.to_checksum_address(trading.functions.getTradingDelegate(trader_address).call())
            delegate_check_ms = _elapsed_ms(delegate_check_started)
            if current_delegate != agent_address:
                raise GTradeWalletError(f"agent {agent_address} is not active delegate; current={current_delegate}")
            self._cache_delegate(trader_address, agent_address)
        encode_started = time.perf_counter()
        call_data = bytes.fromhex(fn._encode_transaction_data()[2:])
        encode_ms = _elapsed_ms(encode_started)
        wrap_started = time.perf_counter()
        delegated_fn = trading.functions.delegatedTradingAction(trader_address, call_data)
        wrap_ms = _elapsed_ms(wrap_started)
        result = self._send(web3, agent, agent_address, delegated_fn, label)
        result["delegated"] = True
        result["agent"] = agent_address
        result["trader"] = trader_address
        result["delegateTiming"] = {
            "startedAt": delegated_started_at,
            "beforeSendMs": round(
                (float(result["timestamps"]["startedAt"]) - delegated_started_at) * 1000,
                1,
            ),
            "delegateCacheHit": delegate_cache_hit,
            "delegateCheckMs": delegate_check_ms,
            "encodeMs": encode_ms,
            "wrapMs": wrap_ms,
            "totalMs": _elapsed_ms(delegated_started),
        }
        return result

    def _build_transaction(
        self,
        web3: Web3,
        address: str,
        fn: Any,
        gas: int,
        *,
        aggressive: bool = False,
        fresh_nonce: bool = False,
        nonce_override: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        started = time.perf_counter()
        if nonce_override is None:
            nonce, nonce_timing = self._next_nonce(web3, address, fresh=fresh_nonce)
        else:
            nonce = nonce_override
            nonce_timing = {"elapsedMs": 0.0, "source": "override", "cacheHit": None}
        fee_started = time.perf_counter()
        fee_params, fee_timing = self._cached_fee_params(web3, aggressive=aggressive)
        fee_ms = _elapsed_ms(fee_started)
        contract_started = time.perf_counter()
        tx = fn.build_transaction(
            {
                "from": address,
                "chainId": ARBITRUM_CHAIN_ID,
                "nonce": nonce,
                "gas": int(Decimal(gas) * Decimal("1.25")),
                **fee_params,
            }
        )
        contract_ms = _elapsed_ms(contract_started)
        return tx, {
            "nonceMs": nonce_timing["elapsedMs"],
            "nonceSource": nonce_timing["source"],
            "nonceCacheHit": nonce_timing["cacheHit"],
            "feeParamsMs": fee_ms,
            "feeSource": fee_timing["source"],
            "feeCacheHit": fee_timing["cacheHit"],
            "contractBuildMs": contract_ms,
            "totalMs": _elapsed_ms(started),
            "aggressive": aggressive,
            "nonce": nonce,
            "maxFeePerGas": fee_params.get("maxFeePerGas"),
            "maxPriorityFeePerGas": fee_params.get("maxPriorityFeePerGas"),
        }

    def _delegate_is_cached(self, trader_address: str, agent_address: str) -> bool:
        cache = self._delegate_cache
        if not cache:
            return False
        cached_trader, cached_agent, expires_at = cache
        return (
            cached_trader == Web3.to_checksum_address(trader_address)
            and cached_agent == Web3.to_checksum_address(agent_address)
            and time.monotonic() < expires_at
        )

    def _cache_delegate(self, trader_address: str, agent_address: str) -> None:
        ttl = float(os.getenv("GTRADE_DELEGATE_CACHE_SECONDS", "60"))
        self._delegate_cache = (
            Web3.to_checksum_address(trader_address),
            Web3.to_checksum_address(agent_address),
            time.monotonic() + max(0.0, ttl),
        )

    def _prewarm_execution_cache(self, web3: Web3, trader_address: str) -> None:
        self._events(trader_address).start()
        self._prewarm_delegate(web3, trader_address)
        try:
            sender = self._agent().address if os.getenv("GTRADE_DELEGATED", "0") == "1" else trader_address
            self._prewarm_nonce(web3, sender)
            self._cached_fee_params(web3, aggressive=False)
        except Exception:
            pass

    def _prewarm_delegate(self, web3: Web3, trader_address: str) -> None:
        if os.getenv("GTRADE_DELEGATED", "0") != "1":
            return
        try:
            agent = self._agent()
            agent_address = Web3.to_checksum_address(agent.address)
            if self._delegate_is_cached(trader_address, agent_address):
                return
            trading = self._trading(web3)
            current_delegate = Web3.to_checksum_address(trading.functions.getTradingDelegate(trader_address).call())
            if current_delegate == agent_address:
                self._cache_delegate(trader_address, agent_address)
        except Exception:
            pass

    def _next_nonce(self, web3: Web3, address: str, *, fresh: bool = False) -> tuple[int, dict[str, Any]]:
        checksum = Web3.to_checksum_address(address)
        use_cache = os.getenv("GTRADE_NONCE_CACHE", "1") == "1"
        with self._tx_cache_lock:
            if use_cache and not fresh and checksum in self._nonce_cache:
                nonce = self._nonce_cache[checksum]
                self._nonce_cache[checksum] = nonce + 1
                return nonce, {"elapsedMs": 0.0, "source": "cache", "cacheHit": True}

            started = time.perf_counter()
            nonce = web3.eth.get_transaction_count(checksum, "pending")
            elapsed = _elapsed_ms(started)
            if use_cache:
                self._nonce_cache[checksum] = nonce + 1
            return nonce, {"elapsedMs": elapsed, "source": "rpc", "cacheHit": False}

    def _prewarm_nonce(self, web3: Web3, address: str) -> None:
        if os.getenv("GTRADE_NONCE_CACHE", "1") != "1":
            return
        checksum = Web3.to_checksum_address(address)
        with self._tx_cache_lock:
            if checksum in self._nonce_cache:
                return
            nonce = web3.eth.get_transaction_count(checksum, "pending")
            self._nonce_cache[checksum] = nonce

    def _invalidate_nonce(self, address: str) -> None:
        with self._tx_cache_lock:
            self._nonce_cache.pop(Web3.to_checksum_address(address), None)

    def _cached_fee_params(self, web3: Web3, *, aggressive: bool = False) -> tuple[dict[str, int], dict[str, Any]]:
        use_cache = os.getenv("GTRADE_FEE_CACHE", "1") == "1" and not aggressive
        ttl = max(0.0, float(os.getenv("GTRADE_FEE_CACHE_MS", "5000")) / 1000)
        now = time.monotonic()
        with self._tx_cache_lock:
            if use_cache and self._fee_cache and now < self._fee_cache[0]:
                return dict(self._fee_cache[1]), {"elapsedMs": 0.0, "source": "cache", "cacheHit": True}

        started = time.perf_counter()
        params = _fee_params(web3, aggressive=aggressive)
        elapsed = _elapsed_ms(started)
        if use_cache:
            with self._tx_cache_lock:
                self._fee_cache = (time.monotonic() + ttl, dict(params))
        return params, {"elapsedMs": elapsed, "source": "rpc", "cacheHit": False}

    def _invalidate_fee_cache(self) -> None:
        with self._tx_cache_lock:
            self._fee_cache = None

    @staticmethod
    def _agent() -> Any:
        load_dotenv(ROOT / ".env")
        value = os.getenv("GTRADE_AGENT_PK")
        if not value:
            raise GTradeWalletError("GTRADE_AGENT_PK missing in root .env")
        key = value.strip().strip('"').strip("'")
        return Account.from_key(key if key.startswith("0x") else f"0x{key}")

    def _events(self, address: str) -> GTradeEventStream:
        checksum = Web3.to_checksum_address(address)
        if self._event_stream is None or self._event_stream.owner != checksum.lower():
            self._event_stream = GTradeEventStream(checksum)
        return self._event_stream


def _position_public(
    item: dict[str, Any],
    pair_names: dict[int, str],
    prices: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    trade = item["trade"]
    pair_index = int(trade["pairIndex"])
    pair = normalize_pair(pair_names.get(pair_index, str(pair_index)))
    entry = Decimal(str(trade["openPrice"])) / Decimal(10**10)
    collateral = Decimal(str(trade["collateralAmount"])) / Decimal(10**6)
    leverage = Decimal(str(trade["leverage"])) / Decimal(1000)
    side = "long" if trade["long"] else "short"
    mark = Decimal(str((prices.get(pair) or {}).get("mid") or entry))
    direction = Decimal(1) if side == "long" else Decimal(-1)
    pnl = ((mark - entry) / entry) * direction * collateral * leverage if entry else Decimal(0)
    return {
        "pair": pair,
        "pairId": pair_index,
        "idx": int(trade["index"]),
        "side": side,
        "entry": float(entry),
        "mark": float(mark),
        "collateral": float(collateral),
        "leverage": float(leverage),
        "pnl": float(pnl),
        "roePct": float((pnl / collateral) * Decimal(100)) if collateral else 0.0,
        "openedAt": int(item.get("tradeInfo", {}).get("lastOiUpdateTs") or time.time()),
        "closeAvailable": True,
    }


def _trade_from_event_args(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict) or hasattr(value, "get"):
        return {
            name: _plain_value(value.get(name))
            for name, _ in TRADE_FIELDS
            if value.get(name) is not None
        }
    if isinstance(value, (list, tuple)):
        return {
            name: _plain_value(value[index])
            for index, (name, _) in enumerate(TRADE_FIELDS)
            if index < len(value)
        }
    return {}


def _plain_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return _hex(value)
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    if isinstance(value, dict) or hasattr(value, "items"):
        return {str(key): _plain_value(item) for key, item in value.items()}
    return value


def _hex(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "hex"):
        raw = value.hex()
        return raw if str(raw).startswith("0x") else f"0x{raw}"
    return str(value)


def _normalize_tx_hash(value: str | None) -> str:
    if not value:
        return ""
    return "0x" + str(value).lower().removeprefix("0x")


def _topic_address(value: str) -> str:
    return "0x" + Web3.to_checksum_address(value).lower().removeprefix("0x").rjust(64, "0")


def _topic_u256(value: int | None) -> str:
    if value is None:
        return ""
    return "0x" + hex(int(value))[2:].rjust(64, "0")


def _tx_succeeded(tx: dict[str, Any]) -> bool:
    return int(tx.get("status", 0)) == 1


def _fee_params(web3: Web3, *, aggressive: bool = False) -> dict[str, int]:
    latest = web3.eth.get_block("latest")
    base_fee = int(latest.get("baseFeePerGas") or web3.eth.gas_price)
    priority = int(os.getenv("GTRADE_PRIORITY_FEE_WEI", "0"))
    if os.getenv("GTRADE_USE_RPC_PRIORITY_FEE", "0") == "1":
        try:
            priority = max(priority, int(web3.eth.max_priority_fee))
        except Exception:
            pass
    priority = max(priority, 50_000_000 if aggressive else 10_000_000)
    multiplier = Decimal("3.0") if aggressive else Decimal("2.0")
    return {
        "maxFeePerGas": int(Decimal(base_fee) * multiplier) + priority,
        "maxPriorityFeePerGas": priority,
    }


def _is_base_fee_error(exc: Exception) -> bool:
    return bool(re.search(r"max fee per gas less than block base fee|baseFee", str(exc), re.IGNORECASE))


def _is_nonce_error(exc: Exception) -> bool:
    return bool(
        re.search(
            r"nonce too low|nonce has already been used|invalid transaction nonce|account sequence mismatch",
            str(exc),
            re.IGNORECASE,
        )
    )


def _is_known_transaction_error(exc: Exception) -> bool:
    return bool(re.search(r"already known|already imported|known transaction", str(exc), re.IGNORECASE))


def _usdc_units(value: Decimal) -> int:
    return int((value * Decimal(10**6)).to_integral_value(rounding=ROUND_DOWN))


def _price_units(value: Decimal) -> int:
    return int((value * Decimal(10**10)).to_integral_value(rounding=ROUND_UP))


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _fixed_gas(label: str) -> int:
    defaults = {
        "approve": 100_000,
        "open": 2_300_000,
        "close": 2_000_000,
        "setDelegate": 120_000,
    }
    key = f"GTRADE_{label.upper()}_GAS"
    return int(os.getenv(key, str(defaults.get(label, 2_500_000))))
