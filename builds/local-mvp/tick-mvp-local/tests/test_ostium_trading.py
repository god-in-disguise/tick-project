from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.connectors import ostium_trading


class OstiumTradingTest(unittest.TestCase):
    def test_preflighted_close_uses_stream_price_and_rpc_confirmation(self) -> None:
        pair = {"id": "0", "from": "BTC", "to": "USD"}
        position = {"pair": "BTC-USD", "pairId": 0, "idx": 0, "side": "long"}
        web3 = SimpleNamespace(eth=SimpleNamespace())

        with (
            patch.object(ostium_trading, "_load", return_value=(object(), "0x0000000000000000000000000000000000000001", web3)),
            patch.object(ostium_trading, "_find_pair", return_value=pair),
            patch.object(ostium_trading, "_prices", side_effect=AssertionError("REST prices should not be called")),
            patch.object(ostium_trading, "_open_trades", side_effect=AssertionError("subgraph should not be called")),
            patch.object(ostium_trading, "_balances", side_effect=AssertionError("balance preflight should not repeat")),
            patch.object(ostium_trading, "_close_fn", return_value="close-call"),
            patch.object(ostium_trading, "_send", return_value={"txHash": "0xclose", "timing": {}}),
            patch.object(
                ostium_trading,
                "wait_for_close_callback",
                return_value={
                    "status": "closed",
                    "closed": True,
                    "price": 64010.0,
                    "usdcSentToTrader": 19.0,
                    "confirmation": {"source": "arbitrum_rpc"},
                },
            ),
        ):
            result = ostium_trading.close_trade(
                "BTC-USD",
                position=position,
                execution_price=Decimal("64000"),
                preflighted=True,
                wait=False,
            )

        self.assertEqual(result["status"], "closed")
        self.assertTrue(result["closed"])
        self.assertEqual(result["fillPrice"], 64010.0)
        self.assertEqual(result["confirmation"]["source"], "arbitrum_rpc")

    def test_preflighted_open_uses_rpc_confirmation_without_subgraph_reads(self) -> None:
        pair = {"id": "0", "from": "BTC", "to": "USD"}
        contract = SimpleNamespace(functions=SimpleNamespace(approve=Mock(return_value="approve-call")))
        web3 = SimpleNamespace(eth=SimpleNamespace(contract=Mock(return_value=contract)))
        position = {
            "pair": "BTC-USD",
            "pairId": 0,
            "idx": 0,
            "side": "long",
            "entry": 64001.0,
            "collateral": 17.9,
            "leverage": 100.0,
        }

        with (
            patch.object(ostium_trading, "_load", return_value=(object(), "0x0000000000000000000000000000000000000001", web3)),
            patch.object(ostium_trading, "_find_pair", return_value=pair),
            patch.object(ostium_trading, "_max_leverage", return_value=Decimal("100")),
            patch.object(ostium_trading, "_prices", side_effect=AssertionError("REST prices should not be called")),
            patch.object(ostium_trading, "_open_trades", side_effect=AssertionError("subgraph should not be called")),
            patch.object(ostium_trading, "_balances", side_effect=AssertionError("balance preflight should not repeat")),
            patch.object(ostium_trading, "_open_fn", return_value="open-call"),
            patch.object(ostium_trading, "_send", return_value={"txHash": "0xopen", "timing": {}}),
            patch.object(
                ostium_trading,
                "wait_for_open_callback",
                return_value={"status": "opened", "position": position, "confirmation": {"source": "arbitrum_rpc"}},
            ),
        ):
            result = ostium_trading.open_trade(
                "long",
                100,
                "BTC-USD",
                Decimal("20"),
                execution_price=Decimal("64001"),
                preflighted=True,
                wait=False,
            )

        self.assertEqual(result["status"], "opened")
        self.assertEqual(result["position"], position)
        self.assertEqual(result["confirmation"]["source"], "arbitrum_rpc")

    def test_open_auto_approves_and_submits_without_network(self) -> None:
        pair = {"id": "0", "from": "BTC", "to": "USD"}
        price = {"mid": 64000, "bid": 63999, "ask": 64001, "isMarketOpen": True}
        indexed_position = {"pair": pair, "index": "0"}
        contract = SimpleNamespace(functions=SimpleNamespace(approve=Mock(return_value="approve-call")))
        web3 = SimpleNamespace(eth=SimpleNamespace(contract=Mock(return_value=contract)))
        balances = [
            {"usdc": 100_000_000, "allowance": 0},
            {"usdc": 100_000_000, "allowance": ostium_trading.MAX_UINT256},
        ]
        send = Mock(
            side_effect=[
                {"txHash": "0xapprove", "timing": {}},
                {"txHash": "0xopen", "timing": {}},
            ]
        )

        with (
            patch.object(ostium_trading, "_load", return_value=(object(), "0x0000000000000000000000000000000000000001", web3)),
            patch.object(ostium_trading, "_find_pair", return_value=pair),
            patch.object(ostium_trading, "_max_leverage", return_value=Decimal("100")),
            patch.object(ostium_trading, "_prices", return_value={"BTC-USD": price}),
            patch.object(ostium_trading, "_open_trades", return_value=[]),
            patch.object(ostium_trading, "_balances", side_effect=balances),
            patch.object(ostium_trading, "_open_fn", return_value="open-call"),
            patch.object(ostium_trading, "_send", send),
            patch.object(ostium_trading, "_wait_for_order", return_value=[]),
            patch.object(ostium_trading, "_wait_for_position", return_value=indexed_position),
            patch.object(ostium_trading, "_position_public", return_value={"pair": "BTC-USD"}),
        ):
            result = ostium_trading.open_trade("long", pair_name="BTC-USD", wait=True)

        self.assertEqual(result["status"], "opened")
        self.assertEqual(result["ticketUsd"], 20.0)
        self.assertEqual(result["slippageBps"], ostium_trading.DEFAULT_SLIPPAGE_BPS)
        self.assertEqual(result["approval"]["txHash"], "0xapprove")
        self.assertEqual(result["tx"]["txHash"], "0xopen")
        self.assertEqual(send.call_count, 2)


if __name__ == "__main__":
    unittest.main()
