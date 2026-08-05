from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import requests

from tick_mvp.core.config import Settings
from tick_mvp.domain.schemas import WalletAccountResponse, WalletBalancesResponse
from tick_mvp.domain.states import VenueMode
from tick_mvp.venues.flash.constants import SOLANA_MAINNET_CHAIN_ID, USDC_MINT, USD_DECIMALS


def read_flash_wallet_balances(
    wallet: WalletAccountResponse,
    settings: Settings,
) -> WalletBalancesResponse:
    fetched_at = datetime.now(UTC)
    if not settings.solana_rpc_url:
        return _unavailable(wallet, fetched_at, "SOLANA_RPC_URL is not configured")
    try:
        rpc_payload = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getBalance",
                "params": [wallet.address, {"commitment": "confirmed"}],
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "getTokenAccountsByOwner",
                "params": [
                    wallet.address,
                    {"mint": USDC_MINT},
                    {"encoding": "jsonParsed", "commitment": "confirmed"},
                ],
            },
        ]
        rpc_response = requests.post(
            settings.solana_rpc_url,
            json=rpc_payload,
            timeout=6,
            headers={"user-agent": "tick-mvp-flash/0.1"},
        )
        rpc_response.raise_for_status()
        rpc = _result_by_id(rpc_response.json())
        native_sol = Decimal(int(rpc[1]["value"])).scaleb(-9)
        wallet_usdc = _token_total(rpc[2])

        owner_response = requests.get(
            f"{settings.flash_api_url.rstrip('/')}/owner/{wallet.address}",
            timeout=6,
            headers={"user-agent": "tick-mvp-flash/0.1"},
        )
        owner_response.raise_for_status()
        basket = owner_response.json().get("basketPubkey")
        venue_ready = bool(basket)
        spendable = Decimal(0)
        if basket:
            basket_response = requests.get(
                f"{settings.flash_api_url.rstrip('/')}/raw/baskets/{basket}",
                timeout=6,
                headers={"user-agent": "tick-mvp-flash/0.1"},
            )
            basket_response.raise_for_status()
            spendable = _basket_available_usdc(basket_response.json())
        return WalletBalancesResponse(
            chainId=SOLANA_MAINNET_CHAIN_ID,
            address=wallet.address,
            nativeEth=native_sol,
            usdc=spendable,
            onchainUsdc=wallet_usdc,
            gasChargesUsdc=Decimal(0),
            spendableUsdc=spendable,
            gtradeAllowanceUsdc=None,
            venue=VenueMode.FLASH,
            network="Solana",
            venueReady=venue_ready,
            source="solana_rpc+flash_raw_basket",
            fetchedAt=fetched_at,
            unavailableReason=None if venue_ready else "Flash account setup is pending",
        )
    except Exception as exc:
        return _unavailable(wallet, fetched_at, f"{type(exc).__name__}: {exc}")


def _result_by_id(payload: object) -> dict[int, dict]:
    if not isinstance(payload, list):
        raise ValueError("Solana RPC batch returned non-list payload")
    results: dict[int, dict] = {}
    for item in payload:
        if not isinstance(item, dict) or item.get("error"):
            raise ValueError(f"Solana RPC error: {item}")
        results[int(item["id"])] = item["result"]
    return results


def _token_total(payload: dict) -> Decimal:
    total = Decimal(0)
    for row in payload.get("value") or []:
        token = row["account"]["data"]["parsed"]["info"]["tokenAmount"]
        total += Decimal(str(token["amount"])).scaleb(-int(token["decimals"]))
    return total


def _basket_available_usdc(payload: dict) -> Decimal:
    account = payload.get("account") or {}
    debits = _mint_amount(account.get("debits") or [])
    pending_credits = _mint_amount(account.get("pendingCredits") or [])
    return max(Decimal(0), Decimal(debits - pending_credits).scaleb(-USD_DECIMALS))


def _mint_amount(rows: list[dict]) -> int:
    return sum(int(row.get("amount") or 0) for row in rows if row.get("mint") == USDC_MINT)


def _unavailable(
    wallet: WalletAccountResponse,
    fetched_at: datetime,
    reason: str,
) -> WalletBalancesResponse:
    return WalletBalancesResponse(
        chainId=SOLANA_MAINNET_CHAIN_ID,
        address=wallet.address,
        venue=VenueMode.FLASH,
        network="Solana",
        venueReady=False,
        source="unavailable",
        fetchedAt=fetched_at,
        unavailableReason=reason,
    )
