from __future__ import annotations

import json
import time
import unittest

from backend.connectors.gtrade_events import GTradeEventStream


class GTradeEventStreamTest(unittest.TestCase):
    def test_matches_unregister_trade_by_position_index_without_pair_index(self) -> None:
        stream = GTradeEventStream("0x1111111111111111111111111111111111111111")
        since = time.time() - 1

        stream._handle_raw(  # type: ignore[attr-defined]
            json.dumps(
                {
                    "name": "unregisterTrade",
                    "value": {
                        "user": "0x1111111111111111111111111111111111111111",
                        "index": 7,
                    },
                }
            )
        )

        result = stream.wait_for_position_event(
            999,
            present=False,
            since=since,
            timeout_seconds=0.01,
            position_index=7,
        )

        self.assertFalse(result["timedOut"])
        self.assertEqual(result["source"], "backend_ws")
        self.assertEqual(result["event"]["name"], "unregisterTrade")

    def test_tracks_message_size_and_matched_events(self) -> None:
        stream = GTradeEventStream("0x2222222222222222222222222222222222222222")
        stream._handle_raw(  # type: ignore[attr-defined]
            json.dumps(
                {
                    "name": "registerTrade",
                    "value": {
                        "trade": {
                            "user": "0x2222222222222222222222222222222222222222",
                            "pairIndex": 300,
                            "index": 3,
                        }
                    },
                }
            )
        )

        health = stream.health()
        self.assertEqual(health["lastMessageName"], "registerTrade")
        self.assertEqual(health["messageCount"], 1)
        self.assertEqual(health["matchedEventCount"], 1)
        self.assertGreater(health["maxRawBytes"], 0)


if __name__ == "__main__":
    unittest.main()
