from __future__ import annotations

from decimal import Decimal
from typing import Any

from . import ostium_client as raw


def estimate_open(
    pair: str,
    side: str,
    ticket_usd: Decimal,
    leverage: Decimal,
    *,
    live: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if side not in {"long", "short"}:
        raise raw.OstiumError("side must be long or short")
    if leverage not in {Decimal("25"), Decimal("50"), Decimal("100")}:
        raise raw.OstiumError("leverage must be one of 25, 50, or 100")
    if ticket_usd <= 0:
        raise raw.OstiumError("ticket must be positive")

    pair_config = raw._find_pair(pair)
    pair_name = raw._pair_key(pair_config)
    max_leverage = raw._max_leverage(pair_config)
    if max_leverage > 0 and leverage > max_leverage:
        raise raw.OstiumError(f"{pair_name} max leverage is {max_leverage}x")

    live = live or raw._prices(fresh=True).get(pair_name)
    if not live:
        raise raw.OstiumError(f"price not found: {pair_name}")
    if not live.get("isMarketOpen", True):
        raise raw.OstiumError(f"{pair_name} market is closed")

    mid = raw._dec(live["mid"])
    bid = raw._dec(live["bid"])
    ask = raw._dec(live["ask"])
    execution_price = ask if side == "long" else bid
    taker_fee_rate = raw._taker_fee_rate(pair_config)
    notional = ticket_usd * leverage
    opening_fee = notional * taker_fee_rate
    oracle_reserve = raw.DEFAULT_ORDER_RESERVE_USDC
    active_collateral = ticket_usd - opening_fee - oracle_reserve
    if active_collateral <= 0:
        raise raw.OstiumError("ticket is too small for the selected leverage and fees")

    effective_notional = active_collateral * leverage
    spread_pct = ((ask - bid) / mid) * Decimal(100) if mid else Decimal(0)
    spread_cost = effective_notional * spread_pct / Decimal(100)
    conservative_cost = opening_fee + oracle_reserve + spread_cost
    hurdle_pct = conservative_cost / effective_notional * Decimal(100) if effective_notional else Decimal(999)
    liquidation = raw._liquidation_estimate(execution_price, side, leverage, max_leverage)

    return {
        "venue": "ostium",
        "pair": pair_name,
        "side": side,
        "ticketUsd": float(ticket_usd),
        "leverage": float(leverage),
        "notionalUsd": float(notional),
        "activeCollateralUsd": float(active_collateral),
        "effectiveNotionalUsd": float(effective_notional),
        "collateralAtRiskUsd": float(ticket_usd),
        "price": float(execution_price),
        "mid": float(mid),
        "bid": float(bid),
        "ask": float(ask),
        "spreadPct": float(spread_pct),
        "estimatedOpeningFeeUsd": float(opening_fee),
        "oracleReserveUsd": float(oracle_reserve),
        "oracleReserveRefundableOnFullClose": True,
        "estimatedSpreadCostUsd": float(spread_cost),
        "estimatedOpenCostUsd": float(opening_fee + oracle_reserve),
        "estimatedCloseCostUsd": 0.0,
        "estimatedAllInCostUsd": float(conservative_cost),
        "feeHurdlePct": float(hurdle_pct),
        "estimatedLiquidationPrice": float(liquidation) if liquidation is not None else None,
        "liquidationEstimateApproximate": True,
        "maxVenueLeverage": float(max_leverage),
        "slippageBps": raw.DEFAULT_SLIPPAGE_BPS,
        "takerFeeRate": float(taker_fee_rate),
        "takerFeeBps": float(taker_fee_rate * Decimal(10000)),
        "marketOpen": True,
    }


def estimate_close(pair: str) -> dict[str, Any]:
    pair_name = raw._normalize_pair(pair)
    account = raw.positions()
    position = next((item for item in account["positions"] if item["pair"] == pair_name), None)
    if position is None:
        raise raw.OstiumError(f"no open position for {pair_name}")
    live = raw.pair_price(pair_name)["price"]
    execution_price = live["bid"] if position["side"] == "long" else live["ask"]
    return {
        "venue": "ostium",
        "pair": pair_name,
        "position": position,
        "price": execution_price,
        "estimatedCloseCostUsd": 0.0,
        "slippageBps": raw.DEFAULT_SLIPPAGE_BPS,
        "marketOpen": live["open"],
    }
