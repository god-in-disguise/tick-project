from __future__ import annotations

import base64
from decimal import Decimal

import pytest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import MessageV0, to_bytes_versioned
from solders.signature import Signature
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction, VersionedTransaction

from tick_mvp.venues.flash.signing import (
    PreparedFlashTransaction,
    sign_built_transaction_multi,
)
from tick_mvp.wallets.arbitrum import WithdrawalRejected
from tick_mvp.wallets.repository import WithdrawalContext
from tick_mvp.wallets.solana import SolanaUSDCWithdrawalExecutor, _amount_units


class _Signer:
    def __init__(self, address: str) -> None:
        self._address = address

    def pubkey(self) -> str:
        return self._address


class _Flash:
    def __init__(self) -> None:
        self.body = None

    def post(self, path: str, body: dict):
        assert path == "/transaction-builder/withdraw"
        self.body = body
        return {"transactionBase64": "unsigned"}


def test_flash_custody_release_only_requests_the_missing_wallet_amount(
    monkeypatch,
) -> None:
    executor = object.__new__(SolanaUSDCWithdrawalExecutor)
    executor._fee_payer = _Signer("fee-payer")
    executor._flash = _Flash()
    prepared = PreparedFlashTransaction(
        signature="release-signature",
        signed_transaction_base64="signed",
        quote={},
    )
    monkeypatch.setattr(
        "tick_mvp.wallets.solana.sign_built_transaction_multi",
        lambda encoded, signers: prepared,
    )

    result = executor._prepare_venue_withdrawal(
        _context(),
        _Signer("owner"),
        7_500_001,
    )

    assert result == prepared
    assert executor._flash.body == {
        "owner": "owner",
        "tokenSymbol": "USDC",
        "amount": "7.500001",
        "feePayer": "fee-payer",
        "feePayerTopUpLamports": 0,
    }


def test_solana_usdc_amount_uses_six_decimal_precision() -> None:
    assert _amount_units(Decimal("10.123456")) == 10_123_456
    with pytest.raises(WithdrawalRejected, match="6 decimal"):
        _amount_units(Decimal("10.1234567"))


def test_flash_builder_signers_are_matched_by_required_public_key() -> None:
    fee_payer = Keypair()
    owner = Keypair()
    instruction = transfer(
        TransferParams(
            from_pubkey=owner.pubkey(),
            to_pubkey=fee_payer.pubkey(),
            lamports=1,
        )
    )
    message = MessageV0.try_compile(
        fee_payer.pubkey(),
        [instruction],
        [],
        Hash.default(),
    )
    unsigned = VersionedTransaction.populate(
        message,
        [Signature.default()] * message.header.num_required_signatures,
    )

    prepared = sign_built_transaction_multi(
        base64.b64encode(bytes(unsigned)).decode("ascii"),
        [owner, fee_payer],
    )

    signed = VersionedTransaction.from_bytes(
        base64.b64decode(prepared.signed_transaction_base64)
    )
    message_bytes = to_bytes_versioned(signed.message)
    required = signed.message.account_keys[
        : signed.message.header.num_required_signatures
    ]
    assert all(
        signature.verify(pubkey, message_bytes)
        for signature, pubkey in zip(signed.signatures, required, strict=True)
    )


def test_external_usdc_transfer_is_signed_by_owner_and_platform_fee_payer() -> None:
    executor = object.__new__(SolanaUSDCWithdrawalExecutor)
    executor._fee_payer = Keypair()
    executor._rpc_call = lambda method, params: {
        "value": {"blockhash": str(Hash.default())}
    }
    owner = Keypair()

    prepared = executor._prepare_token_transfer(
        owner=owner,
        destination_owner=Keypair().pubkey(),
        amount_units=1_250_000,
    )

    transaction = Transaction.from_bytes(
        base64.b64decode(prepared.signed_transaction_base64)
    )
    transaction.verify()
    assert len(transaction.signatures) == 2
    assert prepared.signature == str(transaction.signatures[0])


def _context() -> WithdrawalContext:
    from tick_mvp.domain.states import WithdrawalStatus

    return WithdrawalContext(
        withdrawal_id="withdrawal_flash",
        user_id="user_flash",
        wallet_id="wallet_flash",
        chain_id=501,
        wallet_address="owner",
        private_key_hex="unused",
        asset="USDC",
        amount=Decimal("10"),
        destination_address="destination",
        status=WithdrawalStatus.VALIDATED,
        tx_hash=None,
        nonce=None,
        signed_raw_transaction=None,
    )
