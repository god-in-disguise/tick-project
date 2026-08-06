from __future__ import annotations

from decimal import Decimal
from typing import Any

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.avantis.catalog import AvantisPair
from tick_mvp.venues.base import VenueQuote


def normalize_open_quote(
    pair: AvantisPair,
    *,
    price: Decimal,
    side: TradeSide,
    ticket_usd: Decimal,
    leverage: Decimal,
    max_loss_usd: Decimal | None,
    take_profit_usd: Decimal | None,
    execution_enabled: bool,
) -> VenueQuote:
    notional = ticket_usd * leverage
    open_cost = notional * pair.pnl_spread_pct / Decimal(100)
    liquidation_move = Decimal("0.8") / leverage
    liquidation_price = price * (
        Decimal(1) - liquidation_move
        if side == TradeSide.LONG
        else Decimal(1) + liquidation_move
    )
    stop_loss_price = _target_price(
        price,
        side,
        notional,
        max_loss_usd,
        favorable=False,
    )
    take_profit_price = _target_price(
        price,
        side,
        notional,
        take_profit_usd,
        favorable=True,
    )
    allowed = (
        execution_enabled
        and pair.market_open
        and pair.feed_stable
        and pair.min_leverage <= leverage <= pair.max_leverage
        and notional >= pair.min_notional_usd
    )
    blocked_reason = _blocked_reason(
        pair,
        leverage=leverage,
        notional=notional,
        execution_enabled=execution_enabled,
    )
    payload: dict[str, Any] = {
        "price": str(price),
        "pairIndex": pair.pair_index,
        "lazerFeedId": pair.lazer_feed_id,
        "orderType": "market_zero_fee",
        "requestedCollateralUsd": str(ticket_usd),
        "effectiveCollateralUsd": str(ticket_usd),
        "requestedNotionalUsd": str(notional),
        "effectiveNotionalUsd": str(notional),
        "pnlSpreadPct": str(pair.pnl_spread_pct),
        "openingAdjustmentUsd": str(open_cost),
        "losingCloseFeeUsd": "0",
        "winningCloseFee": "variable_profit_share",
        "profitFeeTiers": [
            {"minProfitPct": str(threshold), "feeSharePct": str(share)}
            for threshold, share in pair.profit_fee_tiers
        ],
        "minNotionalUsd": str(pair.min_notional_usd),
        "minLeverage": str(pair.min_leverage),
        "maxLeverage": str(pair.max_leverage),
        "openingBlockedReason": blocked_reason,
        "liquidationModel": "estimated_80_percent_collateral_loss",
    }
    return VenueQuote(
        venue="avantis",
        market=pair.market,
        side=side,
        ticket_usd=ticket_usd,
        leverage=leverage,
        notional_usd=notional,
        estimated_open_cost_usd=open_cost,
        estimated_close_cost_usd=Decimal(0),
        estimated_round_trip_cost_usd=open_cost,
        liquidation_price=liquidation_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        opening_allowed=allowed,
        payload=payload,
    )


def _target_price(
    price: Decimal,
    side: TradeSide,
    notional: Decimal,
    budget_usd: Decimal | None,
    *,
    favorable: bool,
) -> Decimal | None:
    if budget_usd is None or budget_usd <= 0 or notional <= 0:
        return None
    move = budget_usd / notional
    direction = Decimal(1) if side == TradeSide.LONG else Decimal(-1)
    if not favorable:
        direction *= Decimal(-1)
    return price * (Decimal(1) + direction * move)


def _blocked_reason(
    pair: AvantisPair,
    *,
    leverage: Decimal,
    notional: Decimal,
    execution_enabled: bool,
) -> str | None:
    if not execution_enabled:
        return "live_execution_disabled"
    if not pair.market_open:
        return "market_closed"
    if not pair.feed_stable:
        return "price_feed_unstable"
    if leverage < pair.min_leverage or leverage > pair.max_leverage:
        return "unsupported_leverage"
    if notional < pair.min_notional_usd:
        return "below_minimum_notional"
    return None
