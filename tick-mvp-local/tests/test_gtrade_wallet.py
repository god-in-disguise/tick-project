from __future__ import annotations

import unittest
from decimal import Decimal

from backend.connectors.gtrade_wallet import (
    GTradeWallet,
    _callback_position_public,
    _is_base_fee_error,
    _is_known_transaction_error,
    _is_nonce_error,
    _topic_address,
    _topic_u256,
)
from backend.connectors.gtrade_public import GTradePair


class GTradeWalletErrorClassifierTest(unittest.TestCase):
    def test_classifies_base_fee_errors(self) -> None:
        self.assertTrue(_is_base_fee_error(Exception("max fee per gas less than block base fee")))
        self.assertTrue(_is_base_fee_error(Exception("baseFee changed")))
        self.assertFalse(_is_base_fee_error(Exception("execution reverted")))

    def test_classifies_nonce_errors_conservatively(self) -> None:
        self.assertTrue(_is_nonce_error(Exception("nonce too low")))
        self.assertTrue(_is_nonce_error(Exception("nonce has already been used")))
        self.assertTrue(_is_nonce_error(Exception("invalid transaction nonce")))
        self.assertFalse(_is_nonce_error(Exception("already known")))
        self.assertFalse(_is_nonce_error(Exception("execution reverted")))

    def test_known_transaction_does_not_trigger_nonce_retry(self) -> None:
        self.assertTrue(_is_known_transaction_error(Exception("already known")))
        self.assertTrue(_is_known_transaction_error(Exception("known transaction")))
        self.assertFalse(_is_known_transaction_error(Exception("nonce too low")))

    def test_raw_trade_topic_match_infers_closeable_trade_index(self) -> None:
        wallet = GTradeWallet()
        owner = "0xeD1fa479504Ec60DB8a314BfF2DbbD1bB481Db78"
        log = {
            "transactionHash": "0xabc",
            "blockNumber": 10,
            "logIndex": 4,
            "topics": [
                "0xa14af6e9b04a80b4f40bf3946fceabd8e21e03bed8bdfd8d7b99af550efbf792",
                _topic_address(owner),
                _topic_u256(17),
            ],
            "data": _topic_u256(452),
        }

        event = wallet._raw_trade_topic_match(  # type: ignore[attr-defined]
            log,
            owner=owner,
            pair_index=452,
            position_index=None,
            initiation_tx_hash="0xinitiation",
            execution_open=True,
        )

        self.assertIsNotNone(event)
        self.assertEqual(event["trade"]["index"], 17)
        self.assertEqual(event["trade"]["pairIndex"], 452)

    def test_callback_position_is_closeable_while_indexing(self) -> None:
        pair = GTradePair(
            pair_index=452,
            pair="HYPEDEGEN-USD",
            raw_symbol="HYPEDEGEN/USD",
            symbol="HYPE",
            name="Hyperliquid",
            group="crypto",
            asset_class="CRYPTO",
            max_leverage=Decimal("500"),
            open_fee_pct=Decimal("0.02"),
            min_position_usd=Decimal("0"),
            min_collateral_usd=Decimal("10"),
            spread_pct=Decimal("0"),
        )
        position = _callback_position_public(
            {
                "trade": {"index": 17, "pairIndex": 452},
                "raw": {
                    "transactionHash": "0xcallback",
                    "blockNumber": 100,
                    "blockTimestamp": 1784567717,
                },
            },
            pair,
            "long",
            ticket_usd=Decimal("10"),
            leverage=Decimal("500"),
            price=Decimal("62.0"),
        )

        self.assertTrue(position["closeAvailable"])
        self.assertTrue(position["venueConfirmed"])
        self.assertTrue(position["indexing"])
        self.assertEqual(position["idx"], 17)


if __name__ == "__main__":
    unittest.main()
