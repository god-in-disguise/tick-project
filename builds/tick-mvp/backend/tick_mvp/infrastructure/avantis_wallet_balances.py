from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import requests
from eth_account import Account
from eth_utils import keccak

from tick_mvp.core.config import Settings
from tick_mvp.domain.schemas import WalletAccountResponse, WalletBalancesResponse
from tick_mvp.domain.states import VenueMode
from tick_mvp.infrastructure.wallet_balances import (
    _address,
    _hex_decimal,
    _quantize,
    _result_by_id,
    _rpc_batch_payload,
)


def read_avantis_wallet_balances(
    wallet: WalletAccountResponse,
    settings: Settings,
    gas_charges_usdc: Decimal = Decimal(0),
) -> WalletBalancesResponse:
    fetched_at = datetime.now(UTC)
    if not settings.base_rpc_url:
        return WalletBalancesResponse(
            chainId=wallet.chainId,
            address=wallet.address,
            venue=VenueMode.AVANTIS,
            network="Base",
            source="unavailable",
            fetchedAt=fetched_at,
            unavailableReason="BASE_RPC_URL is not configured",
        )
    try:
        payload = _rpc_batch_payload(
            owner=_address(wallet.address),
            token=_address(settings.base_usdc_address),
            spender=_address(settings.avantis_trading_storage_address),
        )
        payload.append(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "eth_call",
                "params": [
                    {
                        "to": _address(settings.avantis_trading_address),
                        "data": _delegation(_address(wallet.address)),
                    },
                    "latest",
                ],
            }
        )
        response = requests.post(
            settings.base_rpc_url,
            json=payload,
            timeout=6,
            headers={"user-agent": "tick-mvp/0.1"},
        )
        response.raise_for_status()
        results = _result_by_id(response.json())
        native_eth = _hex_decimal(results[1], 18)
        usdc = _hex_decimal(results[2], 6)
        allowance = _hex_decimal(results[3], 6)
        delegate = _returned_address(results[4])
    except Exception as exc:
        return WalletBalancesResponse(
            chainId=wallet.chainId,
            address=wallet.address,
            venue=VenueMode.AVANTIS,
            network="Base",
            source="unavailable",
            fetchedAt=fetched_at,
            unavailableReason=f"{type(exc).__name__}: {exc}",
        )
    raw_usdc = _quantize(usdc, 6)
    charges = _quantize(max(Decimal(0), gas_charges_usdc), 6)
    service_address = (
        Account.from_key(settings.platform_gas_wallet_private_key).address.lower()
        if settings.platform_gas_wallet_private_key
        else None
    )
    delegation_ready = service_address is not None and delegate == service_address
    return WalletBalancesResponse(
        chainId=wallet.chainId,
        address=wallet.address,
        nativeEth=_quantize(native_eth, 18),
        usdc=raw_usdc,
        onchainUsdc=raw_usdc,
        gasChargesUsdc=charges,
        spendableUsdc=max(Decimal(0), raw_usdc - charges),
        gtradeAllowanceUsdc=_quantize(allowance, 6),
        venueReady=allowance > 0 and delegation_ready,
        source="base_rpc_batch",
        venue=VenueMode.AVANTIS,
        network="Base",
        fetchedAt=fetched_at,
    )


def _delegation(owner: str) -> str:
    selector = keccak(text="delegations(address)")[:4].hex()
    return f"0x{selector}{owner.removeprefix('0x').rjust(64, '0')}"


def _returned_address(value: str) -> str:
    raw = value.removeprefix("0x").rjust(64, "0")
    return f"0x{raw[-40:]}".lower()
