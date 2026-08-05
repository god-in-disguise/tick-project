from __future__ import annotations

import base64
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreparedFlashTransaction:
    signature: str
    signed_transaction_base64: str
    quote: dict
    build_ms: float = 0.0
    sign_ms: float = 0.0


def keypair_from_secret(secret: str):
    from solders.keypair import Keypair

    value = secret.strip()
    if value.startswith("["):
        raw = bytes(json.loads(value))
    else:
        hex_value = value.removeprefix("0x")
        try:
            raw = bytes.fromhex(hex_value)
        except ValueError:
            return Keypair.from_base58_string(value)
    if len(raw) == 64:
        return Keypair.from_bytes(raw)
    if len(raw) == 32:
        return Keypair.from_seed(raw)
    raise ValueError("Flash wallet secret must contain 32 or 64 bytes")


def sign_built_transaction(transaction_base64: str, keypair) -> PreparedFlashTransaction:
    from solders.transaction import VersionedTransaction

    unsigned = VersionedTransaction.from_bytes(base64.b64decode(transaction_base64))
    signer_count = unsigned.message.header.num_required_signatures
    required = list(unsigned.message.account_keys[:signer_count])
    if required != [keypair.pubkey()]:
        raise ValueError(
            "Flash transaction requested unexpected signers: "
            + ", ".join(map(str, required))
        )
    signed = VersionedTransaction(unsigned.message, [keypair])
    return PreparedFlashTransaction(
        signature=str(signed.signatures[0]),
        signed_transaction_base64=base64.b64encode(bytes(signed)).decode("ascii"),
        quote={},
    )
