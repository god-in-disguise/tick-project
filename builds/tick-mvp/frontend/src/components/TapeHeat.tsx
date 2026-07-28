import type { CSSProperties } from "react";

import { percent } from "../format";
import type { MarketPulse } from "../marketActivity";

type Props = {
  pulse: MarketPulse;
  accent: string;
  compact?: boolean;
};

export function TapeHeat({ pulse, accent, compact = false }: Props) {
  const style = { "--heat-accent": accent } as CSSProperties;

  return (
    <div className={`tape-heat ${compact ? "compact" : ""}`} style={style}>
      <div className="tape-heat-heading">
        <span>TAPE HEAT</span>
        <strong>{pulse.heat}</strong>
      </div>
      <div
        className="tape-heat-samples"
        role="img"
        aria-label={`${pulse.heat} tape, 10 second range ${percent(pulse.recentRangePct, 3)}, pace ${tempoLabel(pulse.tempoRatio)} versus the preceding 30 seconds`}
      >
        {pulse.heatSamples.map((sample, index) => (
          <i
            key={index}
            style={{ "--sample-height": `${Math.round(sample * 100)}%` } as CSSProperties}
          />
        ))}
      </div>
      <div className="tape-heat-values">
        <span>10s RANGE <strong>{percent(pulse.recentRangePct, 3)}</strong></span>
        <span>VS 30s <strong>{tempoLabel(pulse.tempoRatio)}</strong></span>
      </div>
    </div>
  );
}

function tempoLabel(ratio: number): string {
  if (!Number.isFinite(ratio) || ratio <= 0) return "STILL";
  return `${ratio < 1.1 ? ratio.toFixed(2) : ratio.toFixed(1)}x`;
}
