import base64
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from solders.pubkey import Pubkey

from tick_mvp.core.config import Settings
from tick_mvp.infrastructure.flash_wallet_balances import read_flash_wallet_balances
from tick_mvp.venues.flash.constants import USDC_MINT
from tick_mvp.venues.flash.deposit_ledger import (
    decode_deposit_ledger_usdc,
    deposit_ledger_address,
)


OWNER = "AQ7omuC1f1NMFrKzJ3JMisJvLKMYzyB2tQL3qynnooHd"
LEDGER = "CxcVo6hnGUY1xnm94VQ1xZ8VuFVCAQ91NFHST1PjLzHD"


class Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _ledger_data(amount_units: int) -> bytes:
    header = bytes(48) + (1).to_bytes(4, "little")
    entry = bytes(Pubkey.from_string(USDC_MINT)) + amount_units.to_bytes(8, "little")
    return header + entry


def test_flash_deposit_ledger_address_and_usdc_decoder() -> None:
    assert deposit_ledger_address(OWNER) == LEDGER
    assert decode_deposit_ledger_usdc(_ledger_data(15_000_000)) == Decimal("15")


def test_flash_balance_includes_deposit_ledger_collateral(monkeypatch) -> None:
    encoded = base64.b64encode(_ledger_data(15_000_000)).decode()

    def post(*_args, **_kwargs):
        return Response([
            {"jsonrpc": "2.0", "id": 1, "result": {"value": 10_000_000}},
            {"jsonrpc": "2.0", "id": 2, "result": {"value": []}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {"value": {"data": [encoded, "base64"]}},
            },
        ])

    def get(url, **_kwargs):
        if "/owner/" in url:
            return Response({"basketPubkey": "basket"})
        return Response({
            "source": "er",
            "account": {"debits": [], "pendingCredits": []},
        })

    monkeypatch.setattr("tick_mvp.infrastructure.flash_wallet_balances.requests.post", post)
    monkeypatch.setattr("tick_mvp.infrastructure.flash_wallet_balances.requests.get", get)
    wallet = SimpleNamespace(
        address=OWNER,
        createdAt=datetime.now(UTC),
    )

    balances = read_flash_wallet_balances(
        wallet,
        Settings(solana_rpc_url="https://solana.invalid"),
    )

    assert balances.usdc == Decimal("15")
    assert balances.onchainUsdc == Decimal(0)
    assert balances.spendableUsdc == Decimal("15")
    assert balances.venueReady is True
    assert balances.source == "solana_rpc+flash_raw_basket+deposit_ledger"
