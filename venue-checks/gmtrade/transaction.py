from __future__ import annotations

from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import MessageV0, VersionedMessage
from solders.transaction import VersionedTransaction


def sign_with_blockhash(
    message: VersionedMessage,
    blockhash: Hash,
    payer: Keypair,
) -> VersionedTransaction:
    if not isinstance(message, MessageV0):
        raise TypeError(f"Expected a v0 message, got {type(message).__name__}")

    signer_count = message.header.num_required_signatures
    required_signers = list(message.account_keys[:signer_count])
    if required_signers != [payer.pubkey()]:
        names = ", ".join(map(str, required_signers))
        raise RuntimeError(f"Unexpected transaction signers: {names}")

    current_message = MessageV0(
        message.header,
        message.account_keys,
        blockhash,
        message.instructions,
        message.address_table_lookups,
    )
    return VersionedTransaction(current_message, [payer])
