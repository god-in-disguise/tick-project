from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import requests


TERMINAL_POSITION_STATUSES = {"open", "closed", "liquidated", "unknown"}


class CanaryError(RuntimeError):
    pass


@dataclass
class StepTimer:
    started_at: float

    @classmethod
    def start(cls) -> "StepTimer":
        return cls(started_at=time.perf_counter())

    def ms(self) -> float:
        return round((time.perf_counter() - self.started_at) * 1000, 1)


def main() -> None:
    args = parse_args()
    client = ApiClient(args.base_url, timeout=args.http_timeout)
    timeline: list[dict[str, Any]] = []
    run_id = uuid.uuid4().hex[:12]

    try:
        health = timed(timeline, "health", lambda: client.get("/health"))
        session = timed(
            timeline,
            "dev_session",
            lambda: client.post("/api/auth/dev-session", {"userId": args.user_id}),
        )
        token = session["token"]
        auth = {"Authorization": f"Bearer {token}"}

        deposit = timed(timeline, "deposit_address", lambda: client.get("/api/wallet/deposit-address", headers=auth))
        balances = optional_timed(timeline, "wallet_balances", lambda: client.get("/api/wallet/balances", headers=auth))
        quote = timed(
            timeline,
            "quote",
            lambda: client.post(
                "/api/trade/quote",
                {
                    "market": args.market,
                    "side": args.side,
                    "ticketUsd": str(args.ticket_usd),
                    "leverage": str(args.leverage),
                    "maxLossUsd": str(args.max_loss_usd) if args.max_loss_usd is not None else None,
                },
                headers=auth,
            ),
        )
        if not quote["openingAllowed"]:
            raise CanaryError(f"quote was not openingAllowed: {quote}")

        open_response = timed(
            timeline,
            "open_accept",
            lambda: client.post(
                "/api/trade/open",
                {"quoteId": quote["quoteId"], "idempotencyKey": f"canary-open-{run_id}"},
                headers=auth,
            ),
        )
        position_id = open_response["position"]["id"]
        open_execution_id = open_response["executionAttempt"]["id"]

        open_state = wait_for_position(
            client,
            auth,
            position_id=position_id,
            desired_status="open",
            timeout_seconds=args.open_timeout,
            poll_seconds=args.poll_seconds,
        )
        timeline.append({"step": "open_visible", **open_state})

        close_response = None
        close_state = None
        close_execution_id = None
        if args.close and open_state["status"] == "open":
            if args.hold_seconds > 0:
                time.sleep(args.hold_seconds)
            close_response = timed(
                timeline,
                "close_accept",
                lambda: client.post(
                    "/api/trade/close",
                    {"positionId": position_id, "idempotencyKey": f"canary-close-{run_id}"},
                    headers=auth,
                ),
            )
            close_execution_id = close_response["executionAttempt"]["id"]
            close_state = wait_for_position(
                client,
                auth,
                position_id=position_id,
                desired_status="closed",
                timeout_seconds=args.close_timeout,
                poll_seconds=args.poll_seconds,
                terminal_statuses={"closed", "liquidated", "unknown"},
            )
            timeline.append({"step": "close_done", **close_state})
        elif args.close:
            timeline.append(
                {
                    "step": "close_skipped",
                    "reason": f"position did not reach open status, current={open_state['status']}",
                }
            )

        state = timed(timeline, "final_state", lambda: client.get("/api/state", headers=auth))
        database = None
        if args.db_url:
            database = optional_timed(
                timeline,
                "database_details",
                lambda: {
                    "ok": True,
                    **load_database_details(
                        args.db_url,
                        execution_ids=[item for item in [open_execution_id, close_execution_id] if item],
                        position_id=position_id,
                    ),
                },
            )
        output = {
            "ok": True,
            "runId": run_id,
            "backend": args.base_url,
            "health": health,
            "wallet": {
                "address": session.get("walletAddress"),
                "depositAddress": deposit.get("address"),
                "balances": balances,
            },
            "quote": compact_quote(quote),
            "open": {
                "executionAttemptId": open_execution_id,
                "positionId": position_id,
                "acceptedStatus": open_response["executionAttempt"]["status"],
                "visibleStatus": open_state["status"],
                "elapsedMs": open_state["elapsedMs"],
            },
            "close": compact_close(close_response, close_state),
            "latestState": compact_state(state),
            "database": database,
            "timeline": timeline,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "timeline": timeline,
                },
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(1) from exc


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def get(self, path: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        response = self.session.get(f"{self.base_url}{path}", headers=headers or {}, timeout=self.timeout)
        return parse_response(response)

    def post(self, path: str, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        response = self.session.post(f"{self.base_url}{path}", json=payload, headers=headers or {}, timeout=self.timeout)
        return parse_response(response)


def parse_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {"body": response.text}
    if response.status_code >= 400:
        raise CanaryError(f"{response.request.method} {response.url} -> {response.status_code}: {payload}")
    if not isinstance(payload, dict):
        raise CanaryError(f"{response.request.method} {response.url} returned non-object JSON")
    return payload


def timed(timeline: list[dict[str, Any]], step: str, fn):
    timer = StepTimer.start()
    try:
        result = fn()
    except Exception as exc:
        timeline.append({"step": step, "ok": False, "elapsedMs": timer.ms(), "error": f"{type(exc).__name__}: {exc}"})
        raise
    timeline.append({"step": step, "ok": True, "elapsedMs": timer.ms()})
    return result


def optional_timed(timeline: list[dict[str, Any]], step: str, fn):
    timer = StepTimer.start()
    try:
        result = fn()
    except Exception as exc:
        timeline.append({"step": step, "ok": False, "elapsedMs": timer.ms(), "error": f"{type(exc).__name__}: {exc}"})
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    timeline.append({"step": step, "ok": True, "elapsedMs": timer.ms()})
    return result


def wait_for_position(
    client: ApiClient,
    headers: dict[str, str],
    *,
    position_id: str,
    desired_status: str,
    timeout_seconds: float,
    poll_seconds: float,
    terminal_statuses: set[str] | None = None,
) -> dict[str, Any]:
    terminal_statuses = terminal_statuses or TERMINAL_POSITION_STATUSES
    started = time.perf_counter()
    last_position: dict[str, Any] | None = None
    last_execution: dict[str, Any] | None = None
    polls = 0
    while time.perf_counter() - started <= timeout_seconds:
        polls += 1
        state = client.get("/api/state", headers=headers)
        last_position = find_by_id(state.get("positions", []), position_id)
        if last_position is not None:
            last_execution = newest_execution_for_position(state.get("executionAttempts", []), state.get("intents", []), position_id)
            status = last_position["status"]
            if status == desired_status or status in terminal_statuses - {desired_status}:
                return {
                    "status": status,
                    "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
                    "polls": polls,
                    "position": compact_position(last_position),
                    "execution": compact_execution(last_execution),
                }
        time.sleep(poll_seconds)

    return {
        "status": last_position["status"] if last_position else "missing",
        "elapsedMs": round((time.perf_counter() - started) * 1000, 1),
        "polls": polls,
        "position": compact_position(last_position),
        "execution": compact_execution(last_execution),
        "timedOut": True,
        "hint": "If execution stayed created/opening, TICK_REAL_EXECUTION_ENABLED is probably false or the worker is not running.",
    }


def newest_execution_for_position(executions: list[dict[str, Any]], intents: list[dict[str, Any]], position_id: str) -> dict[str, Any] | None:
    intent_ids = {item["id"] for item in intents if item.get("positionId") == position_id}
    candidates = [item for item in executions if item.get("tradeIntentId") in intent_ids]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.get("createdAt", ""), reverse=True)[0]


def find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("id") == item_id), None)


