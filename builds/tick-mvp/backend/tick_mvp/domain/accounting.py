from __future__ import annotations

from decimal import Decimal
from typing import Any


def whole_trade_wallet_delta(
    position_payload: dict[str, Any] | None,
    account_balance_after_usd: Decimal | None,
) -> Decimal | None:
    if account_balance_after_usd is None:
        return None
    raw_baseline = (position_payload or {}).get("accountBalanceBeforeOpenUsd")
    if raw_baseline is None:
        return None
    return account_balance_after_usd - Decimal(str(raw_baseline))


def net_wallet_delta(
    position_payload: dict[str, Any] | None,
    account_balance_after_usd: Decimal | None,
    gas_ledger_total_usd: Decimal = Decimal(0),
) -> Decimal | None:
    wallet_delta = whole_trade_wallet_delta(
        position_payload,
        account_balance_after_usd,
    )
    if wallet_delta is None:
        return None
    return wallet_delta + gas_ledger_total_usd
