from __future__ import annotations

import unittest

from backend.connectors.gtrade_wallet import (
    _is_base_fee_error,
    _is_known_transaction_error,
    _is_nonce_error,
)


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


if __name__ == "__main__":
    unittest.main()