def compact_quote(quote: dict[str, Any]) -> dict[str, Any]:
    return {
        "quoteId": quote["quoteId"],
        "venue": quote["venue"],
        "market": quote["market"],
        "side": quote["side"],
        "ticketUsd": quote["ticketUsd"],
        "leverage": quote["leverage"],
        "notionalUsd": quote["notionalUsd"],
        "estimatedRoundTripCostUsd": quote["estimatedRoundTripCostUsd"],
        "liquidationPrice": quote["liquidationPrice"],
        "stopLossPrice": quote["stopLossPrice"],
        "expiresAt": quote["expiresAt"],
    }


def compact_close(response: dict[str, Any] | None, state: dict[str, Any] | None) -> dict[str, Any] | None:
    if response is None:
        return None
    return {
        "executionAttemptId": response["executionAttempt"]["id"],
        "acceptedStatus": response["executionAttempt"]["status"],
        "visibleStatus": state["status"] if state else None,
        "elapsedMs": state["elapsedMs"] if state else None,
        "execution": state.get("execution") if state else None,
    }


def compact_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "positions": [compact_position(item) for item in state.get("positions", [])[:5]],
        "executions": [compact_execution(item) for item in state.get("executionAttempts", [])[:5]],
        "reconciliations": state.get("reconciliations", [])[:5],
    }


