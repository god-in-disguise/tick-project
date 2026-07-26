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
) -> VenueQuote:
    if ticket_usd <= 0:
        raise GTradeError("ticket must be positive")
    leverage = gtrade_execution_leverage(pair, requested_leverage)
    if leverage <= 0 or leverage > pair.max_leverage:
        raise GTradeError(f"{pair.pair} max leverage is {pair.max_leverage}x")
    if ticket_usd < pair.min_collateral_usd:
        raise GTradeError(f"{pair.pair} min margin is ${pair.min_collateral_usd:.2f}")

    bid = Decimal(str(live["bid"]))
    ask = Decimal(str(live["ask"]))
    execution_price = ask if side == TradeSide.LONG else bid
    notional = ticket_usd * leverage
    open_fee = notional * (pair.open_fee_pct / Decimal(100))
    close_fee = notional * (pair.open_fee_pct / Decimal(100))
    spread_cost = notional * (pair.spread_pct / Decimal(100))
    round_trip = open_fee + close_fee + spread_cost
    active_collateral = ticket_usd - open_fee
    if active_collateral <= 0:
        raise GTradeError("ticket is too small for gTrade fee at selected leverage")

    liquidation = _liquidation_estimate(execution_price, side, leverage)
    stop_loss = _stop_loss_estimate(execution_price, side, notional, max_loss_usd)
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
            "activeCollateralUsd": str(active_collateral),
            "effectiveNotionalUsd": str(notional),
            "estimatedSpreadCostUsd": str(spread_cost),
            "feeHurdlePct": str((round_trip / notional) * Decimal(100) if notional else Decimal(999)),
            "maxVenueLeverage": str(pair.max_leverage),
            "slippageBps": 100,
            "marketOpen": bool(live.get("isMarketOpen", True)),
        },
    )


def _liquidation_estimate(entry: Decimal, side: TradeSide, leverage: Decimal) -> Decimal:
    distance = Decimal("0.80") / leverage
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

