from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import psycopg

from tick_mvp.core.config import Settings


LOGGER = logging.getLogger("tick.market-history")
RETENTION_HOURS = 24
FLUSH_SECONDS = 1.0
PRUNE_SECONDS = 10 * 60
QUEUE_BATCH_LIMIT = 20_000


@dataclass(slots=True)
class PriceBar:
    venue: str
    market: str
    bucket_second: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    sample_count: int
    first_sequence: int
    last_sequence: int
    source: str

    @classmethod
    def from_tick(cls, tick: dict[str, Any]) -> PriceBar:
        price = Decimal(str(tick["price"]))
        sequence = int(tick["sequence"])
        return cls(
            venue=str(tick["venue"]),
            market=str(tick["market"]),
            bucket_second=int(float(tick["receivedAt"])),
            open=price,
            high=price,
            low=price,
            close=price,
            sample_count=1,
            first_sequence=sequence,
            last_sequence=sequence,
            source=str(tick["source"]),
        )

    def add(self, tick: dict[str, Any]) -> None:
        price = Decimal(str(tick["price"]))
        sequence = int(tick["sequence"])
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        if sequence >= self.last_sequence:
            self.close = price
            self.last_sequence = sequence
        self.first_sequence = min(self.first_sequence, sequence)
        self.sample_count += 1


class PostgresMarketHistory:
    """Batches shared market observations into durable one-second bars."""

    def __init__(self, settings: Settings) -> None:
        self._database_url = settings.database_url
        self._queue: queue.Queue[list[dict[str, Any]]] = queue.Queue(
            maxsize=QUEUE_BATCH_LIMIT
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._dropped_batches = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="market-history",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def record(self, observations: list[dict[str, Any]]) -> None:
        if not observations:
            return
        try:
            self._queue.put_nowait(observations)
        except queue.Full:
            self._dropped_batches += 1
            if self._dropped_batches == 1 or self._dropped_batches % 100 == 0:
                LOGGER.error(
                    "Market history queue full; droppedBatches=%s",
                    self._dropped_batches,
                )

    def bars(self, *, venue: str, market: str, window_seconds: int) -> list[dict[str, Any]]:
        query = """
            SELECT bucket_at, open, high, low, close, sample_count,
                   first_sequence, last_sequence, source
            FROM market_price_bars_1s
            WHERE venue = %s
              AND market = %s
              AND bucket_at >= now() - (%s * interval '1 second')
            ORDER BY bucket_at
        """
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (venue, market, window_seconds))
                rows = cursor.fetchall()
        return [
            {
                "bucketTs": bucket_at.timestamp(),
                "open": str(open_price),
                "high": str(high),
                "low": str(low),
                "close": str(close),
                "sampleCount": int(sample_count),
                "firstSeq": int(first_sequence),
                "lastSeq": int(last_sequence),
                "source": source,
            }
            for (
                bucket_at,
                open_price,
                high,
                low,
                close,
                sample_count,
                first_sequence,
                last_sequence,
                source,
            ) in rows
        ]

    def _run(self) -> None:
        pending: dict[tuple[str, str, int], PriceBar] = {}
        connection = None
        next_flush = time.monotonic() + FLUSH_SECONDS
        next_prune = time.monotonic() + PRUNE_SECONDS
        try:
            while not self._stop.is_set():
                timeout = max(0.05, min(0.25, next_flush - time.monotonic()))
                try:
                    observations = self._queue.get(timeout=timeout)
                except queue.Empty:
                    observations = []
                for tick in observations:
                    key = (
                        str(tick["venue"]),
                        str(tick["market"]),
                        int(float(tick["receivedAt"])),
                    )
                    bar = pending.get(key)
                    if bar is None:
                        pending[key] = PriceBar.from_tick(tick)
                    else:
                        bar.add(tick)

                now = time.monotonic()
                if now >= next_flush and pending:
                    connection = self._write(connection, list(pending.values()))
                    if connection is not None:
                        pending.clear()
                    next_flush = now + FLUSH_SECONDS
                if now >= next_prune:
                    connection = self._prune(connection)
                    next_prune = now + PRUNE_SECONDS

            while not self._queue.empty():
                try:
                    observations = self._queue.get_nowait()
                except queue.Empty:
                    break
                for tick in observations:
                    key = (
                        str(tick["venue"]),
                        str(tick["market"]),
                        int(float(tick["receivedAt"])),
                    )
                    bar = pending.get(key)
                    if bar is None:
                        pending[key] = PriceBar.from_tick(tick)
                    else:
                        bar.add(tick)
            if pending:
                connection = self._write(connection, list(pending.values()))
        finally:
            if connection is not None:
                connection.close()

    def _write(self, connection, bars: list[PriceBar]):
        connection = self._connection(connection)
        if connection is None:
            return None
        statement = """
            INSERT INTO market_price_bars_1s (
                venue, market, bucket_at, open, high, low, close,
                sample_count, first_sequence, last_sequence, source, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now()
            )
            ON CONFLICT (venue, market, bucket_at) DO UPDATE SET
                high = GREATEST(market_price_bars_1s.high, EXCLUDED.high),
                low = LEAST(market_price_bars_1s.low, EXCLUDED.low),
                close = CASE
                    WHEN EXCLUDED.last_sequence >= market_price_bars_1s.last_sequence
                    THEN EXCLUDED.close
                    ELSE market_price_bars_1s.close
                END,
                sample_count = market_price_bars_1s.sample_count + EXCLUDED.sample_count,
                first_sequence = LEAST(
                    market_price_bars_1s.first_sequence,
                    EXCLUDED.first_sequence
                ),
                last_sequence = GREATEST(
                    market_price_bars_1s.last_sequence,
                    EXCLUDED.last_sequence
                ),
                source = EXCLUDED.source,
                updated_at = now()
        """
        values = [
            (
                bar.venue,
                bar.market,
                datetime.fromtimestamp(bar.bucket_second, UTC),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.sample_count,
                bar.first_sequence,
                bar.last_sequence,
                bar.source,
            )
            for bar in bars
        ]
        try:
            with connection.cursor() as cursor:
                cursor.executemany(statement, values)
            connection.commit()
            return connection
        except Exception:
            LOGGER.exception("Could not persist %s market history bars", len(bars))
            connection.close()
            return None

    def _prune(self, connection):
        connection = self._connection(connection)
        if connection is None:
            return None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM market_price_bars_1s
                    WHERE bucket_at < now() - (%s * interval '1 hour')
                    """,
                    (RETENTION_HOURS,),
                )
            connection.commit()
            return connection
        except Exception:
            LOGGER.exception("Could not prune market history")
            connection.close()
            return None

    def _connection(self, connection):
        if connection is not None and not connection.closed:
            return connection
        try:
            return psycopg.connect(self._database_url)
        except Exception:
            LOGGER.exception("Could not connect market history writer to Postgres")
            return None
