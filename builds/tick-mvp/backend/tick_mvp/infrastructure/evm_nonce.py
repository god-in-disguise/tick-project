from __future__ import annotations

import threading
from typing import Any


class EvmNonceCoordinator:
    """Coordinates sender nonces across all EVM writers in one worker process."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}
        self._next_nonce: dict[str, int] = {}

    def sender_lock(self, address: str) -> threading.RLock:
        key = _address_key(address)
        with self._guard:
            return self._locks.setdefault(key, threading.RLock())

    def reserve(self, web3: Any, address: str) -> int:
        """Reserve the next nonce while the caller holds sender_lock(address)."""
        key = _address_key(address)
        cached = self._next_nonce.get(key)
        if cached is None:
            cached = int(web3.eth.get_transaction_count(address, "pending"))
        self._next_nonce[key] = cached + 1
        return cached

    def warm(self, web3: Any, address: str) -> int:
        with self.sender_lock(address):
            chain_nonce = int(web3.eth.get_transaction_count(address, "pending"))
            key = _address_key(address)
            cached = self._next_nonce.get(key)
            if cached is None or cached < chain_nonce:
                self._next_nonce[key] = chain_nonce
            return self._next_nonce[key]

    def observe(self, address: str, nonce: int) -> None:
        with self.sender_lock(address):
            key = _address_key(address)
            next_nonce = int(nonce) + 1
            cached = self._next_nonce.get(key)
            if cached is None or cached < next_nonce:
                self._next_nonce[key] = next_nonce

    def invalidate(self, address: str) -> None:
        with self.sender_lock(address):
            self._next_nonce.pop(_address_key(address), None)

    def peek(self, address: str) -> int | None:
        with self.sender_lock(address):
            return self._next_nonce.get(_address_key(address))


EVM_NONCES = EvmNonceCoordinator()


def _address_key(address: str) -> str:
    return address.strip().lower()
