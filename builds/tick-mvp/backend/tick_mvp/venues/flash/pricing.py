from __future__ import annotations

from decimal import Decimal
from typing import Any

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.base import VenueQuote
from tick_mvp.venues.flash.client import FlashError
from tick_mvp.venues.flash.constants import FlashMarket


def normalize_open_quote(
    market: FlashMarket,
    response: dict[str, Any],
    *,
    side: TradeSide,
    ticket_usd: Decimal,
    requested_leverage: Decimal,
    max_loss_usd: Decimal | None,
    take_profit_usd: Decimal | None,
    execution_enabled: bool,
) -> VenueQuote:
    if ticket_usd <= 0:
        raise FlashError("ticket must be positive")
    if requested_leverage <= 0 or requested_leverage > market.max_leverage:
        raise FlashError(
            f"{market.symbol} supports at most {market.max_leverage}x on Flash"
        )

    entry_price = _decimal(response, "newEntryPrice")
    liquidation_price = _decimal(response, "newLiquidationPrice")
    effective_notional = _decimal(response, "youRecieveUsdUi")
    open_cost = _decimal(response, "entryFee")
    open_fee_percent = _optional_decimal(response.get("openPositionFeePercent"))
    close_cost = (
        effective_notional * open_fee_percent / Decimal(100)
        if open_fee_percent is not None
        else open_cost
    )
    capacity_passed = all(
        bool(response.get(key))
        for key in ("passesMaxPositionSize", "passesMaxExposure", "passesMaxUtilization")
    )
    triggers_requested = max_loss_usd is not None or take_profit_usd is not None
    opening_allowed = (
        execution_enabled
        and market.execution_certified
        and capacity_passed
        and not triggers_requested
    )
    blocked_reason = None
    if not execution_enabled:
        blocked_reason = "flash_live_execution_disabled"
    elif not market.execution_certified:
        blocked_reason = "market_not_canary_certified"
    elif not capacity_passed:
        blocked_reason = "venue_capacity_check_failed"
    elif triggers_requested:
        blocked_reason = "native_trigger_orders_not_certified"

    return VenueQuote(
        venue="flash",
        market=market.market,
        side=side,
        ticket_usd=ticket_usd,
        leverage=requested_leverage,
        notional_usd=effective_notional,
        estimated_open_cost_usd=open_cost,
        estimated_close_cost_usd=close_cost,
        estimated_round_trip_cost_usd=open_cost + close_cost,
        liquidation_price=liquidation_price,
        stop_loss_price=None,
        take_profit_price=None,
        opening_allowed=opening_allowed,
        payload={
            "price": str(entry_price),
            "symbol": market.symbol,
            "assetClass": market.asset_class,
            "requestedNotionalUsd": str(ticket_usd * requested_leverage),
            "effectiveNotionalUsd": str(effective_notional),
            "venueLeverage": str(_decimal(response, "newLeverage")),
            "venueCollateralUsd": str(_decimal(response, "youPayUsdUi")),
            "openFeeUsd": str(open_cost),
            "estimatedCloseFeeUsd": str(close_cost),
            "openFeePercent": str(open_fee_percent or ""),
            "maintenanceLeverage": str(market.maintenance_leverage),
            "availableLiquidityUsd": str(response.get("availableLiquidity") or ""),
            "maxPositionSizeUsd": str(response.get("maxPositionSizeUsd") or ""),
            "openingBlockedReason": blocked_reason,
            "capacityPassed": capacity_passed,
            "nativeTriggerOrdersCertified": False,
            "quote": response,
        },
    )


def _decimal(payload: dict[str, Any], key: str) -> Decimal:
    value = payload.get(key)
    if value is None:
        raise FlashError(f"Flash quote is missing {key}")
    return Decimal(str(value))


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))
