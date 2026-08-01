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
  heat: "QUIET" | "WARM" | "ACTIVE" | "HOT";
  rangePositionPct: number;
  recentRangePct: number;
  tempoRatio: number;
  heatSamples: number[];
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

export function describeMarket(
  market: Market,
  bars: MicroBar[],
  nowSeconds = Date.now() / 1_000
): MarketPulse {
  const rangePositionPct = rangePosition(market);
  const recentBars = bars.filter((bar) => bar.endTs > nowSeconds - 10);
  const baselineBars = bars.filter(
    (bar) => bar.endTs <= nowSeconds - 10 && bar.endTs > nowSeconds - 40
  );
  const recentRangePct = barRangePct(recentBars, market.price);
  const recent = activityAverage(recentBars);
  const baseline = activityAverage(baselineBars);
  const tempoRatio = baseline > 0 ? recent / baseline : recent > 0 ? 1 : 0;
  const heat = heatFor(tempoRatio);
  const pace: MarketPulse["pace"] = heat === "HOT"
    ? "FAST"
    : heat === "QUIET"
      ? "QUIET"
      : "ACTIVE";
  const heatSamples = activitySamples(recentBars, baseline, nowSeconds);
  const pulse = { pace, heat, rangePositionPct, recentRangePct, tempoRatio, heatSamples };

  if (!market.openingAllowed) {
    return { story: "MARKET PAUSED", ...pulse };
  }

  if (baseline > 0 && recent >= baseline * 1.65) {
    return { story: "TAPE ACCELERATING", ...pulse };
  }
  if (rangePositionPct >= 94) {
    return { story: "NEAR 90s HIGH", ...pulse };
  }
  if (rangePositionPct <= 6) {
    return { story: "NEAR 90s LOW", ...pulse };
  }
  if (baseline > 0 && recent <= baseline * 0.48) {
    return { story: "TAPE COOLING", ...pulse };
  }
  return {
    story: rangePositionPct >= 75
      ? "90s HIGH ZONE"
      : rangePositionPct <= 25
        ? "90s LOW ZONE"
        : "MID 90s RANGE",
    ...pulse
  };
}

function heatFor(tempoRatio: number): MarketPulse["heat"] {
  if (tempoRatio >= 1.55) return "HOT";
  if (tempoRatio >= 1) return "ACTIVE";
  if (tempoRatio >= 0.6) return "WARM";
  return "QUIET";
}

function activitySamples(
  bars: MicroBar[],
  baseline: number,
  nowSeconds: number
): number[] {
  const bucketSeconds = 2;
  // Only display completed buckets. Including the in-progress bucket made the
  // newest segment repeatedly collapse to zero at every two-second boundary.
  const end = Math.floor(nowSeconds / bucketSeconds) * bucketSeconds;
  const byStart = new Map(bars.map((bar) => [bar.startTs, bar]));
  const raw = Array.from({ length: 5 }, (_, index) => {
    const start = end - (5 - index) * bucketSeconds;
    return barActivity(byStart.get(start));
  });
  const scale = Math.max(baseline * 2, ...raw, Number.EPSILON);
  return raw.map((value) => clamp(value / scale, 0, 1));
}

function barActivity(bar: MicroBar | undefined): number {
  if (!bar) return 0;
  return bar.movementPct + Math.log1p(bar.changedUpdates) * 0.0001;
}

function activityAverage(bars: MicroBar[]): number {
  if (!bars.length) return 0;
  return bars.reduce((total, bar) => total + barActivity(bar), 0) / bars.length;
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
