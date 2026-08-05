from __future__ import annotations

from decimal import Decimal
from typing import Any

from tick_mvp.venues.flash.constants import USDC_MINT, USD_DECIMALS


def available_collateral_usd(
    raw_basket: dict[str, Any],
    deposited_usdc: Decimal,
) -> Decimal:
    """Compose Flash's UDL and basket accounting into spendable USDC."""
    account = raw_basket.get("account") or {}
    debits = _mint_amount(account.get("debits") or [])
    pending_credits = _mint_amount(account.get("pendingCredits") or [])
    available = (
        deposited_usdc
        - Decimal(debits).scaleb(-USD_DECIMALS)
        + Decimal(pending_credits).scaleb(-USD_DECIMALS)
    )
    return max(Decimal(0), available)


def _mint_amount(rows: list[dict[str, Any]]) -> int:
    return sum(
        int(row.get("amount") or 0)
        for row in rows
        if row.get("mint") == USDC_MINT
    )