def compact_position(position: dict[str, Any] | None) -> dict[str, Any] | None:
    if position is None:
        return None
    return {
        "id": position["id"],
        "market": position["market"],
        "side": position["side"],
        "status": position["status"],
        "ticketUsd": position["ticketUsd"],
        "leverage": position["leverage"],
        "notionalUsd": position["notionalUsd"],
        "entryPrice": position["entryPrice"],
        "stopLossPrice": position["stopLossPrice"],
        "liquidationPrice": position["liquidationPrice"],
    }


def compact_execution(execution: dict[str, Any] | None) -> dict[str, Any] | None:
    if execution is None:
        return None
    return {
        "id": execution["id"],
        "action": execution["action"],
        "status": execution["status"],
        "txHash": execution["txHash"],
        "createdAt": execution["createdAt"],
        "updatedAt": execution["updatedAt"],
    }


def load_database_details(db_url: str, *, execution_ids: list[str], position_id: str) -> dict[str, Any]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise CanaryError("psycopg is required for --db-url timing inspection") from exc

    with psycopg.connect(db_url, row_factory=dict_row) as connection:
        executions = connection.execute(
            """
            select id, action, status, tx_hash, nonce, gas_cost_native, error, payload, created_at, updated_at
            from execution_attempts
            where id = any(%s)
            order by created_at asc
            """,
            (execution_ids,),
        ).fetchall()
        positions = connection.execute(
            """
            select id, status, venue_position_id, entry_price, stop_loss_price, liquidation_price,
                   payload, created_at, updated_at, opened_at, closed_at
            from positions
            where id = %s
            """,
            (position_id,),
        ).fetchall()
        reconciliations = connection.execute(
            """
            select id, status, venue_realized_pnl_usd, wallet_delta_usd, difference_usd, payload, created_at, updated_at
            from reconciliations
            where position_id = %s
            order by created_at asc
            """,
            (position_id,),
        ).fetchall()
    return {
        "executions": [json_safe(row) for row in executions],
        "positions": [json_safe(row) for row in positions],
        "reconciliations": [json_safe(row) for row in reconciliations],
    }


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one TICK backend API canary through quote/open/close.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--user-id", default=f"canary-{int(time.time())}")
    parser.add_argument("--market", default="BTCDEGEN/USD")
    parser.add_argument("--side", choices=["long", "short"], default="long")
    parser.add_argument("--ticket-usd", type=Decimal, default=Decimal("10"))
    parser.add_argument("--leverage", type=Decimal, default=Decimal("100"))
    parser.add_argument("--max-loss-usd", type=Decimal, default=Decimal("10"))
    parser.add_argument("--hold-seconds", type=float, default=3.0)
    parser.add_argument("--open-timeout", type=float, default=20.0)
    parser.add_argument("--close-timeout", type=float, default=20.0)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--http-timeout", type=float, default=10.0)
    parser.add_argument("--db-url", default=os.getenv("CANARY_DATABASE_URL", ""))
    parser.add_argument("--no-close", action="store_false", dest="close")
    parser.set_defaults(close=True)
    return parser.parse_args()


if __name__ == "__main__":
    main()
