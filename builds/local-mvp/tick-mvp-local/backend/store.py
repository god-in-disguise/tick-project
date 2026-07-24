from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


ACTIVE_STATUSES = ("created", "opening", "open", "closing", "unknown")
PENDING_STATUSES = ("created", "opening", "closing", "unknown")


class LocalStore:
    """Small durable journal for the one-wallet canary."""

    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = FULL;

                CREATE TABLE IF NOT EXISTS route_quotes (
                    id TEXT PRIMARY KEY,
                    venue TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    side TEXT NOT NULL,
                    ticket_usd TEXT NOT NULL,
                    leverage TEXT NOT NULL,
                    price TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    action TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    side TEXT,
                    quote_id TEXT,
                    ticket_usd TEXT,
                    leverage TEXT,
                    status TEXT NOT NULL,
                    balance_before TEXT,
                    balance_after TEXT,
                    tx_hash TEXT,
                    realized_wallet_delta TEXT,
                    position_json TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS executions_status_idx
                    ON executions(status, updated_at DESC);
                CREATE INDEX IF NOT EXISTS executions_pair_idx
                    ON executions(pair, created_at DESC);

                CREATE TABLE IF NOT EXISTS execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(execution_id) REFERENCES executions(id)
                );
                """
            )

    def create_quote(self, quote: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO route_quotes (
                    id, venue, pair, side, ticket_usd, leverage, price,
                    expires_at, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote["quoteId"],
                    quote["venue"],
                    quote["pair"],
                    quote["side"],
                    str(quote["ticketUsd"]),
                    str(quote["leverage"]),
                    str(quote["price"]),
                    float(quote["expiresAt"]),
                    _dumps(quote),
                    float(quote["createdAt"]),
                ),
            )
        return quote

    def get_quote(self, quote_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM route_quotes WHERE id = ?",
                (quote_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def create_execution(self, execution: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        now = time.time()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO executions (
                        id, idempotency_key, action, venue, pair, side, quote_id,
                        ticket_usd, leverage, status, balance_before, position_json,
                        result_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        execution["id"],
                        execution["idempotencyKey"],
                        execution["action"],
                        execution["venue"],
                        execution["pair"],
                        execution.get("side"),
                        execution.get("quoteId"),
                        _optional_str(execution.get("ticketUsd")),
                        _optional_str(execution.get("leverage")),
                        execution["status"],
                        _optional_str(execution.get("balanceBefore")),
                        _dumps(execution["position"]) if execution.get("position") is not None else None,
                        _dumps(execution["result"]) if execution.get("result") is not None else None,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self.get_execution_by_idempotency(execution["idempotencyKey"])
                if existing is None:
                    raise
                return existing, False
        created = self.get_execution(execution["id"])
        if created is None:
            raise RuntimeError("execution was not persisted")
        self.add_event(created["id"], "created", execution)
        return created, True

    def update_execution(self, execution_id: str, **fields: Any) -> dict[str, Any]:
        if not fields:
            current = self.get_execution(execution_id)
            if current is None:
                raise KeyError(execution_id)
            return current

        allowed = {
            "status": "status",
            "balanceBefore": "balance_before",
            "balanceAfter": "balance_after",
            "txHash": "tx_hash",
            "realizedWalletDelta": "realized_wallet_delta",
            "position": "position_json",
            "result": "result_json",
            "error": "error",
        }
        assignments: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            column = allowed.get(key)
            if column is None:
                raise ValueError(f"unsupported execution field: {key}")
            assignments.append(f"{column} = ?")
            if key in {"position", "result"}:
                values.append(_dumps(value) if value is not None else None)
            elif key in {"balanceBefore", "balanceAfter", "realizedWalletDelta"}:
                values.append(_optional_str(value))
            else:
                values.append(value)
        assignments.append("updated_at = ?")
        values.extend([time.time(), execution_id])

        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE executions SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            if cursor.rowcount != 1:
                raise KeyError(execution_id)
        updated = self.get_execution(execution_id)
        if updated is None:
            raise KeyError(execution_id)
        self.add_event(execution_id, "updated", fields)
        return updated

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM executions WHERE id = ?",
                (execution_id,),
            ).fetchone()
        return _execution_row(row) if row else None

    def get_execution_by_idempotency(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM executions WHERE idempotency_key = ?",
                (key,),
            ).fetchone()
        return _execution_row(row) if row else None

    def active_execution(self) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM executions WHERE status IN ({placeholders}) ORDER BY updated_at DESC LIMIT 1",
                ACTIVE_STATUSES,
            ).fetchone()
        return _execution_row(row) if row else None

    def latest_execution(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM executions ORDER BY created_at DESC, updated_at DESC LIMIT 1"
            ).fetchone()
        return _execution_row(row) if row else None

    def pending_executions(self) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in PENDING_STATUSES)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM executions WHERE status IN ({placeholders}) ORDER BY created_at ASC",
                PENDING_STATUSES,
            ).fetchall()
        return [_execution_row(row) for row in rows]

    def open_executions(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM executions
                WHERE action = 'open' AND status = 'open'
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [_execution_row(row) for row in rows]

    def latest_open_for_pair(self, pair: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM executions
                WHERE action = 'open' AND pair = ? AND status IN ('open', 'closed')
                ORDER BY created_at DESC LIMIT 1
                """,
                (pair,),
            ).fetchone()
        return _execution_row(row) if row else None

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM executions
                WHERE status = 'closed'
                  AND (
                    action = 'close'
                    OR result_json LIKE '%"status":"external_closed"%'
                    OR result_json LIKE '%"status":"stop_loss_hit"%'
                    OR result_json LIKE '%"status":"liquidated"%'
                  )
                ORDER BY updated_at DESC LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [_execution_row(row) for row in rows]

    def recent_executions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM executions
                ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [_execution_row(row) for row in rows]

    def add_event(self, execution_id: str, event_type: str, payload: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO execution_events (execution_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (execution_id, event_type, _dumps(payload), time.time()),
            )

    def execution_events(self, execution_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, execution_id, event_type, payload_json, created_at
                FROM execution_events
                WHERE execution_id = ?
                ORDER BY id ASC
                """,
                (execution_id,),
            ).fetchall()
        return [_event_row(row) for row in rows]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _execution_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "idempotencyKey": row["idempotency_key"],
        "action": row["action"],
        "venue": row["venue"],
        "pair": row["pair"],
        "side": row["side"],
        "quoteId": row["quote_id"],
        "ticketUsd": _optional_float(row["ticket_usd"]),
        "leverage": _optional_float(row["leverage"]),
        "status": row["status"],
        "balanceBefore": _optional_float(row["balance_before"]),
        "balanceAfter": _optional_float(row["balance_after"]),
        "txHash": row["tx_hash"],
        "realizedWalletDelta": _optional_float(row["realized_wallet_delta"]),
        "position": json.loads(row["position_json"]) if row["position_json"] else None,
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": row["error"],
        "createdAt": float(row["created_at"]),
        "updatedAt": float(row["updated_at"]),
    }


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "executionId": row["execution_id"],
        "eventType": row["event_type"],
        "payload": json.loads(row["payload_json"]) if row["payload_json"] else None,
        "createdAt": float(row["created_at"]),
    }


def _dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
