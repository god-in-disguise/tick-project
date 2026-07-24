from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from backend.connectors import ostium_pricing


class OstiumPricingTest(unittest.TestCase):
    def test_estimate_open_uses_stream_price_without_rest_fetch(self) -> None:
        pair = {"id": "0", "from": "BTC", "to": "USD"}
        live = {"mid": 64000, "bid": 63999, "ask": 64001, "isMarketOpen": True}

        with (
            patch.object(ostium_pricing.raw, "_find_pair", return_value=pair),
            patch.object(ostium_pricing.raw, "_max_leverage", return_value=Decimal("100")),
            patch.object(ostium_pricing.raw, "_taker_fee_rate", return_value=Decimal("0.0004")),
            patch.object(ostium_pricing.raw, "_liquidation_estimate", return_value=Decimal("63361")),
            patch.object(ostium_pricing.raw, "_prices", side_effect=AssertionError("REST should not be called")),
        ):
            quote = ostium_pricing.estimate_open(
                "BTC-USD",
                "long",
                Decimal("20"),
                Decimal("100"),
                live=live,
            )

        self.assertEqual(quote["price"], 64001.0)
        self.assertEqual(quote["leverage"], 100.0)


if __name__ == "__main__":
    unittest.main()
