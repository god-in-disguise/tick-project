from __future__ import annotations

import tempfile
import threading
import time
import unittest
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from backend.execution import ExecutionError, ExecutionService

from tests.fakes import FakeConnector, FakeMarkets


class ExecutionServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.connector = FakeConnector()
        self.service = ExecutionService(
            self.connector,
            FakeMarkets(),  # type: ignore[arg-type]
            Path(self.temp.name) / "tick.sqlite3",
        )
        self.service.start()

    def tearDown(self) -> None:
        self.service.stop()
        self.temp.cleanup()

    def test_idempotent_open_close_and_realized_result(self) -> None:
        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))
        opened = self.service.open(quote["quoteId"], "open-1")
        duplicate = self.service.open(quote["quoteId"], "open-1")
        self.assertEqual(opened["id"], duplicate["id"])

        opened = wait_for(lambda: self.service.execution(opened["id"]), "open")
        self.assertEqual(opened["txHash"], "0xopen")
        self.assertEqual(len(self.service.state()["positions"]), 1)

        with self.assertRaises(ExecutionError):
            second_quote = self.service.quote("BTC-USD", "short", Decimal("20"), Decimal("100"))
            self.service.open(second_quote["quoteId"], "open-2")

        closed = self.service.close("BTC-USD", "close-1")
        duplicate_close = self.service.close("BTC-USD", "close-1")
        self.assertEqual(closed["id"], duplicate_close["id"])
        closed = wait_for(lambda: self.service.execution(closed["id"]), "closed")
        self.assertEqual(closed["txHash"], "0xclose")
        self.assertEqual(closed["realizedWalletDelta"], 1.0)
        self.assertEqual(self.service.state()["positions"], [])
        self.assertEqual(self.service.state()["lastExecution"]["action"], "close")
        self.assertEqual(len(self.service.history()), 1)

    def test_open_acknowledges_with_optimistic_position_before_venue_io(self) -> None:
        release = threading.Event()
        original_open = self.connector.open_position

        def delayed_open(pair, side, ticket_usd, leverage, quote=None):
            release.wait(2)
            return original_open(pair, side, ticket_usd, leverage, quote)

        self.connector.open_position = delayed_open  # type: ignore[method-assign]
        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))

        started = perf_counter()
        execution = self.service.open(quote["quoteId"], "optimistic-open")
        elapsed = perf_counter() - started

        self.assertLess(elapsed, 0.25)
        self.assertEqual(execution["status"], "created")
        self.assertTrue(execution["position"]["optimistic"])
        self.assertTrue(self.service.state()["positions"][0]["optimistic"])

        release.set()
        wait_for(lambda: self.service.execution(execution["id"]), "open")

    def test_venue_open_market_remains_executable_when_tape_is_quiet(self) -> None:
        quiet = {
            **FakeMarkets.opportunity(),
            "feedLabel": "Live tape",
            "activitySurplusPct": -0.1,
            "tradability": 0.0,
        }
        self.service.markets.find = lambda pair: quiet  # type: ignore[method-assign]

        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))

        self.assertTrue(quote["openingAllowed"])
        self.assertFalse(quote["marketTradeable"])

    def test_pending_close_keeps_position_until_venue_disappears(self) -> None:
        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))
        opened = self.service.open(quote["quoteId"], "open-pending-close")
        wait_for(lambda: self.service.execution(opened["id"]), "open")

        self.connector.close_position = lambda pair, position=None: {  # type: ignore[method-assign]
            "status": "pending_execution",
            "closed": False,
            "tx": {"txHash": "0xpendingclose"},
        }
        closing = self.service.close("BTC-USD", "close-pending")
        closing = wait_for(lambda: self.service.execution(closing["id"]), "closing")
        self.assertEqual(closing["txHash"], "0xpendingclose")
        self.assertEqual(len(self.service.state()["positions"]), 1)

        with self.connector._lock:
            self.connector.position = None
            self.connector.balance = 101.0
        closed = wait_for(lambda: self.service.execution(closing["id"]), "closed", timeout=4.5)
        closed = wait_for_result(lambda: self.service.execution(closing["id"]))
        self.assertEqual(closed["realizedWalletDelta"], 1.0)
        self.assertEqual(self.service.state()["positions"], [])

    def test_stale_close_fails_open_for_a_safe_retry(self) -> None:
        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))
        opened = self.service.open(quote["quoteId"], "open-before-stale-close")
        wait_for(lambda: self.service.execution(opened["id"]), "open")

        self.connector.close_position = lambda pair, position=None: {  # type: ignore[method-assign]
            "status": "pending_execution",
            "closed": False,
            "tx": {"txHash": "0xstaleclose"},
        }
        closing = self.service.close("BTC-USD", "stale-close")
        wait_for(lambda: self.service.execution(closing["id"]), "closing")

        with patch("backend.execution.STALE_EXECUTION_SECONDS", -1):
            self.service._reconcile_pending()

        failed = self.service.execution(closing["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(len(self.service.state()["positions"]), 1)
        retry = self.service.close("BTC-USD", "retry-close")
        self.assertNotEqual(retry["id"], closing["id"])

    def test_close_worker_submits_first_then_recovers_disappeared_position(self) -> None:
        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))
        opened = self.service.open(quote["quoteId"], "open-before-external-close")
        wait_for(lambda: self.service.execution(opened["id"]), "open")

        with self.connector._lock:
            self.connector.position = None
            self.connector.balance = 90.0
        with self.service._state_lock:
            self.service._account_updated_at = 0.0

        submitted = threading.Event()

        def failed_submit_then_recovered(pair, position=None):
            submitted.set()
            return {
                "status": "external_closed",
                "closed": True,
                "closeTxFailed": True,
                "tx": {"txHash": "0xfailedclose", "status": 0},
                "position": position,
                "error": "close initiation transaction reverted; position is no longer visible",
                "finalizationSource": "position_absent_after_failed_close",
            }

        self.connector.close_position = failed_submit_then_recovered  # type: ignore[method-assign]
        closing = self.service.close("BTC-USD", "close-after-external-close")
        wait_for(lambda: self.service.execution(closing["id"]), "closed")
        closed = wait_for_result(lambda: self.service.execution(closing["id"]))

        self.assertTrue(submitted.is_set())
        self.assertEqual(closed["result"]["status"], "external_closed")
        self.assertEqual(closed["result"]["finalizationSource"], "position_absent_after_failed_close")
        self.assertEqual(closed["realizedWalletDelta"], -10.0)

    def test_successful_close_waits_for_post_close_balance_to_move(self) -> None:
        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))
        opened = self.service.open(quote["quoteId"], "open-before-delayed-balance")
        wait_for(lambda: self.service.execution(opened["id"]), "open")

        def delayed_balance_close(pair, position=None):
            with self.connector._lock:
                self.connector.position = None

            def settle_balance():
                time.sleep(0.15)
                with self.connector._lock:
                    self.connector.balance = 102.0

            threading.Thread(target=settle_balance, daemon=True).start()
            return {"status": "closed", "closed": True, "tx": {"txHash": "0xdelayedclose", "status": 1}}

        self.connector.close_position = delayed_balance_close  # type: ignore[method-assign]
        closing = self.service.close("BTC-USD", "close-delayed-balance")
        closed = wait_for(lambda: self.service.execution(closing["id"]), "closed")
        closed = wait_for_result(lambda: self.service.execution(closed["id"]), timeout=5)

        self.assertEqual(closed["realizedWalletDelta"], 2.0)
        self.assertEqual(closed["balanceAfter"], 102.0)
        self.assertTrue(closed["result"]["balanceReconciled"])

    def test_open_position_disappearance_is_caught_without_user_close(self) -> None:
        quote = self.service.quote("BTC-USD", "long", Decimal("20"), Decimal("100"))
        opened = self.service.open(quote["quoteId"], "open-before-liquidation")
        opened = wait_for(lambda: self.service.execution(opened["id"]), "open")

        with self.connector._lock:
            self.connector.position = None
            self.connector.balance = 80.0
        with self.service._state_lock:
            self.service._account_updated_at = 0.0

        finalized = wait_for(lambda: self.service.execution(opened["id"]), "closed", timeout=4.5)
        finalized = wait_for_result(lambda: self.service.execution(finalized["id"]))

        self.assertEqual(finalized["result"]["status"], "liquidated")
        self.assertEqual(finalized["result"]["finalizationSource"], "position_absent_in_account_snapshot")
        self.assertEqual(finalized["realizedWalletDelta"], -20.0)
        self.assertEqual(self.service.state()["positions"], [])


def wait_for(reader, status: str, timeout: float = 3.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = reader()
        if latest["status"] == status:
            return latest
        time.sleep(0.02)
    raise AssertionError(f"execution did not reach {status}: {latest}")


def wait_for_result(reader, timeout: float = 3.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = reader()
        if latest["realizedWalletDelta"] is not None:
            return latest
        time.sleep(0.02)
    raise AssertionError(f"execution did not reconcile result: {latest}")


if __name__ == "__main__":
    unittest.main()
