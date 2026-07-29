import { ArrowUpRight } from "lucide-react";
import type { CSSProperties } from "react";

import { percent, price } from "../format";
import type { MarketPulse } from "../marketActivity";
import { themeFor } from "../theme";
import type { Market, MarketObservation } from "../types";
import { TapeHeat } from "./TapeHeat";

type Props = {
  market: Market;
  pulse: MarketPulse;
  onOpen: () => void;
};

type Sparkline = {
  line: string;
  area: string;
  lastX: number;
  lastY: number;
};

export function PulseFeature({ market, pulse, onOpen }: Props) {
  const theme = themeFor(market.market);
  const sparkline = sparklineGeometry(market.observations, market.price);
  const gradientId = `pulse-area-${market.market.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const active = pulse.heat !== "QUIET" && market.openingAllowed;
  const style = {
    "--feature-accent": theme.accent,
    "--feature-glow": theme.glow
  } as CSSProperties;

  return (
    <button
      className="pulse-feature"
      style={style}
      type="button"
      onClick={onOpen}
      aria-label={`Open ${market.symbol} tape`}
    >
      <div className="pulse-feature-topline">
        <span className={active ? "is-active" : ""}>{pulse.story}</span>
        <strong>{pulse.heat}</strong>
      </div>

      <div className="pulse-feature-heading">
        <span>
          <strong>{market.symbol}</strong>
          <small>{market.name}</small>
        </span>
        <span className="pulse-feature-price">
          <strong>{price(market.price, true)}</strong>
          <small className={market.movePct >= 0 ? "positive" : "negative"}>
            {percent(market.movePct)}
          </small>
        </span>
      </div>

      <div className="pulse-feature-chart" aria-hidden="true">
        <svg viewBox="0 0 320 116" preserveAspectRatio="none">
          <defs>
            <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="var(--feature-accent)" stopOpacity="0.12" />
              <stop offset="72%" stopColor="var(--feature-accent)" stopOpacity="0.025" />
              <stop offset="100%" stopColor="var(--feature-accent)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <g className="pulse-feature-grid">
            <line x1="0" x2="320" y1="24" y2="24" />
            <line x1="0" x2="320" y1="58" y2="58" />
            <line x1="0" x2="320" y1="92" y2="92" />
            <line x1="80" x2="80" y1="8" y2="108" />
            <line x1="160" x2="160" y1="8" y2="108" />
            <line x1="240" x2="240" y1="8" y2="108" />
          </g>
          <path
            className="pulse-feature-area"
            d={sparkline.area}
            fill={`url(#${gradientId})`}
          />
          <path className="pulse-feature-glow" d={sparkline.line} />
          <path className="pulse-feature-line" d={sparkline.line} />
          <circle
            className="pulse-feature-edge-glow"
            cx={sparkline.lastX}
            cy={sparkline.lastY}
            r="6"
          />
          <circle
            className="pulse-feature-edge"
            cx={sparkline.lastX}
            cy={sparkline.lastY}
            r="2.7"
          />
        </svg>
        <span>90S LIVE TAPE</span>
      </div>

      <div className="pulse-feature-footer">
        <TapeHeat pulse={pulse} accent={theme.accent} />
        <span className="pulse-feature-open">
          Trade this tape
          <ArrowUpRight size={15} />
        </span>
      </div>
    </button>
  );
}

function sparklineGeometry(observations: MarketObservation[], fallbackPrice: number): Sparkline {
  const sorted = observations
    .filter((observation) => Number.isFinite(observation.price) && observation.price > 0)
    .sort((left, right) => left.receivedTs - right.receivedTs);
  const latestTs = sorted.at(-1)?.receivedTs ?? Date.now() / 1_000;
  const visible = sorted.filter((observation) => observation.receivedTs >= latestTs - 90);
  const source = visible.length >= 2 ? visible : sorted.slice(-2);
  const points = sampleObservations(source, 90);

  if (points.length < 2) {
    const y = 58;
    return {
      line: `M 0 ${y} L 320 ${y}`,
      area: `M 0 ${y} L 320 ${y} L 320 116 L 0 116 Z`,
      lastX: 320,
      lastY: y
    };
  }

  const low = Math.min(...points.map((point) => point.price), fallbackPrice);
  const high = Math.max(...points.map((point) => point.price), fallbackPrice);
  const rawSpan = high - low;
  const span = Math.max(rawSpan, Math.abs(fallbackPrice) * 0.00005, Number.EPSILON);
  const startTs = points[0].receivedTs;
  const endTs = points.at(-1)?.receivedTs ?? startTs + 1;
  const duration = Math.max(endTs - startTs, 1);
  const coordinates = points.map((point) => {
    const x = (point.receivedTs - startTs) / duration * 320;
    const y = 103 - (point.price - low) / span * 88;
    return [x, y] as const;
  });
  const line = monotonePath(coordinates);
  const first = coordinates[0];
  const last = coordinates.at(-1) ?? first;

  return {
    line,
    area: `${line} L ${last[0].toFixed(2)} 116 L ${first[0].toFixed(2)} 116 Z`,
    lastX: last[0],
    lastY: last[1]
  };
}

function monotonePath(raw: ReadonlyArray<readonly [number, number]>): string {
  const points = raw.filter(
    (point, index) => index === 0 || point[0] > raw[index - 1][0] + 0.01
  );
  if (!points.length) return "";
  let path = `M ${points[0][0].toFixed(2)} ${points[0][1].toFixed(2)}`;
  if (points.length === 1) return path;
  if (points.length === 2) {
    return `${path} L ${points[1][0].toFixed(2)} ${points[1][1].toFixed(2)}`;
  }

  const delta = points.slice(1).map((point, index) => {
    const dx = point[0] - points[index][0];
    return dx > 0 ? (point[1] - points[index][1]) / dx : 0;
  });
  const slopes = [delta[0]];
  for (let index = 1; index < points.length - 1; index += 1) {
    slopes[index] = delta[index - 1] * delta[index] <= 0
      ? 0
      : (delta[index - 1] + delta[index]) / 2;
  }
  slopes[points.length - 1] = delta.at(-1) ?? 0;

  for (let index = 0; index < delta.length; index += 1) {
    if (Math.abs(delta[index]) < 1e-9) {
      slopes[index] = 0;
      slopes[index + 1] = 0;
      continue;
    }
    const left = slopes[index] / delta[index];
    const right = slopes[index + 1] / delta[index];
    const magnitude = Math.hypot(left, right);
    if (magnitude > 3) {
      const scale = 3 / magnitude;
      slopes[index] = scale * left * delta[index];
      slopes[index + 1] = scale * right * delta[index];
    }
  }

  for (let index = 0; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    const dx = next[0] - current[0];
    path += ` C ${(current[0] + dx / 3).toFixed(2)} ${(current[1] + slopes[index] * dx / 3).toFixed(2)}`;
    path += ` ${(next[0] - dx / 3).toFixed(2)} ${(next[1] - slopes[index + 1] * dx / 3).toFixed(2)}`;
    path += ` ${next[0].toFixed(2)} ${next[1].toFixed(2)}`;
  }
  return path;
}

function sampleObservations(
  observations: MarketObservation[],
  maxPoints: number
): MarketObservation[] {
  if (observations.length <= maxPoints) return observations;
  const stride = (observations.length - 1) / (maxPoints - 1);
  return Array.from(
    { length: maxPoints },
    (_, index) => observations[Math.round(index * stride)]
  );
}
