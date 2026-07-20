from __future__ import annotations

import json
import unittest

from backend.connectors.ostium_stream import _parse_message


class OstiumStreamTest(unittest.TestCase):
    def test_parses_snapshot_and_tick_messages(self) -> None:
        btc = {"pair": "BTC-USD", "mid": 64000, "bid": 63999, "ask": 64001}
        sol = {"pair": "SOL-USD", "mid": 77, "bid": 76.99, "ask": 77.01}

        snapshot = _parse_message(
            json.dumps({"type": "snapshot", "data": [btc, sol]}),
            ("BTC-USD", "SOL-USD"),
        )
        tick = _parse_message(
            json.dumps({"type": "tick", "data": btc}),
            ("BTC-USD",),
        )

        self.assertEqual(set(snapshot), {"BTC-USD", "SOL-USD"})
        self.assertEqual(tick["BTC-USD"]["mid"], 64000)


if __name__ == "__main__":
    unittest.main()
