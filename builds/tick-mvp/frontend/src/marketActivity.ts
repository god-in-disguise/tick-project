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

  if (market.feedStatus === "disconnected" || market.feedStatus === "stale") {
    return { story: "MARKET DATA STALE", pace: "QUIET", rangePositionPct };
  }
  if (market.feedStatus === "resyncing" || market.feedStatus === "delayed") {
    return { story: "MARKET DATA DELAYED", pace: "QUIET", rangePositionPct };
  }
  if (!market.openingAllowed) {
    return { story: "OPENING PAUSED", pace, rangePositionPct };
  }

  const recent = activityAverage(bars.slice(-5));
  const baseline = activityAverage(bars.slice(-20, -5));
  if (baseline > 0 && recent >= baseline * 1.65) {
    return { story: "PACE ACCELERATING", pace, rangePositionPct };
  }
  if (rangePositionPct >= 94) {
    return { story: "NEAR 90s HIGH", pace, rangePositionPct };
  }
  if (rangePositionPct <= 6) {
    return { story: "NEAR 90s LOW", pace, rangePositionPct };
  }
  if (market.feeHurdlePct > 0 && market.activeTapePct >= market.feeHurdlePct * 2) {
    return {
      story: `${(market.activeTapePct / market.feeHurdlePct).toFixed(1)}× COST COVERAGE`,
      pace,
      rangePositionPct
    };
  }
  if (market.activitySurplusPct >= 0) {
    return { story: "COST COVERED", pace, rangePositionPct };
  }
  if (baseline > 0 && recent <= baseline * 0.48) {
    return { story: "PACE COOLING", pace, rangePositionPct };
  }
  return { story: "WATCHING", pace, rangePositionPct };
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
