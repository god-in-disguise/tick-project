from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass, field
from typing import Any, Callable


LOGGER = logging.getLogger("tick.arbitrum.broadcast")
ROUTE_PRIMARY = "primary_rpc"
ROUTE_SEQUENCER = "direct_sequencer"
ROUTE_CHAIN = "chain_observed"
_URL_PATTERN = re.compile(r"https?://[^\s)]+")


class BroadcastError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        outcomes: dict[str, "RouteOutcome"] | None = None,
    ) -> None:
        super().__init__(message)
        self.outcomes = dict(outcomes or {})

    def all_routes_report_nonce_too_low(self) -> bool:
        routes = (ROUTE_PRIMARY, ROUTE_SEQUENCER)
        outcomes = [self.outcomes.get(route) for route in routes]
        return all(
            outcome is not None
            and outcome.status == "error"
            and "nonce too low" in (outcome.error or "").lower()
            for outcome in outcomes
        )


@dataclass(frozen=True, slots=True)
class RouteOutcome:
    route: str
    status: str
    elapsed_ms: float
    tx_hash: str | None = None
    error_type: str | None = None
    error: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "elapsedMs": self.elapsed_ms,
            "txHash": self.tx_hash,
            "errorType": self.error_type,
            "error": self.error,
        }


@dataclass(slots=True)
class BroadcastRace:
    expected_tx_hash: str
    started_at: float
    winner: str | None = None
    winner_elapsed_ms: float | None = None
    _outcomes: dict[str, RouteOutcome] = field(default_factory=dict)
    _futures: list[Future[RouteOutcome]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, outcome: RouteOutcome) -> None:
        with self._lock:
            self._outcomes[outcome.route] = outcome

    def add_future(self, future: Future[RouteOutcome]) -> None:
        self._futures.append(future)

    def select(self, outcome: RouteOutcome) -> None:
        with self._lock:
            if self.winner is None:
                self.winner = outcome.route
                self.winner_elapsed_ms = outcome.elapsed_ms

    def wait_for_outcomes(self, timeout: float) -> None:
        wait(self._futures, timeout=timeout)

    def payload(self) -> dict[str, Any]:
        with self._lock:
            outcomes = dict(self._outcomes)
            winner = self.winner
            winner_elapsed_ms = self.winner_elapsed_ms
        return {
            "method": "eth_sendRawTransaction",
            "expectedTxHash": self.expected_tx_hash,
            "winner": winner,
            "winnerElapsedMs": winner_elapsed_ms,
            "routes": {
                route: outcomes[route].payload() if route in outcomes else {"status": "pending"}
                for route in (ROUTE_PRIMARY, ROUTE_SEQUENCER)
            },
        }


class DualBroadcaster:
    """Race identical signed bytes without creating a second transaction."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="arbitrum-write")

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)

    def broadcast(
        self,
        *,
        raw_transaction: Any,
        expected_tx_hash: str,
        primary_web3: Any,
        sequencer_web3: Any,
    ) -> BroadcastRace:
        expected = _normalize_hash(expected_tx_hash)
        race = BroadcastRace(expected_tx_hash=expected, started_at=time.perf_counter())
        senders = {
            ROUTE_PRIMARY: lambda: primary_web3.eth.send_raw_transaction(raw_transaction),
            ROUTE_SEQUENCER: lambda: sequencer_web3.eth.send_raw_transaction(raw_transaction),
        }
        futures: dict[Future[RouteOutcome], str] = {}
        for route, sender in senders.items():
            future = self._executor.submit(_run_route, route, sender, expected, race.started_at)
            future.add_done_callback(lambda completed, current=race: _record_future(current, completed))
            race.add_future(future)
            futures[future] = route

        for future in as_completed(futures):
            outcome = future.result()
            if outcome.status == "accepted":
                race.select(outcome)
                return race

        if _transaction_exists(primary_web3.eth.get_transaction, expected):
            observed = RouteOutcome(
                route=ROUTE_CHAIN,
                status="accepted",
                elapsed_ms=_elapsed_ms(race.started_at),
                tx_hash=expected,
            )
            race.record(observed)
            race.select(observed)
            return race

        errors = "; ".join(
            f"{route}={outcome.error_type}: {outcome.error}"
            for route, outcome in sorted(race._outcomes.items())
        )
        raise BroadcastError(
            f"all Arbitrum write routes failed ({errors or 'unknown errors'})",
            outcomes=dict(race._outcomes),
        )


def _run_route(
    route: str,
    sender: Callable[[], Any],
    expected_tx_hash: str,
    race_started_at: float,
) -> RouteOutcome:
    try:
        returned_hash = _normalize_hash(sender())
        if returned_hash != expected_tx_hash:
            raise BroadcastError(f"{route} returned an unexpected transaction hash")
        outcome = RouteOutcome(
            route=route,
            status="accepted",
            elapsed_ms=_elapsed_ms(race_started_at),
            tx_hash=returned_hash,
        )
    except Exception as exc:
        outcome = RouteOutcome(
            route=route,
            status="error",
            elapsed_ms=_elapsed_ms(race_started_at),
            error_type=type(exc).__name__,
            error=_safe_error(exc),
        )
    LOGGER.info(
        "Arbitrum broadcast route completed route=%s status=%s elapsedMs=%.1f txHash=%s errorType=%s error=%s",
        outcome.route,
        outcome.status,
        outcome.elapsed_ms,
        outcome.tx_hash,
        outcome.error_type,
        outcome.error,
    )
    return outcome


def _record_future(race: BroadcastRace, future: Future[RouteOutcome]) -> None:
    try:
        race.record(future.result())
    except Exception:
        LOGGER.exception("Could not record Arbitrum broadcast route outcome")


def _transaction_exists(find_transaction: Callable[[str], Any], tx_hash: str) -> bool:
    try:
        return find_transaction(tx_hash) is not None
    except Exception:
        return False


def _normalize_hash(value: Any) -> str:
    if hasattr(value, "hex"):
        value = value.hex()
    normalized = str(value).lower()
    return normalized if normalized.startswith("0x") else f"0x{normalized}"


def _safe_error(exc: Exception) -> str:
    return _URL_PATTERN.sub("<rpc>", str(exc))[:300]


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 1)
