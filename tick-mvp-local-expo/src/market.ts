import { MAX_CHART_POINTS } from "./config";
import type { AssetClass, Direction, Market, MarketSummary, Side, TapeTick, Theme } from "./types";

const themes: Record<AssetClass, Theme> = {
  CRYPTO: { accent: "#ff9f2e", glow: "#ffc166", top: "#0e1817", bottom: "#231e10" },
  STOCK: { accent: "#54ddca", glow: "#8bf3e5", top: "#0b1719", bottom: "#0b2b2e" },
  INDEX: { accent: "#60a5fa", glow: "#93c5fd", top: "#0d1620", bottom: "#12243d" },
  COMMODITY: { accent: "#facc15", glow: "#fde68a", top: "#17160e", bottom: "#2b240c" },
  FX: { accent: "#9ee247", glow: "#d9f99d", top: "#10170e", bottom: "#20300e" }
};

export function toMarket(summary: MarketSummary, previous?: Market): Market {
  return {
    ...summary,
    points: previous?.points.length ? previous.points : seedPoints(summary.points, summary.price),
    sequence: previous?.sequence ?? 0,
    theme: themes[summary.assetClass] ?? themes.CRYPTO
  };
}

export function mergeTicks(market: Market, ticks: TapeTick[], sequence: number): Market {
  if (!ticks.length) return { ...market, sequence: Math.max(market.sequence, sequence) };
  const points = [...market.points];
  for (const tick of ticks) appendVisualTick(points, tick.mid);
  const visible = points.slice(-MAX_CHART_POINTS);
  const price = ticks[ticks.length - 1]?.mid ?? market.price;
  const baseline = visible[Math.max(0, visible.length - 90)] ?? visible[0] ?? price;
  const move = baseline ? ((price - baseline) / baseline) * 100 : market.move;
  return { ...market, points: visible, price, move, sequence: Math.max(sequence, market.sequence) };
}

export function seedPoints(points: number[], price: number, target = 260): number[] {
  const clean = points.filter((point) => Number.isFinite(point) && point > 0);
  if (!clean.length) return price > 0 ? [price] : [1];
  if (clean.length < 8) return clean;
  if (clean.length <= target) return resampleValues(clean, clamp(clean.length * 6, clean.length, Math.min(target, MAX_CHART_POINTS)));
  const outputLength = Math.min(target, MAX_CHART_POINTS);
  return Array.from({ length: outputLength }, (_, index) => {
    const source = (index / Math.max(1, outputLength - 1)) * (clean.length - 1);
    const low = Math.floor(source);
    const high = Math.min(clean.length - 1, low + 1);
    const progress = source - low;
    return clean[low] * (1 - progress) + clean[high] * progress;
  });
}

function appendVisualTick(points: number[], price: number) {
  if (!Number.isFinite(price) || price <= 0) return;
  const last = points[points.length - 1];
  if (!last) {
    points.push(price);
    return;
  }
  const minimumMove = Math.max(Math.abs(price) * 0.00000001, 0.00000001);
  if (Math.abs(price - last) <= minimumMove) {
    points.push(price);
    return;
  }

  const stepSize = Math.max(Math.abs(last) * 0.000015, 0.00001);
  const steps = clamp(Math.ceil(Math.abs(price - last) / stepSize), 1, 4);
  for (let index = 1; index <= steps; index += 1) {
    const progress = index / steps;
    points.push(last * (1 - progress) + price * progress);
  }
}

function resampleValues(values: number[], outputLength: number): number[] {
  if (values.length >= outputLength) return values.slice(-outputLength);
  return Array.from({ length: outputLength }, (_, index) => {
    const source = (index / Math.max(1, outputLength - 1)) * (values.length - 1);
    const low = Math.floor(source);
    const high = Math.min(values.length - 1, low + 1);
    const progress = source - low;
    return values[low] * (1 - progress) + values[high] * progress;
  });
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
