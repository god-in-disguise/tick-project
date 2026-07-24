from __future__ import annotations

import unittest

from eth_abi import encode
from hexbytes import HexBytes

from backend.connectors import ostium_rpc


class FakeEth:
    def __init__(self, receipt: dict, callback: dict):
        self.receipt = receipt
        self.callback = callback

    def get_transaction_receipt(self, tx_hash: str) -> dict:
        return self.receipt

    def get_logs(self, params: dict) -> list[dict]:
        return [self.callback]


class FakeWeb3:
    def __init__(self, receipt: dict, callback: dict):
        self.eth = FakeEth(receipt, callback)


def topic(value: int) -> HexBytes:
    return HexBytes(value.to_bytes(32, "big"))


class OstiumRpcTest(unittest.TestCase):
    def test_open_confirmation_decodes_closeable_position(self) -> None:
        order_id = 2_153_335
        receipt = {
            "blockNumber": 100,
            "logs": [
                {
                    "address": ostium_rpc.TRADING,
                    "topics": [ostium_rpc.OPEN_INITIATED, topic(order_id), topic(1), topic(9)],
                }
            ],
        }
        trade = (17_900_000, 77_527_751_440_000_000_000, 0, 0, "0xed1fa479504ec60db8a314bff2dbbd1bb481db78", 10_000, 9, 0, True, False)
        callback = {
            "blockNumber": 106,
            "logIndex": 3,
            "transactionHash": HexBytes("0x" + "12" * 32),
            "topics": [ostium_rpc.OPEN_EXECUTED, topic(order_id)],
            "data": HexBytes(encode(
                ["(uint256,uint192,uint192,uint192,address,uint32,uint16,uint8,bool,bool)", "uint256", "uint256"],
                [trade, 0, 1_790_000_000_000_000_000_000],
            )),
        }

        result = ostium_rpc.wait_for_open_callback(FakeWeb3(receipt, callback), "0xopen", "SOL-USD")

        self.assertEqual(result["status"], "opened")
        self.assertEqual(result["position"]["pairId"], 9)
        self.assertEqual(result["position"]["idx"], 0)
        self.assertAlmostEqual(result["position"]["entry"], 77.52775144)
        self.assertEqual(result["position"]["collateral"], 17.9)
        self.assertTrue(result["position"]["closeAvailable"])
        self.assertEqual(result["confirmation"]["blockDelta"], 6)

    def test_close_confirmation_decodes_settlement(self) -> None:
        order_id = 2_153_336
        trade_id = 2_153_335
        receipt = {
            "blockNumber": 200,
            "logs": [
                {
                    "address": ostium_rpc.TRADING,
                    "topics": [ostium_rpc.CLOSE_INITIATED_V2, topic(order_id), topic(trade_id), topic(1)],
                }
            ],
        }
        callback = {
            "blockNumber": 207,
            "logIndex": 2,
            "transactionHash": HexBytes("0x" + "34" * 32),
            "topics": [ostium_rpc.CLOSE_EXECUTED_V2, topic(order_id), topic(trade_id)],
            "data": HexBytes(encode(
                ["uint256", "uint256", "int256", "uint256", "uint256"],
                [77_516_172_856_187_510_000, 0, -85_277, 17_654_059, 10_000],
            )),
        }

        result = ostium_rpc.wait_for_close_callback(FakeWeb3(receipt, callback), "0xclose")

        self.assertEqual(result["status"], "closed")
        self.assertTrue(result["closed"])
        self.assertAlmostEqual(result["usdcSentToTrader"], 17.654059)
        self.assertEqual(result["confirmation"]["blockDelta"], 7)


if __name__ == "__main__":
    unittest.main()
