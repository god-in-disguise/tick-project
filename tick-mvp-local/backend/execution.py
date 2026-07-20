from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from typing import Any

from .connectors.base import ConnectorError, VenueConnector
from .markets import MarketService
from .store import LocalStore


LOGGER = logging.getLogger("tick.execution")
QUOTE_TTL_SECONDS = float(os.getenv("TICK_QUOTE_TTL_SECONDS", "5"))
STALE_EXECUTION_SECONDS = float(os.getenv("TICK_STALE_EXECUTION_SECONDS", "120"))
MONITOR_INTERVAL_SECONDS = float(os.getenv("TICK_MONITOR_INTERVAL_SECONDS", "0.75"))
POSITION_ABSENT_CONFIRM_SECONDS = float(os.getenv("TICK_POSITION_ABSENT_CONFIRM_SECONDS", "1.0"))
BALANCE_RECONCILE_TIMEOUT_SECONDS = float(os.getenv("TICK_BALANCE_RECONCILE_TIMEOUT_SECONDS", "8"))
BALANCE_RECONCILE_POLL_SECONDS = float(os.getenv("TICK_BALANCE_RECONCILE_POLL_SECONDS", "0.35"))


class ExecutionError(Exception):
    pass


class ExecutionService:
    """One-wallet execution state machine shared by every venue connector."""

    def __init__(
        self,
        connector: VenueConnector,
        markets: MarketService,
        database_path: Path,
    ):
        self.connector = connector
        self.markets = markets
        self.store = LocalStore(database_path)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tick-execution")
        self._refresh_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tick-account-refresh")
        self._state_lock = threading.RLock()
        self._account: dict[str, Any] | None = None
        self._account_updated_at = 0.0
        self._running: set[str] = set()
        self._closed_pairs: set[str] = set()
        self._missing_positions: dict[str, float] = {}
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None

    def start(self) -> None:
        self.store.initialize()
        if self._monitor and self._monitor.is_alive():
            return
        self._stop.clear()
        self._monitor = threading.Thread(target=self._monitor_loop, name="tick-execution-monitor", daemon=True)
        self._monitor.start()

    def stop(self) -> None:
        self._stop.set()
        if self._monitor:
            self._monitor.join(timeout=5)
        self._executor.shutdown(wait=True, cancel_futures=False)
        self._refresh_executor.shutdown(wait=True, cancel_futures=False)

    def quote(self, pair: str, side: str, ticket_usd: Decimal, leverage: Decimal) -> dict[str, Any]:
        started = time.perf_counter()
        started_at = time.time()
        try:
            estimate_started = time.perf_counter()
            estimate = self.connector.estimate_open(pair, side, ticket_usd, leverage)
            estimate_ms = _elapsed_ms(estimate_started)
        except ConnectorError as exc:
            raise ExecutionError(str(exc)) from exc

        market_started = time.perf_counter()
        opportunity = self.markets.find(estimate["pair"])
        market_ms = _elapsed_ms(market_started)
        activity_surplus = float((opportunity or {}).get("activitySurplusPct") or 0)
        tradability = float((opportunity or {}).get("tradability") or 0)
        tradeable = bool(opportunity) and not bool(opportunity.get("cooling")) and activity_surplus > 0 and tradability >= 24
        market_open = bool(estimate.get("marketOpen", True))
        local_override = market_open and not tradeable
        now = time.time()
        quote = {
            **estimate,
            "quoteId": uuid.uuid4().hex,
            "createdAt": now,
            "expiresAt": now + QUOTE_TTL_SECONDS,
            "openingAllowed": market_open,
            "marketTradeable": tradeable,
            "localTestOverride": local_override,
            "activitySurplusPct": activity_surplus,
            "tradability": tradability,
            "marketState": (opportunity or {}).get("feedLabel") or "Loading",
            "timing": {
                "startedAt": started_at,
                "createdAt": now,
                "estimateOpenMs": estimate_ms,
                "marketLookupMs": market_ms,
                "elapsedMs": _elapsed_ms(started),
            },
        }
        return self.store.create_quote(quote)

    def open(self, quote_id: str, idempotency_key: str) -> dict[str, Any]:
        api_started = time.perf_counter()
        api_started_at = time.time()
        if not quote_id:
            raise ExecutionError("quoteId is required")
        if not idempotency_key:
            raise ExecutionError("idempotencyKey is required")

        existing = self.store.get_execution_by_idempotency(idempotency_key)
        if existing is not None:
            return existing

        quote = self.store.get_quote(quote_id)
        if quote is None:
            raise ExecutionError("quote not found")
        if float(quote["expiresAt"]) < time.time():
            raise ExecutionError("quote expired")
        if not quote.get("openingAllowed"):
            raise ExecutionError("market is watching; opening is not allowed")

        with self._state_lock:
            existing = self.store.get_execution_by_idempotency(idempotency_key)
            if existing is not None:
                return existing
            active = self.store.active_execution()
            if active and active["status"] in {"created", "opening", "open", "closing", "unknown"}:
                raise ExecutionError(f"one-position loop is busy: {active['status']}")

            account = self._cached_account()
            if account and account.get("positions"):
                raise ExecutionError("one position is already open")

            execution = {
                "id": uuid.uuid4().hex,
                "idempotencyKey": idempotency_key,
                "action": "open",
                "venue": self.connector.name,
                "pair": quote["pair"],
                "side": quote["side"],
                "quoteId": quote_id,
                "ticketUsd": quote["ticketUsd"],
                "leverage": quote["leverage"],
                "status": "created",
                "balanceBefore": _usdc_balance(account) if account else None,
                "position": self._optimistic_position(quote),
            }
            persisted, created = self.store.create_execution(execution)
            if created:
                self._event(
                    persisted["id"],
                    "api_accepted",
                    {
                        "endpoint": "open",
                        "receivedAt": api_started_at,
                        "returnedAt": time.time(),
                        "elapsedMs": _elapsed_ms(api_started),
                        "quoteAgeMs": round((time.time() - float(quote["createdAt"])) * 1000, 1),
                    },
                )
                self._running.add(persisted["id"])
                self._executor.submit(self._run_open, persisted["id"], quote)
            return persisted

    def close(self, pair: str, idempotency_key: str) -> dict[str, Any]:
        api_started = time.perf_counter()
        api_started_at = time.time()
        if not idempotency_key:
            raise ExecutionError("idempotencyKey is required")
        existing = self.store.get_execution_by_idempotency(idempotency_key)
        if existing is not None:
            return existing

        normalized = pair.upper().replace("/", "-")
        with self._state_lock:
            existing = self.store.get_execution_by_idempotency(idempotency_key)
            if existing is not None:
                return existing
            active = self.store.active_execution()
            if active and active["status"] in {"created", "opening", "closing", "unknown"}:
                raise ExecutionError(f"position cannot close while execution is {active['status']}")

            account = self._cached_account() or self._account_snapshot(max_age=0)
            position = next((item for item in account.get("positions", []) if item["pair"] == normalized), None)
            if position is None and active and active["action"] == "open" and active["status"] == "open":
                position = active.get("position")
            if position is None:
                if active and active["action"] == "open" and active["pair"] == normalized:
                    return self.store.update_execution(active["id"], status="closed", position=None)
                raise ExecutionError(f"no open position for {normalized}")

            execution = {
                "id": uuid.uuid4().hex,
                "idempotencyKey": idempotency_key,
                "action": "close",
                "venue": self.connector.name,
                "pair": normalized,
                "side": position.get("side"),
                "quoteId": None,
                "ticketUsd": None,
                "leverage": position.get("leverage"),
                "status": "created",
                "balanceBefore": _usdc_balance(account),
            }
            persisted, created = self.store.create_execution(execution)
            if created:
                self._event(
                    persisted["id"],
                    "api_accepted",
                    {
                        "endpoint": "close",
                        "receivedAt": api_started_at,
                        "returnedAt": time.time(),
                        "elapsedMs": _elapsed_ms(api_started),
                        "positionPair": normalized,
                        "positionIdx": position.get("idx"),
                    },
                )
                self._running.add(persisted["id"])
                self._executor.submit(self._run_close, persisted["id"], normalized, position)
            return persisted

    def state(self, *, force: bool = False) -> dict[str, Any]:
        account = self._account_snapshot(max_age=0 if force else 5, allow_stale=True)
        positions = [
            self._decorate_position(item)
            for item in account.get("positions") or []
            if item["pair"] not in self._closed_pairs
        ]
        active = self.store.active_execution()
        if (
            not positions
            and active
            and active["action"] == "open"
            and active["status"] in {"created", "opening", "open"}
            and active["pair"] not in self._closed_pairs
        ):
            optimistic = active.get("position")
            if optimistic:
                positions = [self._decorate_position(optimistic)]
        return {
            "venue": self.connector.name,
            "address": account.get("address") or self.connector.wallet_address(),
            "balances": account.get("balances") or {},
            "positions": positions,
            "execution": active,
            "lastExecution": self.store.latest_execution(),
            "localTestOverrideEnabled": True,
            "accountUpdatedAt": self._account_updated_at or None,
        }

    def execution(self, execution_id: str) -> dict[str, Any]:
        value = self.store.get_execution(execution_id)
        if value is None:
            raise ExecutionError("execution not found")
        return value

    def execution_timing(self, execution_id: str) -> dict[str, Any]:
        value = self.execution(execution_id)
        return _timing_report(value, self.store.execution_events(execution_id))

    def timings(self, limit: int = 20) -> list[dict[str, Any]]:
        return [
            _timing_report(execution, self.store.execution_events(execution["id"]))
            for execution in self.store.recent_executions(limit)
        ]

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.store.history(limit)

    def _run_open(self, execution_id: str, quote: dict[str, Any]) -> None:
        run_started = time.perf_counter()
        self._event(execution_id, "worker_started", {"action": "open", "at": time.time()})
        try:
            account_started = time.perf_counter()
            account = self._cached_account() or self._account_snapshot(max_age=0)
            self._event(
                execution_id,
                "account_checked",
                {
                    "elapsedMs": _elapsed_ms(account_started),
                    "positionCount": len(account.get("positions") or []),
                    "balanceUsdc": _usdc_balance(account),
                    "allowance": (account.get("balances") or {}).get("allowance"),
                },
            )
            if account.get("positions"):
                raise ExecutionError("one position is already open")
            balance = _usdc_balance(account)
            if balance is not None and balance < float(quote["ticketUsd"]):
                raise ExecutionError("USDC balance too low")
            allowance = (account.get("balances") or {}).get("allowance")
            if allowance not in {None, "max"} and float(allowance) < float(quote["ticketUsd"]) + 1:
                raise ExecutionError("USDC allowance is not ready")

            current = self.store.get_execution(execution_id)
            updates: dict[str, Any] = {"status": "opening"}
            if current and current.get("balanceBefore") is None:
                updates["balanceBefore"] = balance
            self.store.update_execution(execution_id, **updates)

            try:
                refresh_started = time.perf_counter()
                refreshed = self.connector.estimate_open(
                    quote["pair"],
                    quote["side"],
                    Decimal(str(quote["ticketUsd"])),
                    Decimal(str(quote["leverage"])),
                )
                self._event(
                    execution_id,
                    "quote_refreshed",
                    {
                        "elapsedMs": _elapsed_ms(refresh_started),
                        "originalPrice": quote["price"],
                        "refreshedPrice": refreshed["price"],
                        "moveBps": _price_move_bps(float(quote["price"]), float(refreshed["price"])),
                        "estimatedAllInCostUsd": refreshed.get("estimatedAllInCostUsd"),
                    },
                )
            except ConnectorError as exc:
                raise ExecutionError(str(exc)) from exc
            self._validate_quote_move(quote, refreshed)

            self._event(
                execution_id,
                "tx_submit_started",
                {
                    "action": "open",
                    "pair": quote["pair"],
                    "side": quote["side"],
                    "ticketUsd": quote["ticketUsd"],
                    "leverage": quote["leverage"],
                    "price": refreshed["price"],
                    "quoteAgeMs": round((time.time() - float(quote["createdAt"])) * 1000, 1),
                },
            )
            result = self.connector.open_position(
                quote["pair"],
                quote["side"],
                Decimal(str(quote["ticketUsd"])),
                Decimal(str(quote["leverage"])),
                refreshed,
            )
            self._event(execution_id, "tx_result", _compact_result_timing(result))
            tx_hash = ((result.get("tx") or {}).get("txHash"))
            position = result.get("position")
            if position:
                self._event(
                    execution_id,
                    "position_visible",
                    {
                        "elapsedMs": _elapsed_ms(run_started),
                        "pair": position.get("pair"),
                        "idx": position.get("idx"),
                        "entry": position.get("entry"),
                        "mark": position.get("mark"),
                    },
                )
                self.store.update_execution(
                    execution_id,
                    status="open",
                    txHash=tx_hash,
                    position=position,
                    result=result,
                )
                self._schedule_refresh_account()
            elif result.get("status") in {"pending_execution", "pending_index"}:
                current = self.store.get_execution(execution_id)
                next_status = "open" if current and current["status"] == "open" else "opening"
                self.store.update_execution(
                    execution_id,
                    status=next_status,
                    txHash=tx_hash,
                    position=(current or {}).get("position"),
                    result=result,
                )
            else:
                self.store.update_execution(
                    execution_id,
                    status="failed",
                    txHash=tx_hash,
                    result=result,
                    error=f"open ended in {result.get('status') or 'unknown'}",
                )
            if not position:
                self._refresh_account()
        except Exception as exc:
            LOGGER.exception("open execution failed")
            self._event(execution_id, "failed", {"action": "open", "error": f"{type(exc).__name__}: {exc}"})
            self.store.update_execution(execution_id, status="failed", error=f"{type(exc).__name__}: {exc}")
            self._safe_refresh_account()
        finally:
            with self._state_lock:
                self._running.discard(execution_id)

    def _run_close(self, execution_id: str, pair: str, position: dict[str, Any]) -> None:
        run_started = time.perf_counter()
        self._event(
            execution_id,
            "worker_started",
            {"action": "close", "at": time.time(), "pair": pair, "idx": position.get("idx")},
        )
        try:
            self._event(
                execution_id,
                "position_snapshot_used",
                {
                    "pair": pair,
                    "idx": position.get("idx"),
                    "source": "cached_position",
                    "postAnswerRevalidation": True,
                },
            )
            self._event(
                execution_id,
                "tx_submit_started",
                {
                    "action": "close",
                    "pair": pair,
                    "side": position.get("side"),
                    "idx": position.get("idx"),
                    "entry": position.get("entry"),
                    "mark": position.get("mark"),
                },
            )
            result = self.connector.close_position(pair, position)
            result["workerElapsedMs"] = _elapsed_ms(run_started)
            self._event(execution_id, "tx_result", _compact_result_timing(result))
            tx_hash = ((result.get("tx") or {}).get("txHash"))
            if result.get("closed") or result.get("status") in {"closed", "already_closed"}:
                self._finish_close(execution_id, position, result, tx_hash)
            elif result.get("status") in {"pending_execution", "pending_index"}:
                self.store.update_execution(execution_id, status="closing", txHash=tx_hash, result=result)
            else:
                self.store.update_execution(
                    execution_id,
                    status="failed",
                    txHash=tx_hash,
                    result=result,
                    error=f"close ended in {result.get('status') or 'unknown'}",
                )
        except Exception as exc:
            LOGGER.exception("close execution failed")
            self._event(execution_id, "failed", {"action": "close", "error": f"{type(exc).__name__}: {exc}"})
            self.store.update_execution(execution_id, status="unknown", error=f"{type(exc).__name__}: {exc}")
            self._safe_refresh_account()
        finally:
            with self._state_lock:
                self._running.discard(execution_id)

    def _finish_close(
        self,
        execution_id: str,
        position: dict[str, Any],
        result: dict[str, Any] | None,
        tx_hash: str | None,
    ) -> None:
        closing = self.store.get_execution(execution_id)
        close_balance_before = (closing or {}).get("balanceBefore")
        returned = ((result or {}).get("settlement") or {}).get("usdcSentToTrader")
        balance_after = (
            float(close_balance_before) + float(returned)
            if close_balance_before is not None and returned is not None
            else None
        )
        opening = self.store.latest_open_for_pair(position["pair"])
        balance_before = opening.get("balanceBefore") if opening else None
        realized = balance_after - balance_before if balance_after is not None and balance_before is not None else None
        completed_result = {
            **(result or {}),
            "position": position,
            "realizedWalletDelta": realized,
            "durationSeconds": max(0, int(time.time() - float((opening or {}).get("createdAt") or time.time()))),
        }
        if completed_result.get("status") == "external_closed":
            completed_result["status"] = _external_terminal_status(opening or {}, position, realized)
        if opening and opening["status"] == "open":
            self.store.update_execution(opening["id"], status="closed", position=position)
        with self._state_lock:
            self._closed_pairs.add(position["pair"])
            if self._account:
                self._account["positions"] = [
                    item for item in self._account.get("positions") or [] if item["pair"] != position["pair"]
                ]
                if balance_after is not None:
                    self._account.setdefault("balances", {})["usdc"] = balance_after
                self._account_updated_at = time.time()
        self.store.update_execution(
            execution_id,
            status="closed",
            balanceAfter=balance_after,
            realizedWalletDelta=realized,
            txHash=tx_hash,
            position=position,
            result=completed_result,
            error=None,
        )
        self._event(
            execution_id,
            "position_gone",
            {
                "balanceAfter": balance_after,
                "realizedWalletDelta": realized,
                "txHash": tx_hash,
                "pair": position.get("pair"),
                "idx": position.get("idx"),
            },
        )
        if balance_after is None:
            self._schedule_balance_reconcile(execution_id, completed_result, balance_before)

    def _monitor_loop(self) -> None:
        while not self._stop.is_set():
            self._safe_refresh_account()
            try:
                self._reconcile_pending()
            except Exception:
                LOGGER.exception("execution reconciliation failed")
            self._stop.wait(max(0.25, MONITOR_INTERVAL_SECONDS))

    def _reconcile_pending(self) -> None:
        account = self._account_snapshot(max_age=6)
        positions = account.get("positions") or []
        pending = self.store.pending_executions()
        self._reconcile_open_positions(account, positions, pending)
        self._repair_latest_closed_balance(account, positions, pending)
        now = time.time()
        for execution in pending:
            if execution["id"] in self._running:
                continue
            position = next((item for item in positions if item["pair"] == execution["pair"]), None)
            if execution["action"] == "open" and position:
                self._event(
                    execution["id"],
                    "reconciled_by_monitor",
                    {"status": "open", "pair": position.get("pair"), "idx": position.get("idx")},
                )
                self.store.update_execution(execution["id"], status="open", position=position)
                continue
            if execution["action"] == "close" and not position:
                previous = (execution.get("result") or {}).get("position") or {
                    "pair": execution["pair"],
                    "side": execution.get("side"),
                    "leverage": execution.get("leverage"),
                }
                self._event(execution["id"], "reconciled_by_monitor", {"status": "closed", "pair": execution["pair"]})
                self._finish_close(execution["id"], previous, execution.get("result"), execution.get("txHash"))
                continue
            age = now - float(execution["createdAt"])
            if age <= STALE_EXECUTION_SECONDS or execution["id"] in self._running:
                continue
            status = "failed"
            self.store.update_execution(
                execution["id"],
                status=status,
                error=f"{execution['action']} did not reconcile within {int(STALE_EXECUTION_SECONDS)} seconds",
            )

    def _reconcile_open_positions(
        self,
        account: dict[str, Any],
        positions: list[dict[str, Any]],
        pending: list[dict[str, Any]],
    ) -> None:
        pending_close_pairs = {
            execution["pair"]
            for execution in pending
            if execution["action"] == "close" and execution["status"] in {"created", "closing", "unknown"}
        }
        now = time.time()
        for opening in self.store.open_executions():
            if opening["id"] in self._running or opening["pair"] in pending_close_pairs:
                continue
            previous = opening.get("position") or {}
            gone_event = self._latest_position_event(opening, present=False)
            if gone_event is not None:
                self._event(
                    opening["id"],
                    "external_position_event",
                    {
                        "status": "gone",
                        "source": gone_event.get("source") or "backend_ws",
                        "name": gone_event.get("name"),
                        "currentBlock": gone_event.get("currentBlock"),
                        "pair": opening.get("pair"),
                        "idx": previous.get("idx"),
                    },
                )
                self._finish_external_position_gone(
                    opening,
                    account,
                    reason="venue_unregister_event",
                    external_event=gone_event,
                )
                self._missing_positions.pop(_position_key(opening), None)
                continue

            if _matching_position(positions, opening["pair"], previous):
                self._missing_positions.pop(_position_key(opening), None)
                continue

            missing_key = _position_key(opening)
            first_seen = self._missing_positions.get(missing_key)
            if first_seen is None:
                self._missing_positions[missing_key] = now
                self._event(
                    opening["id"],
                    "position_missing_observed",
                    {
                        "pair": opening.get("pair"),
                        "idx": previous.get("idx"),
                        "source": "account_snapshot",
                    },
                )
                continue
            if now - first_seen < POSITION_ABSENT_CONFIRM_SECONDS:
                continue

            self._finish_external_position_gone(
                opening,
                account,
                reason="position_absent_in_account_snapshot",
                external_event=None,
            )
            self._missing_positions.pop(missing_key, None)

    def _latest_position_event(self, execution: dict[str, Any], *, present: bool) -> dict[str, Any] | None:
        reader = getattr(self.connector, "latest_position_event", None)
        position = execution.get("position") or {}
        position_index = position.get("idx")
        if not callable(reader) or position_index is None:
            return None
        try:
            event = reader(
                execution["pair"],
                present=present,
                since=max(float(execution["createdAt"]), float(execution["updatedAt"]) - 1.0),
                position_index=int(position_index),
            )
        except Exception as exc:
            LOGGER.debug("position event lookup failed: %s", exc)
            return None
        return event

    def _finish_external_position_gone(
        self,
        opening: dict[str, Any],
        account: dict[str, Any],
        *,
        reason: str,
        external_event: dict[str, Any] | None,
    ) -> dict[str, Any]:
        current = self.store.get_execution(opening["id"])
        if current is None or current["status"] != "open":
            return current or opening

        position = current.get("position") or {
            "pair": current["pair"],
            "side": current.get("side"),
            "leverage": current.get("leverage"),
        }
        balance_before = current.get("balanceBefore")
        try:
            balance_after = self._fresh_usdc_balance()
        except Exception:
            balance_after = _usdc_balance(account)
        realized = (
            balance_after - float(balance_before)
            if balance_after is not None and balance_before is not None
            else None
        )
        terminal_status = _external_terminal_status(current, position, realized)
        completed_result = {
            "status": terminal_status,
            "closed": True,
            "position": position,
            "realizedWalletDelta": realized,
            "balanceReconciled": balance_after is not None,
            "finalizationSource": reason,
            "externalEvent": _compact_external_event(external_event),
            "durationSeconds": max(0, int(time.time() - float(current.get("createdAt") or time.time()))),
        }

        with self._state_lock:
            self._closed_pairs.add(position["pair"])
            if self._account:
                self._account["positions"] = [
                    item for item in self._account.get("positions") or [] if item["pair"] != position["pair"]
                ]
                if balance_after is not None:
                    self._account.setdefault("balances", {})["usdc"] = balance_after
                self._account_updated_at = time.time()

        updated = self.store.update_execution(
            current["id"],
            status="closed",
            balanceAfter=balance_after,
            realizedWalletDelta=realized,
            position=position,
            result=completed_result,
            error=None,
        )
        self._event(
            current["id"],
            "position_gone",
            {
                "status": terminal_status,
                "balanceAfter": balance_after,
                "realizedWalletDelta": realized,
                "pair": position.get("pair"),
                "idx": position.get("idx"),
                "source": reason,
            },
        )
        return updated

    def _event(self, execution_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        data = dict(payload or {})
        data.setdefault("at", time.time())
        self.store.add_event(execution_id, event_type, data)

    def _account_snapshot(self, *, max_age: float, allow_stale: bool = False) -> dict[str, Any]:
        with self._state_lock:
            current = self._account
            age = time.time() - self._account_updated_at
        if current is None or age > max_age:
            try:
                return self._refresh_account()
            except Exception as exc:
                if allow_stale and current is not None:
                    LOGGER.warning("account refresh failed; using cached account: %s", exc)
                    return {
                        **current,
                        "stale": True,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                raise
        return current

    def _cached_account(self) -> dict[str, Any] | None:
        with self._state_lock:
            return self._account

    def _refresh_account(self) -> dict[str, Any]:
        account = self.connector.account()
        with self._state_lock:
            self._account = account
            self._account_updated_at = time.time()
            open_pairs = {item["pair"] for item in account.get("positions") or []}
            self._closed_pairs.intersection_update(open_pairs)
        return account

    def _safe_refresh_account(self) -> None:
        try:
            self._refresh_account()
        except Exception as exc:
            LOGGER.warning("account refresh failed: %s", exc)

    def _schedule_refresh_account(self) -> None:
        try:
            self._refresh_executor.submit(self._safe_refresh_account)
        except RuntimeError:
            self._safe_refresh_account()

    def _schedule_balance_reconcile(
        self,
        execution_id: str,
        completed_result: dict[str, Any],
        balance_before: Any,
    ) -> None:
        try:
            self._refresh_executor.submit(
                self._reconcile_close_balance,
                execution_id,
                completed_result,
                balance_before,
            )
        except RuntimeError:
            self._reconcile_close_balance(execution_id, completed_result, balance_before)

    def _reconcile_close_balance(
        self,
        execution_id: str,
        completed_result: dict[str, Any],
        balance_before: Any,
    ) -> None:
        reconcile_started = time.perf_counter()
        try:
            closing = self.store.get_execution(execution_id)
            close_balance_before = (closing or {}).get("balanceBefore")
            exact_balance_after = self._wait_for_post_close_balance(
                close_balance_before,
                completed_result,
            )
            exact_realized = (
                exact_balance_after - float(balance_before)
                if exact_balance_after is not None and balance_before is not None
                else None
            )
            reconciled_result = {
                **completed_result,
                "realizedWalletDelta": exact_realized,
                "balanceReconciled": True,
            }
            self.store.update_execution(
                execution_id,
                balanceAfter=exact_balance_after,
                realizedWalletDelta=exact_realized,
                result=reconciled_result,
                error=None,
            )
            self._event(
                execution_id,
                "balance_reconciled",
                {
                    "elapsedMs": _elapsed_ms(reconcile_started),
                    "balanceAfter": exact_balance_after,
                    "realizedWalletDelta": exact_realized,
                },
            )
        except Exception as exc:
            LOGGER.warning("post-close balance reconciliation failed: %s", exc)
            self._event(
                execution_id,
                "balance_reconcile_failed",
                {"elapsedMs": _elapsed_ms(reconcile_started), "error": f"{type(exc).__name__}: {exc}"},
            )

    def _decorate_position(self, position: dict[str, Any]) -> dict[str, Any]:
        opening = self.store.latest_open_for_pair(position["pair"])
        quote = self.store.get_quote(opening["quoteId"]) if opening and opening.get("quoteId") else None
        opening_cost = float(position.get("estimatedOpenCostUsd") or (quote or {}).get("estimatedOpenCostUsd") or 0)
        closing_cost = float(position.get("estimatedCloseCostUsd") or (quote or {}).get("estimatedCloseCostUsd") or 0)
        gross_pnl = float(position.get("pnl") or 0)
        return {
            **position,
            "grossPnl": gross_pnl,
            "estimatedNetPnl": gross_pnl - opening_cost - closing_cost,
            "estimatedOpenCostUsd": opening_cost,
            "estimatedCloseCostUsd": closing_cost,
            "estimatedAllInCostUsd": opening_cost + closing_cost,
            "ticketUsd": float(position.get("ticketUsd") or (quote or {}).get("ticketUsd") or position.get("collateral") or 0),
            "estimatedLiquidationPrice": position.get("estimatedLiquidationPrice") or (quote or {}).get("estimatedLiquidationPrice"),
            "pnlEstimated": True,
        }

    def _fresh_usdc_balance(self) -> float | None:
        fast_balance = getattr(self.connector, "usdc_balance", None)
        if callable(fast_balance):
            value = fast_balance()
            with self._state_lock:
                if self._account is not None:
                    self._account.setdefault("balances", {})["usdc"] = value
            return float(value)
        return _usdc_balance(self._account_snapshot(max_age=0))

    def _wait_for_post_close_balance(
        self,
        close_balance_before: Any,
        completed_result: dict[str, Any],
    ) -> float | None:
        deadline = time.monotonic() + max(0.0, BALANCE_RECONCILE_TIMEOUT_SECONDS)
        last_balance: float | None = None
        should_wait_for_move = (
            _is_successful_close(completed_result)
            and close_balance_before is not None
        )
        while True:
            balance = self._fresh_usdc_balance()
            last_balance = balance
            if not should_wait_for_move or not _same_amount(balance, close_balance_before):
                return balance
            if time.monotonic() >= deadline:
                return last_balance
            time.sleep(max(0.05, BALANCE_RECONCILE_POLL_SECONDS))

    def _repair_latest_closed_balance(
        self,
        account: dict[str, Any],
        positions: list[dict[str, Any]],
        pending: list[dict[str, Any]],
    ) -> None:
        if positions or pending:
            return
        latest = self.store.latest_execution()
        if not latest or latest["action"] != "close" or latest["status"] != "closed":
            return
        result = latest.get("result") or {}
        if not _is_successful_close(result):
            return
        current_balance = _usdc_balance(account)
        if current_balance is None or _same_amount(current_balance, latest.get("balanceAfter")):
            return
        position = latest.get("position") or (result.get("position") or {})
        if not position.get("pair"):
            return
        opening = self.store.latest_open_for_pair(position["pair"])
        balance_before = opening.get("balanceBefore") if opening else None
        realized = current_balance - float(balance_before) if balance_before is not None else None
        repaired_result = {
            **result,
            "realizedWalletDelta": realized,
            "balanceReconciled": True,
            "balanceRepaired": True,
        }
        self.store.update_execution(
            latest["id"],
            balanceAfter=current_balance,
            realizedWalletDelta=realized,
            result=repaired_result,
            error=None,
        )
        self._event(
            latest["id"],
            "balance_repaired",
            {
                "balanceAfter": current_balance,
                "previousBalanceAfter": latest.get("balanceAfter"),
                "realizedWalletDelta": realized,
            },
        )

    @staticmethod
    def _optimistic_position(quote: dict[str, Any]) -> dict[str, Any]:
        return {
            "pair": quote["pair"],
            "pairId": None,
            "idx": None,
            "side": quote["side"],
            "entry": float(quote["price"]),
            "mark": float(quote["price"]),
            "collateral": float(quote["activeCollateralUsd"]),
            "leverage": float(quote["leverage"]),
            "pnl": 0.0,
            "roePct": 0.0,
            "openedAt": int(time.time()),
            "optimistic": True,
            "closeAvailable": False,
            "ticketUsd": float(quote["ticketUsd"]),
            "estimatedOpenCostUsd": float(quote.get("estimatedOpenCostUsd") or 0),
            "estimatedCloseCostUsd": float(quote.get("estimatedCloseCostUsd") or 0),
            "estimatedAllInCostUsd": float(quote.get("estimatedAllInCostUsd") or 0),
            "estimatedLiquidationPrice": quote.get("estimatedLiquidationPrice"),
        }

    @staticmethod
    def _validate_quote_move(quote: dict[str, Any], refreshed: dict[str, Any]) -> None:
        original_price = Decimal(str(quote["price"]))
        refreshed_price = Decimal(str(refreshed["price"]))
        move_bps = abs(refreshed_price - original_price) / original_price * Decimal(10000) if original_price else Decimal(99999)
        allowed_bps = Decimal(str(quote.get("slippageBps") or 0))
        if move_bps > allowed_bps:
            raise ExecutionError("quote moved beyond slippage tolerance")

        original_cost = Decimal(str(quote.get("estimatedAllInCostUsd") or 0))
        refreshed_cost = Decimal(str(refreshed.get("estimatedAllInCostUsd") or 0))
        if original_cost and refreshed_cost > original_cost * Decimal("1.10"):
            raise ExecutionError("estimated cost changed materially")


def _usdc_balance(account: dict[str, Any]) -> float | None:
    value = (account.get("balances") or {}).get("usdc")
    return float(value) if value is not None else None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _price_move_bps(old: float, new: float) -> float:
    return round(abs(new - old) / old * 10000, 4) if old else 0.0


def _matching_position(positions: list[dict[str, Any]], pair: str, previous: dict[str, Any]) -> dict[str, Any] | None:
    previous_idx = previous.get("idx")
    for position in positions:
        if position.get("pair") != pair:
            continue
        if previous_idx is None or position.get("idx") == previous_idx:
            return position
    return None


def _position_key(execution: dict[str, Any]) -> str:
    position = execution.get("position") or {}
    return f"{execution['id']}:{execution['pair']}:{position.get('idx')}"


def _external_terminal_status(
    execution: dict[str, Any],
    position: dict[str, Any],
    realized: float | None,
) -> str:
    if realized is None:
        return "external_closed"
    ticket = float(
        position.get("ticketUsd")
        or execution.get("ticketUsd")
        or position.get("collateral")
        or 0
    )
    if ticket > 0 and realized <= -(ticket * 0.90):
        return "liquidated"
    return "external_closed"


def _is_successful_close(result: dict[str, Any]) -> bool:
    tx = result.get("tx") or {}
    return (
        result.get("closed") is True
        and result.get("closeTxFailed") is not True
        and int(tx.get("status", 1)) == 1
    )


def _same_amount(left: Any, right: Any, *, tolerance: float = 0.000001) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


def _compact_external_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    position = event.get("position") or {}
    trade = position.get("trade") or {}
    return {
        "source": event.get("source") or "backend_ws",
        "name": event.get("name"),
        "receivedAt": event.get("receivedAt"),
        "currentBlock": event.get("currentBlock"),
        "pairIndex": trade.get("pairIndex"),
        "tradeIndex": trade.get("index"),
    }


def _compact_result_timing(result: dict[str, Any]) -> dict[str, Any]:
    tx = result.get("tx") or {}
    wait = result.get("wait") or {}
    return {
        "status": result.get("status"),
        "closed": result.get("closed"),
        "closeTxFailed": result.get("closeTxFailed"),
        "finalizationSource": result.get("finalizationSource"),
        "error": result.get("error"),
        "workerElapsedMs": result.get("workerElapsedMs"),
        "tx": tx,
        "wait": wait,
        "positionFound": bool(result.get("position")),
        "txHash": tx.get("txHash"),
    }


def _timing_report(execution: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    origin = float(execution["createdAt"])
    normalized_events = []
    for event in events:
        normalized_events.append(
            {
                **event,
                "offsetMs": round((float(event["createdAt"]) - origin) * 1000, 1),
            }
        )

    summary = {
        "apiAcceptedMs": _first_event_offset(normalized_events, "api_accepted"),
        "workerStartedMs": _first_event_offset(normalized_events, "worker_started"),
        "openingMs": _first_status_offset(normalized_events, "opening"),
        "openMs": _first_status_offset(normalized_events, "open"),
        "closedMs": _first_status_offset(normalized_events, "closed"),
        "positionVisibleMs": _first_event_offset(normalized_events, "position_visible"),
        "positionGoneMs": _first_event_offset(normalized_events, "position_gone"),
    }
    result = execution.get("result") or {}
    tx = result.get("tx") or _first_payload_value(normalized_events, "tx_result", "tx") or {}
    wait = result.get("wait") or _first_payload_value(normalized_events, "tx_result", "wait") or {}
    direct_log_wait = wait if wait.get("source") == "direct_rpc_log" else (wait.get("directLogWait") or {})
    direct_log_event = direct_log_wait.get("event") or {}
    return {
        "execution": execution,
        "summary": {
            **summary,
            "txElapsedMs": tx.get("elapsedMs"),
            "txSignMs": tx.get("signMs"),
            "txSendMs": tx.get("sendMs"),
            "txReceiptMs": tx.get("receiptMs"),
            "txHash": tx.get("txHash") or execution.get("txHash"),
            "blockNumber": tx.get("blockNumber"),
            "waitForVenueMs": wait.get("elapsedMs"),
            "waitSource": wait.get("source"),
            "waitPollCount": wait.get("pollCount"),
            "waitTimedOut": wait.get("timedOut"),
            "eventWaitMs": (wait.get("eventWait") or {}).get("elapsedMs"),
            "directLogWaitMs": direct_log_wait.get("elapsedMs"),
            "directLogTimedOut": direct_log_wait.get("timedOut"),
            "directLogTxHash": direct_log_event.get("transactionHash"),
            "directLogBlockNumber": direct_log_event.get("blockNumber"),
            "directLogOpen": direct_log_event.get("open"),
            "waitRaceWinner": (wait.get("race") or {}).get("winner"),
            "waitRaceElapsedMs": (wait.get("race") or {}).get("elapsedMs"),
            "restFallbackDelayMs": (wait.get("race") or {}).get("restFallbackDelayMs"),
            "totalMs": round((float(execution["updatedAt"]) - origin) * 1000, 1),
        },
        "events": normalized_events,
    }


def _first_event_offset(events: list[dict[str, Any]], event_type: str) -> float | None:
    event = next((item for item in events if item["eventType"] == event_type), None)
    return event["offsetMs"] if event else None


def _first_status_offset(events: list[dict[str, Any]], status: str) -> float | None:
    for event in events:
        payload = event.get("payload") or {}
        if payload.get("status") == status:
            return event["offsetMs"]
    return None


def _first_payload_value(events: list[dict[str, Any]], event_type: str, key: str) -> Any:
    event = next((item for item in events if item["eventType"] == event_type), None)
    if not event:
        return None
    return (event.get("payload") or {}).get(key)
