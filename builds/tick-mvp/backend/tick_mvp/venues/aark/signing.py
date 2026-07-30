from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

from eth_abi import encode as abi_encode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak


SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


class MillisecondNonce:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last = 0

    def next(self) -> int:
        with self._lock:
            value = max(int(time.time() * 1000), self._last + 1)
            self._last = value
            return value


def session_private_key(wallet_private_key: str) -> str:
    raw = bytes.fromhex(wallet_private_key.removeprefix("0x"))
    derived = int.from_bytes(
        hashlib.sha256(b"tick:aark:delegate:v1:" + raw).digest(),
        "big",
    )
    scalar = (derived % (SECP256K1_ORDER - 1)) + 1
    return f"0x{scalar:064x}"


def address(private_key: str) -> str:
    return Account.from_key(private_key).address


def sign_delegate(
    private_key: str,
    *,
    chain_id: int,
    delegator: str,
    delegatee: str,
    nonce: int,
) -> str:
    return _typed_signature(
        private_key,
        chain_id=chain_id,
        primary_type="Delegate",
        fields=[
            {"name": "delegator", "type": "address"},
            {"name": "delegatee", "type": "address"},
            {"name": "nonce", "type": "uint256"},
        ],
        values={"delegator": delegator, "delegatee": delegatee, "nonce": nonce},
    )


def sign_open(
    private_key: str,
    *,
    chain_id: int,
    user: str,
    market_id: int,
    amount_in: int,
    leverage: int,
    credit_to_use: int,
    take_profit: int,
    is_long: bool,
    nonce: int,
) -> str:
    # Aark's current production frontend uses EIP-712 here. Its July 2026
    # EIP-191 integration example was rejected by the live API in our canary.
    return _typed_signature(
        private_key,
        chain_id=chain_id,
        primary_type="MoonOrder",
        fields=[
            {"name": "user", "type": "address"},
            {"name": "marketId", "type": "uint32"},
            {"name": "amountIn", "type": "uint256"},
            {"name": "leverage", "type": "uint256"},
            {"name": "creditToUse", "type": "uint256"},
            {"name": "takeProfit", "type": "uint256"},
            {"name": "isLong", "type": "bool"},
            {"name": "nonce", "type": "uint256"},
        ],
        values={
            "user": user,
            "marketId": market_id,
            "amountIn": amount_in,
            "leverage": leverage,
            "creditToUse": credit_to_use,
            "takeProfit": take_profit,
            "isLong": is_long,
            "nonce": nonce,
        },
    )


def sign_open_eip191(
    private_key: str,
    *,
    user: str,
    market_id: int,
    amount_in: int,
    leverage: int,
    credit_to_use: int,
    take_profit: int,
    is_long: bool,
    nonce: int,
) -> str:
    digest = keccak(
        abi_encode(
            [
                "address",
                "uint32",
                "uint256",
                "uint256",
                "uint256",
                "uint256",
                "bool",
                "uint256",
            ],
            [
                user,
                market_id,
                amount_in,
                leverage,
                credit_to_use,
                take_profit,
                is_long,
                nonce,
            ],
        )
    )
    signed = Account.sign_message(
        encode_defunct(primitive=digest),
        private_key=private_key,
    )
    return f"0x{signed.signature.hex()}"


def sign_close(
    private_key: str,
    *,
    chain_id: int,
    user: str,
    moon_index: int,
    nonce: int,
) -> str:
    return _typed_signature(
        private_key,
        chain_id=chain_id,
        primary_type="MoonCloseOrder",
        fields=[
            {"name": "user", "type": "address"},
            {"name": "moonIndex", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
        ],
        values={"user": user, "moonIndex": moon_index, "nonce": nonce},
    )


def sign_close_eip191(
    private_key: str,
    *,
    user: str,
    moon_index: int,
    nonce: int,
) -> str:
    digest = keccak(
        abi_encode(
            ["address", "uint32", "uint256"],
            [user, moon_index, nonce],
        )
    )
    signed = Account.sign_message(
        encode_defunct(primitive=digest),
        private_key=private_key,
    )
    return f"0x{signed.signature.hex()}"


def sign_withdraw(
    private_key: str,
    *,
    chain_id: int,
    user: str,
    recipient: str,
    token_address: str,
    amount: int,
    nonce: int,
    is_lp: bool = False,
) -> str:
    return _typed_signature(
        private_key,
        chain_id=chain_id,
        primary_type="Withdrawal",
        fields=[
            {"name": "user", "type": "address"},
            {"name": "recipient", "type": "address"},
            {"name": "tokenAddress", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
            {"name": "isLP", "type": "bool"},
        ],
        values={
            "user": user,
            "recipient": recipient,
            "tokenAddress": token_address,
            "amount": amount,
            "nonce": nonce,
            "isLP": is_lp,
        },
    )


def sign_deposit(
    private_key: str,
    *,
    chain_id: int,
    payor: str,
    user: str,
    token_address: str,
    amount: int,
    nonce: int,
) -> str:
    return _typed_signature(
        private_key,
        chain_id=chain_id,
        primary_type="Deposit",
        fields=[
            {"name": "payor", "type": "address"},
            {"name": "user", "type": "address"},
            {"name": "tokenAddress", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
        ],
        values={
            "payor": payor,
            "user": user,
            "tokenAddress": token_address,
            "amount": amount,
            "nonce": nonce,
        },
    )


def sign_usdc_permit(
    private_key: str,
    *,
    chain_id: int,
    token_address: str,
    token_name: str,
    token_version: str,
    owner: str,
    spender: str,
    value: int,
    nonce: int,
    deadline: int,
) -> str:
    signed = Account.sign_typed_data(
        private_key,
        domain_data={
            "name": token_name,
            "version": token_version,
            "chainId": chain_id,
            "verifyingContract": token_address,
        },
        message_types={
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ]
        },
        message_data={
            "owner": owner,
            "spender": spender,
            "value": value,
            "nonce": nonce,
            "deadline": deadline,
        },
    )
    return f"0x{signed.signature.hex()}"


def partner_headers(private_key: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signed = Account.sign_message(
        encode_defunct(text=f"Aark-Partner-Auth:{timestamp}"),
        private_key=private_key,
    )
    return {
        "x-partner-timestamp": timestamp,
        "x-partner-signature": f"0x{signed.signature.hex()}",
    }


def _typed_signature(
    private_key: str,
    *,
    chain_id: int,
    primary_type: str,
    fields: list[dict[str, str]],
    values: dict[str, Any],
) -> str:
    signed = Account.sign_typed_data(
        private_key,
        domain_data={"name": "AARK", "chainId": chain_id},
        message_types={primary_type: fields},
        message_data=values,
    )
    return f"0x{signed.signature.hex()}"
