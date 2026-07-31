from __future__ import annotations

from decimal import Decimal
from typing import Any

from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.base import VenueQuote
from tick_mvp.venues.gtrade.public import GTradeError, GTradePair, gtrade_execution_leverage


def estimate_open(
    pair: GTradePair,
    live: dict[str, Any],
    side: TradeSide,
    ticket_usd: Decimal,
    requested_leverage: Decimal,
    max_loss_usd: Decimal | None,
    take_profit_usd: Decimal | None,
) -> VenueQuote:
    if ticket_usd <= 0:
        raise GTradeError("ticket must be positive")
    leverage = gtrade_execution_leverage(pair, requested_leverage)
    if leverage <= 0 or leverage > pair.max_leverage:
        raise GTradeError(f"{pair.pair} max leverage is {pair.max_leverage}x")
    minimum_collateral = pair.min_position_usd / leverage
    if ticket_usd * leverage < pair.min_position_usd:
        raise GTradeError(f"{pair.pair} min margin is ${minimum_collateral:.2f} at {leverage}x")

    bid = Decimal(str(live["bid"]))
    ask = Decimal(str(live["ask"]))
    execution_price = ask if side == TradeSide.LONG else bid
    notional = ticket_usd * leverage
    open_fee = notional * (pair.open_fee_pct / Decimal(100))
    close_fee = notional * (pair.open_fee_pct / Decimal(100))
    liquidation_fee = ticket_usd * (pair.liquidation_fee_pct / Decimal(100))
    spread_cost = notional * (pair.spread_pct / Decimal(100))
    round_trip = open_fee + close_fee + spread_cost
    trade_value_after_open_fee = ticket_usd - open_fee
    if trade_value_after_open_fee <= 0:
        raise GTradeError("ticket is too small for gTrade fee at selected leverage")

    liquidation = _liquidation_estimate(
        execution_price,
        side,
        ticket_usd,
        leverage,
        open_fee,
        close_fee,
        liquidation_fee,
    )
    stop_loss = _stop_loss_estimate(execution_price, side, notional, max_loss_usd)
    take_profit = _take_profit_estimate(execution_price, side, notional, take_profit_usd)
    return VenueQuote(
        venue="gtrade",
        market=pair.pair,
        side=side,
        ticket_usd=ticket_usd,
        leverage=leverage,
        notional_usd=notional,
        estimated_open_cost_usd=open_fee,
        estimated_close_cost_usd=close_fee,
        estimated_round_trip_cost_usd=round_trip,
        liquidation_price=liquidation,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
        opening_allowed=bool(live.get("isMarketOpen", True)),
        payload={
            "pairIndex": pair.pair_index,
            "requestedLeverage": str(requested_leverage),
            "executionLeverage": str(leverage),
            "leverageNormalized": leverage != requested_leverage,
            "price": str(execution_price),
            "mid": str(live["mid"]),
            "bid": str(bid),
            "ask": str(ask),
            "spreadPct": str(pair.spread_pct),
            "openFeePct": str(pair.open_fee_pct),
            "requestedCollateralUsd": str(ticket_usd),
            "venueCollateralUsd": str(ticket_usd),
            "tradeValueAfterOpenFeeUsd": str(trade_value_after_open_fee),
            "effectiveNotionalUsd": str(notional),
            "realizedOpeningFeeUsd": str(open_fee),
            "estimatedClosingFeeUsd": str(close_fee),
            "estimatedSpreadCostUsd": str(spread_cost),
            "dynamicSpreadIncluded": False,
            "holdingFeesIncluded": False,
            "quoteModelVersion": "gtrade-v10-fixed-costs-v1",
            "estimatedLiquidationFeeUsd": str(liquidation_fee),
            "liquidationEstimateSource": "fee_aware_quote",
            "feeHurdlePct": str((round_trip / notional) * Decimal(100) if notional else Decimal(999)),
            "maxVenueLeverage": str(pair.max_leverage),
            "minPositionSizeUsd": str(pair.min_position_usd),
            "minCollateralUsd": str(minimum_collateral),
            "slippageBps": 100,
            "marketOpen": bool(live.get("isMarketOpen", True)),
        },
    )


def _liquidation_estimate(
    entry: Decimal,
    side: TradeSide,
    collateral: Decimal,
    leverage: Decimal,
    open_fee: Decimal,
    close_fee: Decimal,
    liquidation_fee: Decimal,
) -> Decimal:
    # gTrade's live value also includes holding costs and closing spread. Those
    # become available from the protocol getter once the position exists.
    loss_budget = max(
        Decimal(0),
        collateral * Decimal("0.80") - open_fee - close_fee - liquidation_fee,
    )
    distance = (loss_budget / collateral) / leverage
    return entry * (Decimal(1) - distance if side == TradeSide.LONG else Decimal(1) + distance)


def _stop_loss_estimate(
    entry: Decimal,
    side: TradeSide,
    notional: Decimal,
    max_loss_usd: Decimal | None,
) -> Decimal | None:
    if max_loss_usd is None or max_loss_usd <= 0 or notional <= 0:
        return None
    distance = max_loss_usd / notional
    return entry * (Decimal(1) - distance if side == TradeSide.LONG else Decimal(1) + distance)


def _take_profit_estimate(
    entry: Decimal,
    side: TradeSide,
    notional: Decimal,
    take_profit_usd: Decimal | None,
) -> Decimal | None:
    if take_profit_usd is None or take_profit_usd <= 0 or notional <= 0:
        return None
    distance = take_profit_usd / notional
    return entry * (Decimal(1) + distance if side == TradeSide.LONG else Decimal(1) - distance)
