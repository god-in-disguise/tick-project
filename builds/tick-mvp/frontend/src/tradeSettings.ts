import type { Market, TradeSettings } from "./types";

export function minimumTicketUsd(market: Market, leverage: number): number {
  const venueLeverage = Math.max(1, Math.min(leverage, market.maxLeverage));
  return Math.ceil(market.minPositionSizeUsd / venueLeverage * 100) / 100;
}

export function effectiveTicketUsd(settings: TradeSettings, market: Market): number {
  return settings.amountMode === "minimum"
    ? minimumTicketUsd(market, settings.leverage)
    : settings.ticketUsd;
}

export function ticketMeetsMarketMinimum(settings: TradeSettings, market: Market): boolean {
  return effectiveTicketUsd(settings, market) >= minimumTicketUsd(market, settings.leverage);
}
