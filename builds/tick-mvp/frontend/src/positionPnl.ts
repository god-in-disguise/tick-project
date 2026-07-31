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
  return Math.max(-Math.abs(position.ticketUsd), gross - estimatedCost);
}
