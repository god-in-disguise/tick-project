from __future__ import annotations

from decimal import Decimal
from typing import Any

from .gtrade_public import GTradeError, GTradePair


def estimate_open(
    pair: GTradePair,
    live: dict[str, Any],
    side: str,
    ticket_usd: Decimal,
    leverage: Decimal,
) -> dict[str, Any]:
    if side not in {"long", "short"}:
        raise GTradeError("side must be long or short")
    if ticket_usd <= 0:
        raise GTradeError("ticket must be positive")
    if leverage <= 0 or leverage > pair.max_leverage:
        raise GTradeError(f"{pair.pair} max leverage is {pair.max_leverage}x")
    if ticket_usd < pair.min_collateral_usd:
        raise GTradeError(f"{pair.pair} min margin is ${pair.min_collateral_usd:.2f}")

    mid = Decimal(str(live["mid"]))
    bid = Decimal(str(live["bid"]))
    ask = Decimal(str(live["ask"]))
    execution_price = ask if side == "long" else bid
    notional = ticket_usd * leverage
    open_fee = notional * (pair.open_fee_pct / Decimal(100))
    close_fee = open_fee
    spread_cost = notional * (pair.spread_pct / Decimal(100))
    all_in_cost = open_fee + close_fee + spread_cost
    fee_hurdle_pct = (all_in_cost / notional) * Decimal(100) if notional else Decimal(999)
    active_collateral = ticket_usd - open_fee
    if active_collateral <= 0:
        raise GTradeError("ticket is too small for gTrade fee at selected leverage")

    return {
        "venue": "gtrade",
        "pair": pair.pair,
        "side": side,
        "ticketUsd": float(ticket_usd),
        "leverage": float(leverage),
        "notionalUsd": float(notional),
        "activeCollateralUsd": float(active_collateral),
        "effectiveNotionalUsd": float(notional),
        "collateralAtRiskUsd": float(ticket_usd),
        "price": float(execution_price),
        "mid": float(mid),
        "bid": float(bid),
        "ask": float(ask),
        "spreadPct": float(pair.spread_pct),
        "estimatedOpeningFeeUsd": float(open_fee),
        "estimatedOpenCostUsd": float(open_fee),
        "estimatedCloseCostUsd": float(close_fee),
        "estimatedAllInCostUsd": float(all_in_cost),
        "feeHurdlePct": float(fee_hurdle_pct),
        "estimatedLiquidationPrice": float(_liquidation_estimate(execution_price, side, leverage)),
        "liquidationEstimateApproximate": True,
        "maxVenueLeverage": float(pair.max_leverage),
        "slippageBps": 100,
        "takerFeeRate": float(pair.open_fee_pct / Decimal(100)),
        "takerFeeBps": float(pair.open_fee_pct * Decimal(100)),
        "marketOpen": bool(live.get("isMarketOpen", True)),
    }


def estimate_close(pair: GTradePair, position: dict[str, Any], live: dict[str, Any]) -> dict[str, Any]:
    side = position.get("side")
    execution_price = live["bid"] if side == "long" else live["ask"]
    return {
        "venue": "gtrade",
        "pair": pair.pair,
        "position": position,
        "price": execution_price,
        "estimatedCloseCostUsd": 0.0,
        "slippageBps": 100,
        "marketOpen": bool(live.get("isMarketOpen", True)),
    }


def _liquidation_estimate(entry: Decimal, side: str, leverage: Decimal) -> Decimal:
    # gTrade exact liquidation includes pair params, spreads, fees, and collateral type.
    # This conservative display estimate keeps the phone UI directionally truthful.
    distance = Decimal("0.80") / leverage
    return entry * (Decimal(1) - distance if side == "long" else Decimal(1) + distance)
