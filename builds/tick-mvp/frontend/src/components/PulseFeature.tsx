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
};

export function PulseFeature({ market, pulse, onOpen }: Props) {
  const theme = themeFor(market.market);
  const sparkline = sparklineGeometry(market.observations, market.price);
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
          <path className="pulse-feature-area" d={sparkline.area} />
          <path className="pulse-feature-line" d={sparkline.line} />
        </svg>
        <span>90S LIVE TAPE</span>
      </div>

      <div className="pulse-feature-footer">
        <TapeHeat pulse={pulse} accent={theme.accent} />
        <span className="pulse-feature-open">
          Open tape
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
      area: `M 0 ${y} L 320 ${y} L 320 116 L 0 116 Z`
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
  const line = coordinates
    .map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ");
  const first = coordinates[0];
  const last = coordinates.at(-1) ?? first;

  return {
    line,
    area: `${line} L ${last[0].toFixed(2)} 116 L ${first[0].toFixed(2)} 116 Z`
  };
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
