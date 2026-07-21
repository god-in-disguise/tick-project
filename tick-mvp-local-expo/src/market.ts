import { CHART_WINDOW_SECONDS, MAX_CHART_POINTS } from "./config";
import type { AssetClass, ChartPoint, Direction, Market, MarketSummary, Side, TapeTick, Theme } from "./types";

const themes: Record<AssetClass, Theme> = {
  CRYPTO: { accent: "#ff9f2e", glow: "#ffc166", top: "#0e1817", bottom: "#231e10" },
  STOCK: { accent: "#54ddca", glow: "#8bf3e5", top: "#0b1719", bottom: "#0b2b2e" },
  INDEX: { accent: "#60a5fa", glow: "#93c5fd", top: "#0d1620", bottom: "#12243d" },
  COMMODITY: { accent: "#facc15", glow: "#fde68a", top: "#17160e", bottom: "#2b240c" },
  FX: { accent: "#9ee247", glow: "#d9f99d", top: "#10170e", bottom: "#20300e" }
};

export function toMarket(summary: MarketSummary, previous?: Market): Market {
  const chartPoints = previous?.chartPoints.length
    ? previous.chartPoints
    : seedChartPoints(summary.points, summary.price);
  return {
    ...summary,
    points: previous?.points.length ? previous.points : chartPoints.map((point) => point.price),
    chartPoints,
    sequence: previous?.sequence ?? 0,
    theme: themes[summary.assetClass] ?? themes.CRYPTO
  };
}

export function mergeTicks(market: Market, ticks: TapeTick[], sequence: number): Market {
  if (!ticks.length) return { ...market, sequence: Math.max(market.sequence, sequence) };
  const chartPoints = compactChartPoints([...market.chartPoints, ...chartPointsFromTicks(ticks)]);
  const visible = chartPoints.map((point) => point.price);
  const price = ticks[ticks.length - 1]?.mid ?? market.price;
  const baseline = visible[Math.max(0, visible.length - 90)] ?? visible[0] ?? price;
  const move = baseline ? ((price - baseline) / baseline) * 100 : market.move;
  return { ...market, points: visible, chartPoints, price, move, sequence: Math.max(sequence, market.sequence) };
}

export function seedPoints(points: number[], price: number, target = 260): number[] {
  const clean = points.filter((point) => Number.isFinite(point) && point > 0);
  if (!clean.length) return price > 0 ? [price] : [1];
  return downsampleByExtrema(clean, Math.min(target, MAX_CHART_POINTS), (point) => point);
}

export function seedChartPoints(points: number[], price: number, target = 260): ChartPoint[] {
  const seeded = seedPoints(points, price, target);
  const now = Date.now() / 1000;
  const count = Math.max(1, seeded.length - 1);
  return seeded.map((point, index) => ({
    time: now - CHART_WINDOW_SECONDS + (index / count) * CHART_WINDOW_SECONDS,
    price: point
  }));
}

export function chartPointsFromTicks(ticks: TapeTick[]): ChartPoint[] {
  return ticks
    .filter((tick) => Number.isFinite(tick.mid) && tick.mid > 0)
    .map((tick) => ({
      time: tick.time,
      price: tick.mid,
      seq: tick.sequence,
      unchanged: tick.unchanged
    }));
}

export function compactChartPoints(points: ChartPoint[]): ChartPoint[] {
  const ordered = points
    .filter((point) => Number.isFinite(point.price) && point.price > 0 && Number.isFinite(point.time))
    .sort((a, b) => a.time - b.time || (a.seq ?? 0) - (b.seq ?? 0));
  if (!ordered.length) return [];
  const latest = ordered[ordered.length - 1].time;
  const windowStart = latest - CHART_WINDOW_SECONDS;
  const windowed = ordered.filter((point) => point.time >= windowStart);
  const source = windowed.length >= 2 ? windowed : ordered.slice(-Math.min(ordered.length, MAX_CHART_POINTS));
  return downsampleByExtrema(source, MAX_CHART_POINTS, (point) => point.price);
}

export function allowedLeverage(requested: number, maxVenueLeverage: number): number {
  const cap = Math.min(requested, maxVenueLeverage || 25);
  if (cap >= 500) return 500;
  if (cap >= 250) return 250;
  if (cap >= 100) return 100;
  if (cap >= 50) return 50;
  return 25;
}

export function directionForSide(side: Side): Direction {
  return side === "long" ? "up" : "down";
}

export function sideForDirection(direction: Direction): Side {
  return direction === "up" ? "long" : "short";
}

export function idempotencyKey(action: string, pair: string): string {
  return `${action}-${pair}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export function formatMoney(value: number): string {
  return `$${safe(value).toFixed(2)}`;
}

export function formatSignedMoney(value: number): string {
  const amount = safe(value);
  return `${amount >= 0 ? "+" : "-"}$${Math.abs(amount).toFixed(2)}`;
}

export function formatPrice(value: number): string {
  const price = safe(value);
  if (price < 1) return `$${price.toFixed(5)}`;
  if (price < 10) return `$${price.toFixed(4)}`;
  if (price < 100) return `$${price.toFixed(3)}`;
  return `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

export function formatAxisPrice(value: number, span = 0): string {
  const price = safe(value);
  if (price < 1) return price.toFixed(span > 0 && span < 0.001 ? 5 : 4);
  if (span > 0 && span < 0.01) return price.toFixed(4);
  if (span > 0 && span < 0.1) return price.toFixed(3);
  if (span > 0 && span < 1) return price.toFixed(2);
  if (price < 1000) return price.toFixed(1);
  return Math.round(price).toLocaleString(undefined, { useGrouping: false });
}

export function formatPercent(value: number, digits = 2): string {
  const amount = safe(value);
  return `${amount >= 0 ? "+" : ""}${amount.toFixed(digits)}%`;
}

export function liquidationDistance(entry: number, liquidation: number | null): string {
  if (!liquidation || !entry) return "--";
  return `${(Math.abs(entry - liquidation) / entry * 100).toFixed(2)}%`;
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function safe(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

function downsampleByExtrema<T>(items: T[], maxItems: number, valueOf: (item: T) => number): T[] {
  if (items.length <= maxItems) return items;
  if (maxItems <= 2) return [items[0], items[items.length - 1]].slice(0, maxItems);
  const result: T[] = [items[0]];
  const body = items.slice(1, -1);
  const bucketCount = Math.max(1, Math.floor((maxItems - 2) / 2));
  for (let bucket = 0; bucket < bucketCount && result.length < maxItems - 1; bucket += 1) {
    const start = Math.floor((bucket / bucketCount) * body.length);
    const end = Math.floor(((bucket + 1) / bucketCount) * body.length);
    const slice = body.slice(start, Math.max(start + 1, end));
    let minIndex = 0;
    let maxIndex = 0;
    for (let index = 1; index < slice.length; index += 1) {
      if (valueOf(slice[index]) < valueOf(slice[minIndex])) minIndex = index;
      if (valueOf(slice[index]) > valueOf(slice[maxIndex])) maxIndex = index;
    }
    if (minIndex === maxIndex) {
      if (result.length < maxItems - 1) result.push(slice[minIndex]);
    } else if (minIndex < maxIndex) {
      if (result.length < maxItems - 1) result.push(slice[minIndex]);
      if (result.length < maxItems - 1) result.push(slice[maxIndex]);
    } else {
      if (result.length < maxItems - 1) result.push(slice[maxIndex]);
      if (result.length < maxItems - 1) result.push(slice[minIndex]);
    }
  }
  result.push(items[items.length - 1]);
  return result;
}
