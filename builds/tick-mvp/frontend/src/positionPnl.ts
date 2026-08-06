import type { Market, Position, Quote } from "./types";

export function liquidationThresholdCrossed(position: Position, marketPrice: number): boolean {
  const liquidationPrice = position.liquidationPrice;
  if (
    liquidationPrice === null
    || !Number.isFinite(liquidationPrice)
    || !Number.isFinite(marketPrice)
  ) {
    return false;
  }
  return position.side === "long"
    ? marketPrice <= liquidationPrice
    : marketPrice >= liquidationPrice;
}

export function positionNetPnl(
  position: Position | null,
  market: Market | null,
  quote: Quote | null
): number | null {
  if (
    position?.venue === "flash"
    && typeof position.venueEstimatedNetPnlUsd === "number"
    && Number.isFinite(position.venueEstimatedNetPnlUsd)
  ) {
    return Math.max(
      -Math.abs(position.ticketUsd),
      position.venueEstimatedNetPnlUsd
    );
  }
  if (!position?.entryPrice || !market || position.market !== market.market) return null;
  const estimatedCost = quote?.estimatedRoundTripCostUsd ?? 0;
  const latestObservation = market.observations.at(-1);
  const positionConfirmedAt = Date.parse(position.openedAt ?? position.updatedAt) / 1_000;
  if (!latestObservation || latestObservation.receivedTs < positionConfirmedAt) {
    return -estimatedCost;
  }
  if (liquidationThresholdCrossed(position, market.price)) {
    return -Math.abs(position.ticketUsd);
  }
  const direction = position.side === "long" ? 1 : -1;
  const gross = (
    (market.price - position.entryPrice)
    / position.entryPrice
  ) * position.notionalUsd * direction;
  if (position.venue === "avantis") {
    const profitFee = gross > 0
      ? gross * profitFeeShare(quote, gross / position.ticketUsd * 100) / 100
      : 0;
    return Math.max(-Math.abs(position.ticketUsd), gross - profitFee);
  }
  return Math.max(-Math.abs(position.ticketUsd), gross - estimatedCost);
}

export function profitFeeShare(quote: Quote | null, profitPct: number): number {
  if (!quote?.profitFeeTiers?.length || !Number.isFinite(profitPct) || profitPct <= 0) {
    return 0;
  }
  let share = quote.profitFeeTiers[0]?.feeSharePct ?? 0;
  for (const tier of quote.profitFeeTiers) {
    if (profitPct < tier.minProfitPct) break;
    share = tier.feeSharePct;
  }
  return share;
}
