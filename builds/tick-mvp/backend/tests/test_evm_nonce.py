from types import SimpleNamespace

from tick_mvp.infrastructure.evm_nonce import EvmNonceCoordinator


def test_nonce_coordinator_reuses_one_chain_read_across_writers() -> None:
    calls: list[tuple[str, str]] = []
    web3 = SimpleNamespace(
        eth=SimpleNamespace(
            get_transaction_count=lambda address, state: (
                calls.append((address, state)) or 7
            )
        )
    )
    coordinator = EvmNonceCoordinator()
    address = "0x" + "12" * 20

    with coordinator.sender_lock(address):
        first = coordinator.reserve(web3, address)
    with coordinator.sender_lock(address):
        second = coordinator.reserve(web3, address)

    assert first == 7
    assert second == 8
    assert coordinator.peek(address) == 9
    assert calls == [(address, "pending")]
