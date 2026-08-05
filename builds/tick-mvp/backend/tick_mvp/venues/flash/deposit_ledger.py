from __future__ import annotations

import base64
from decimal import Decimal

from solders.pubkey import Pubkey

from tick_mvp.venues.flash.constants import FLASH_PROGRAM_ID, USDC_MINT, USD_DECIMALS


_HEADER_BYTES = 52
_ENTRY_BYTES = 40


def deposit_ledger_address(owner: str) -> str:
    address, _ = Pubkey.find_program_address(
        [b"user_deposit_ledger", bytes(Pubkey.from_string(owner))],
        Pubkey.from_string(FLASH_PROGRAM_ID),
    )
    return str(address)


def deposit_ledger_usdc(account_info: dict | None) -> Decimal:
    if not account_info:
        return Decimal(0)
    encoded = account_info.get("data")
    if not isinstance(encoded, list) or not encoded:
        return Decimal(0)
    return decode_deposit_ledger_usdc(base64.b64decode(encoded[0]))


def decode_deposit_ledger_usdc(data: bytes) -> Decimal:
    if not data:
        return Decimal(0)
    if len(data) < _HEADER_BYTES:
        raise ValueError("Flash deposit ledger is truncated")

    entry_count = int.from_bytes(data[48:52], "little")
    expected_size = _HEADER_BYTES + entry_count * _ENTRY_BYTES
    if len(data) < expected_size:
        raise ValueError("Flash deposit ledger entries are truncated")

    units = 0
    offset = _HEADER_BYTES
    for _ in range(entry_count):
        mint = str(Pubkey.from_bytes(data[offset : offset + 32]))
        amount = int.from_bytes(data[offset + 32 : offset + 40], "little")
        if mint == USDC_MINT:
            units += amount
        offset += _ENTRY_BYTES
    return Decimal(units).scaleb(-USD_DECIMALS)
