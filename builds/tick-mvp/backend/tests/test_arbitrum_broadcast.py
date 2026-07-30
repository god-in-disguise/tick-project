from __future__ import annotations

import threading

import pytest

from tick_mvp.venues.gtrade.broadcast import (
    ROUTE_CHAIN,
    ROUTE_PRIMARY,
    ROUTE_SEQUENCER,
    BroadcastError,
    DualBroadcaster,
)


TX_HASH = "0x" + "ab" * 32
RAW_TRANSACTION = bytes.fromhex("02cafe")


class FakeEth:
    def __init__(self, send, *, transaction=None) -> None:
        self._send = send
        self._transaction = transaction
        self.raw_transactions: list[bytes] = []

    def send_raw_transaction(self, raw_transaction: bytes):
        self.raw_transactions.append(raw_transaction)
        return self._send(raw_transaction)

    def get_transaction(self, _tx_hash: str):
        if isinstance(self._transaction, Exception):
            raise self._transaction
        return self._transaction


class FakeWeb3:
    def __init__(self, send, *, transaction=None) -> None:
        self.eth = FakeEth(send, transaction=transaction)


def test_direct_sequencer_can_win_with_identical_signed_bytes() -> None:
    release_primary = threading.Event()
    primary = FakeWeb3(lambda _raw: release_primary.wait(0.5) and TX_HASH)
    sequencer = FakeWeb3(lambda _raw: TX_HASH)
    broadcaster = DualBroadcaster()

    try:
        race = broadcaster.broadcast(
            raw_transaction=RAW_TRANSACTION,
            expected_tx_hash=TX_HASH,
            primary_web3=primary,
            sequencer_web3=sequencer,
        )
        release_primary.set()
        race.wait_for_outcomes(timeout=0.5)

        assert race.winner == ROUTE_SEQUENCER
        assert primary.eth.raw_transactions == [RAW_TRANSACTION]
        assert sequencer.eth.raw_transactions == [RAW_TRANSACTION]
        assert race.payload()["routes"][ROUTE_PRIMARY]["status"] == "accepted"
        assert race.payload()["routes"][ROUTE_SEQUENCER]["status"] == "accepted"
    finally:
        release_primary.set()
        broadcaster.close()


def test_primary_succeeds_when_sequencer_rejects() -> None:
    primary = FakeWeb3(lambda _raw: TX_HASH)
    sequencer = FakeWeb3(lambda _raw: (_ for _ in ()).throw(ConnectionError("offline")))
    broadcaster = DualBroadcaster()

    try:
        race = broadcaster.broadcast(
            raw_transaction=RAW_TRANSACTION,
            expected_tx_hash=TX_HASH,
            primary_web3=primary,
            sequencer_web3=sequencer,
        )
        race.wait_for_outcomes(timeout=0.5)

        assert race.winner == ROUTE_PRIMARY
        assert race.payload()["routes"][ROUTE_SEQUENCER]["errorType"] == "ConnectionError"
    finally:
        broadcaster.close()


def test_known_hash_recovers_ambiguous_route_errors() -> None:
    primary = FakeWeb3(
        lambda _raw: (_ for _ in ()).throw(TimeoutError("timeout")),
        transaction={"hash": TX_HASH},
    )
    sequencer = FakeWeb3(lambda _raw: (_ for _ in ()).throw(ConnectionError("offline")))
    broadcaster = DualBroadcaster()

    try:
        race = broadcaster.broadcast(
            raw_transaction=RAW_TRANSACTION,
            expected_tx_hash=TX_HASH,
            primary_web3=primary,
            sequencer_web3=sequencer,
        )

        assert race.winner == ROUTE_CHAIN
        assert race.expected_tx_hash == TX_HASH
    finally:
        broadcaster.close()


def test_all_routes_fail_when_hash_is_not_observed() -> None:
    primary = FakeWeb3(
        lambda _raw: (_ for _ in ()).throw(TimeoutError("timeout")),
        transaction=LookupError("not found"),
    )
    sequencer = FakeWeb3(lambda _raw: (_ for _ in ()).throw(ConnectionError("offline")))
    broadcaster = DualBroadcaster()

    try:
        with pytest.raises(BroadcastError, match="all Arbitrum write routes failed"):
            broadcaster.broadcast(
                raw_transaction=RAW_TRANSACTION,
                expected_tx_hash=TX_HASH,
                primary_web3=primary,
                sequencer_web3=sequencer,
            )
    finally:
        broadcaster.close()


def test_all_route_nonce_rejection_is_structured_for_safe_recovery() -> None:
    nonce_error = RuntimeError("nonce too low: tx: 71 state: 73")
    primary = FakeWeb3(
        lambda _raw: (_ for _ in ()).throw(nonce_error),
        transaction=LookupError("not found"),
    )
    sequencer = FakeWeb3(lambda _raw: (_ for _ in ()).throw(nonce_error))
    broadcaster = DualBroadcaster()

    try:
        with pytest.raises(BroadcastError) as raised:
            broadcaster.broadcast(
                raw_transaction=RAW_TRANSACTION,
                expected_tx_hash=TX_HASH,
                primary_web3=primary,
                sequencer_web3=sequencer,
            )

        assert raised.value.all_routes_report_nonce_too_low() is True
    finally:
        broadcaster.close()
