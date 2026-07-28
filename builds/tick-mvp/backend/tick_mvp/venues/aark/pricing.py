from __future__ import annotations

from decimal import Decimal

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.aark.constants import (
    AARK_INITIAL_PROFIT_FEE_PCT,
    AARK_MATURE_PROFIT_FEE_PCT,
    AARK_MAX_PROFIT_PCT,
    AARK_PROFIT_FEE_DECAY_SECONDS,
)
from tick_mvp.venues.aark.public import AarkError, AarkMarket
from tick_mvp.venues.base import VenueQuote


def estimate_open(
    market: AarkMarket,
    *,
    side: TradeSide,
    ticket_usd: Decimal,
    requested_leverage: Decimal,
    max_loss_usd: Decimal | None,
    take_profit_usd: Decimal | None,
    execution_fee_usd: Decimal,
    requires_open_challenge: bool,
    execution_enabled: bool,
) -> VenueQuote:
    leverage = _execution_leverage(market, requested_leverage)
    if ticket_usd < Decimal("10"):
        raise AarkError("Aark requires at least $10 collateral")
    if market.initial_margin_cap_usd and ticket_usd > market.initial_margin_cap_usd:
        raise AarkError(
            f"{market.symbol} supports at most ${market.initial_margin_cap_usd} collateral on Aark"
        )

    notional = ticket_usd * leverage
    trading_fee = notional * (market.base_fee_pct / Decimal(100))
    open_cost = trading_fee + execution_fee_usd
    requested_stop_is_supported = max_loss_usd is None or max_loss_usd >= ticket_usd
    maximum_take_profit_pct = min(
        market.take_profit_cap_pct,
        Decimal(AARK_MAX_PROFIT_PCT),
    )
    take_profit_pct = (
        take_profit_usd / ticket_usd * Decimal(100)
        if take_profit_usd is not None
        else min(Decimal(100), maximum_take_profit_pct)
    )
    if take_profit_pct > maximum_take_profit_pct:
        raise AarkError(
            f"{market.symbol} take profit is capped at {maximum_take_profit_pct}% of collateral on Aark"
        )

    reference = market.index_price
    target_profit_usd = ticket_usd * take_profit_pct / Decimal(100)
    take_profit_price = _target_price(
        reference,
        side,
        target_profit_usd,
        notional,
    )
    opening_allowed = (
        market.opening_allowed
        and execution_enabled
        and requested_stop_is_supported
    )
    blocked_reason = None
    if not execution_enabled:
        blocked_reason = "aark_live_execution_disabled"
    elif not requested_stop_is_supported:
        blocked_reason = "native_stop_loss_unavailable"
    elif not market.opening_allowed:
        blocked_reason = "market_unavailable"

    return VenueQuote(
        venue="aark",
        market=market.market,
        side=side,
        ticket_usd=ticket_usd,
        leverage=leverage,
        notional_usd=notional,
        estimated_open_cost_usd=open_cost,
        estimated_close_cost_usd=Decimal(0),
        estimated_round_trip_cost_usd=open_cost,
        liquidation_price=None,
        stop_loss_price=None,
        take_profit_price=take_profit_price,
        opening_allowed=opening_allowed,
        payload={
            "marketId": market.market_id,
            "symbol": market.symbol,
            "referencePrice": str(reference),
            "indexPrice": str(market.index_price),
            "marketPrice": str(market.market_price),
            "baseFeePct": str(market.base_fee_pct),
            "tradingOpenFeeUsd": str(trading_fee),
            "executionFeeUsd": str(execution_fee_usd),
            "positivePnlFeePctNow": str(AARK_INITIAL_PROFIT_FEE_PCT),
            "positivePnlFeePctAfter30s": str(AARK_MATURE_PROFIT_FEE_PCT),
            "positivePnlFeeDecaySeconds": AARK_PROFIT_FEE_DECAY_SECONDS,
            "profitCapPct": str(maximum_take_profit_pct),
            "profitCapUsd": str(ticket_usd * maximum_take_profit_pct / Decimal(100)),
            "takeProfitPct": str(take_profit_pct),
            "mmrPct": str(market.mmr_pct),
            "nativeStopLoss": False,
            "maxLossUsd": str(ticket_usd),
            "requiresOpenChallenge": requires_open_challenge,
            "openChallengeKind": "recaptcha_enterprise" if requires_open_challenge else None,
            "openingBlockedReason": blocked_reason,
            "venueMarket": market.payload,
        },
    )


def _execution_leverage(market: AarkMarket, requested: Decimal) -> Decimal:
    if requested < market.min_leverage or requested > market.max_leverage:
        raise AarkError(
            f"{market.symbol} supports leverage from {market.min_leverage}x to {market.max_leverage}x on Aark"
        )
    if market.leverage_steps and requested not in market.leverage_steps:
        allowed = ", ".join(f"{value}x" for value in market.leverage_steps)
        raise AarkError(f"{market.symbol} supports {allowed} on Aark")
    return requested


def _target_price(
    reference: Decimal,
    side: TradeSide,
    target_profit_usd: Decimal | None,
    notional_usd: Decimal,
) -> Decimal | None:
    if target_profit_usd is None or notional_usd <= 0:
        return None
    move = target_profit_usd / notional_usd
    direction = Decimal(1) if side == TradeSide.LONG else Decimal(-1)
    return reference * (Decimal(1) + move * direction)
