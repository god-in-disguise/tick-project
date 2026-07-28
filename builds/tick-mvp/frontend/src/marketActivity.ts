import type { Market, MarketObservation } from "./types";

export type MicroBar = {
  startTs: number;
  endTs: number;
  open: number;
  high: number;
  low: number;
  close: number;
  updates: number;
  changedUpdates: number;
  movementPct: number;
};

export type MarketPulse = {
  story: string;
  pace: "QUIET" | "ACTIVE" | "FAST";
  rangePositionPct: number;
  recentRangePct: number;
};

export function buildMicroBars(
  observations: MarketObservation[],
  nowSeconds: number,
  bucketSeconds = 2,
  windowSeconds = 90
): MicroBar[] {
  const start = nowSeconds - windowSeconds;
  const buckets = new Map<number, MicroBar>();
  let previousPrice: number | null = null;

  for (const observation of observations) {
    if (
      observation.receivedTs < start
      || observation.receivedTs > nowSeconds + 1
      || !Number.isFinite(observation.price)
      || observation.price <= 0
    ) {
      continue;
    }

    const startTs = Math.floor(observation.receivedTs / bucketSeconds) * bucketSeconds;
    const existing = buckets.get(startTs);
    const changed = previousPrice !== null && observation.price !== previousPrice;
    const movementPct = previousPrice && changed
      ? Math.abs(observation.price - previousPrice) / previousPrice * 100
      : 0;

    if (existing) {
      existing.high = Math.max(existing.high, observation.price);
      existing.low = Math.min(existing.low, observation.price);
      existing.close = observation.price;
      existing.updates += 1;
      existing.changedUpdates += changed ? 1 : 0;
      existing.movementPct += movementPct;
    } else {
      buckets.set(startTs, {
        startTs,
        endTs: startTs + bucketSeconds,
        open: observation.price,
        high: observation.price,
        low: observation.price,
        close: observation.price,
        updates: 1,
        changedUpdates: changed ? 1 : 0,
        movementPct
      });
    }
    previousPrice = observation.price;
  }

  return [...buckets.values()].sort((left, right) => left.startTs - right.startTs);
}

export function describeMarket(market: Market, bars: MicroBar[]): MarketPulse {
  const rangePositionPct = rangePosition(market);
  const pace = paceFor(bars);
  const latestEndTs = bars.at(-1)?.endTs ?? 0;
  const recentBars = bars.filter((bar) => bar.endTs > latestEndTs - 10);
  const baselineBars = bars.filter(
    (bar) => bar.endTs <= latestEndTs - 10 && bar.endTs > latestEndTs - 40
  );
  const recentRangePct = barRangePct(recentBars, market.price);

  if (!market.openingAllowed) {
    return { story: "MARKET PAUSED", pace, rangePositionPct, recentRangePct };
  }

  const recent = activityAverage(recentBars);
  const baseline = activityAverage(baselineBars);
  if (baseline > 0 && recent >= baseline * 1.65) {
    return { story: "COST TEMPO RISING", pace, rangePositionPct, recentRangePct };
  }
  if (rangePositionPct >= 94) {
    return { story: "NEAR 90s HIGH", pace, rangePositionPct, recentRangePct };
  }
  if (rangePositionPct <= 6) {
    return { story: "NEAR 90s LOW", pace, rangePositionPct, recentRangePct };
  }
  if (baseline > 0 && recent <= baseline * 0.48) {
    return { story: "COST TEMPO COOLING", pace, rangePositionPct, recentRangePct };
  }
  return {
    story: pace === "FAST" ? "COST TEMPO FAST" : pace === "ACTIVE" ? "COST TEMPO ACTIVE" : "COST TEMPO QUIET",
    pace,
    rangePositionPct,
    recentRangePct
  };
}

function paceFor(bars: MicroBar[]): MarketPulse["pace"] {
  if (bars.length < 3) return "QUIET";
  const recent = activityAverage(bars.slice(-5));
  const baseline = activityAverage(bars.slice(-20));
  if (recent > 0 && recent >= baseline * 1.55) return "FAST";
  if (recent > 0 && recent >= baseline * 0.7) return "ACTIVE";
  return "QUIET";
}

function activityAverage(bars: MicroBar[]): number {
  if (!bars.length) return 0;
  return bars.reduce(
    (total, bar) => total + bar.movementPct + Math.log1p(bar.changedUpdates) * 0.0001,
    0
  ) / bars.length;
}

function barRangePct(bars: MicroBar[], current: number): number {
  if (!bars.length || current <= 0) return 0;
  const high = Math.max(...bars.map((bar) => bar.high));
  const low = Math.min(...bars.map((bar) => bar.low));
  return (high - low) / current * 100;
}

function rangePosition(market: Market): number {
  const prices = market.observations
    .filter((observation) => Number.isFinite(observation.price) && observation.price > 0)
    .map((observation) => observation.price);
  if (!prices.length) return 50;
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  if (high <= low) return 50;
  return clamp((market.price - low) / (high - low) * 100, 0, 100);
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
