from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, localcontext

import requests

from tick_mvp.core.config import Settings
from tick_mvp.domain.schemas import WalletAccountResponse, WalletBalancesResponse


def read_wallet_balances(
    wallet: WalletAccountResponse,
    settings: Settings,
    *,
    gas_charges_usdc: Decimal = Decimal(0),
) -> WalletBalancesResponse:
    fetched_at = datetime.now(UTC)
    if not settings.arb_rpc_url:
        return WalletBalancesResponse(
            chainId=wallet.chainId,
            address=wallet.address,
            source="unavailable",
            fetchedAt=fetched_at,
            unavailableReason="ARB_RPC_URL is not configured",
        )
    try:
        address = _address(wallet.address)
        payload = _rpc_batch_payload(
            owner=address,
            token=_address(settings.gtrade_usdc_address),
            spender=_address(settings.gtrade_diamond_address),
        )
        response = requests.post(settings.arb_rpc_url, json=payload, timeout=6, headers={"user-agent": "tick-mvp/0.1"})
        response.raise_for_status()
        results = _result_by_id(response.json())
        native_eth = _hex_decimal(results[1], 18)
        usdc = _hex_decimal(results[2], 6)
        allowance = _hex_decimal(results[3], 6)
    except Exception as exc:
        return WalletBalancesResponse(
            chainId=wallet.chainId,
            address=wallet.address,
            source="unavailable",
            fetchedAt=fetched_at,
            unavailableReason=f"{type(exc).__name__}: {exc}",
        )
    raw_usdc = _quantize(usdc, 6)
    charges = _quantize(max(Decimal(0), gas_charges_usdc), 6)
    spendable = _quantize(max(Decimal(0), raw_usdc - charges), 6)
    return WalletBalancesResponse(
        chainId=wallet.chainId,
        address=wallet.address,
        nativeEth=_quantize(native_eth, 18),
        usdc=spendable,
        onchainUsdc=raw_usdc,
        gasChargesUsdc=charges,
        spendableUsdc=spendable,
        gtradeAllowanceUsdc=_quantize(allowance, 6),
        source="arbitrum_rpc_batch+gas_ledger",
        fetchedAt=fetched_at,
    )


def _quantize(value: Decimal, decimals: int) -> Decimal:
    with localcontext() as context:
        context.prec = max(80, len(value.as_tuple().digits) + decimals)
        return value.quantize(Decimal(1).scaleb(-decimals))


def _rpc_batch_payload(*, owner: str, token: str, spender: str) -> list[dict[str, object]]:
    return [
        {"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [owner, "latest"]},
        {"jsonrpc": "2.0", "id": 2, "method": "eth_call", "params": [{"to": token, "data": _balance_of(owner)}, "latest"]},
        {"jsonrpc": "2.0", "id": 3, "method": "eth_call", "params": [{"to": token, "data": _allowance(owner, spender)}, "latest"]},
    ]


def _result_by_id(payload: object) -> dict[int, str]:
    if not isinstance(payload, list):
        raise ValueError("RPC batch returned non-list payload")
    results: dict[int, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("RPC batch item is not an object")
        if item.get("error"):
            raise ValueError(f"RPC error: {item['error']}")
        results[int(item["id"])] = str(item["result"])
    return results


def _balance_of(owner: str) -> str:
    return "0x70a08231" + _slot(owner)


def _allowance(owner: str, spender: str) -> str:
    return "0xdd62ed3e" + _slot(owner) + _slot(spender)


def _slot(address: str) -> str:
    return address.removeprefix("0x").rjust(64, "0")


def _address(address: str) -> str:
    cleaned = address.lower()
    if not cleaned.startswith("0x") or len(cleaned) != 42:
        raise ValueError(f"invalid EVM address: {address}")
    int(cleaned[2:], 16)
    return cleaned


def _hex_decimal(value: str, decimals: int) -> Decimal:
    return Decimal(int(value, 16)) / Decimal(10**decimals)
