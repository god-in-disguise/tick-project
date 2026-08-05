import type { Market, TradeSettings } from "./types";

export function minimumTicketUsd(market: Market, leverage: number): number {
  const venueLeverage = Math.max(1, Math.min(leverage, market.maxLeverage));
  const notionalMinimum = Math.ceil(market.minPositionSizeUsd / venueLeverage * 100) / 100;
  return Math.max(market.minCollateralUsd ?? 0, notionalMinimum);
}

export function effectiveTicketUsd(settings: TradeSettings, market: Market): number {
  return settings.amountMode === "minimum"
    ? minimumTicketUsd(market, settings.leverage)
    : settings.ticketUsd;
}

export function effectiveLeverage(settings: TradeSettings, market: Market): number {
  return Math.max(1, Math.min(settings.leverage, market.maxLeverage));
}

export function estimatedRouteCostUsd(
  market: Market,
  ticketUsd: number,
  leverage: number
): number {
  return ticketUsd * Math.min(leverage, market.maxLeverage) * market.feeHurdlePct / 100;
}

export function ticketMeetsMarketMinimum(settings: TradeSettings, market: Market): boolean {
  return effectiveTicketUsd(settings, market) >= minimumTicketUsd(market, settings.leverage);
}
