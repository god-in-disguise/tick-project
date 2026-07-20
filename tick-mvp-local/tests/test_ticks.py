from __future__ import annotations

import time
import unittest

from backend.ticks import TickService

from tests.fakes import FakeConnector


class TickServiceTest(unittest.TestCase):
    def test_samples_all_prices_into_memory(self) -> None:
        service = TickService(FakeConnector(), ["BTC-USD"], interval_seconds=0.01, max_points=20)
        service.start()
        try:
            deadline = time.time() + 1
            while time.time() < deadline and len(service.snapshot("BTC-USD")["ticks"]) < 3:
                time.sleep(0.01)
            snapshot = service.snapshot("BTC-USD")
            self.assertGreaterEqual(len(snapshot["ticks"]), 3)
            self.assertFalse(snapshot["stale"])
            self.assertGreater(snapshot["latest"]["mid"], 64000)
        finally:
            service.stop()


if __name__ == "__main__":
    unittest.main()
