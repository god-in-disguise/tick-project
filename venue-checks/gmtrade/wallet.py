from __future__ import annotations

import json

from solders.keypair import Keypair


def load_keypair(value: str) -> Keypair:
    """Load a Solana keypair without writing the secret to disk."""
    value = value.strip()
    if value.startswith("["):
        secret = bytes(json.loads(value))
        if len(secret) != 64:
            raise ValueError("Solana JSON private key must contain 64 bytes")
        return Keypair.from_bytes(secret)
    return Keypair.from_base58_string(value)
