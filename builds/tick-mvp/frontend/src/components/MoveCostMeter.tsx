import type { CSSProperties } from "react";

import { percent } from "../format";

type Props = {
  movePct: number;
  costPct: number;
  accent: string;
  compact?: boolean;
  moveLabel?: string;
};

export function MoveCostMeter({
  movePct,
  costPct,
  accent,
  compact = false,
  moveLabel = "RECENT MOVE"
}: Props) {
  const move = Math.max(0, movePct);
  const cost = Math.max(0, costPct);
  const coverage = cost > 0 ? move / cost : null;
  const style = {
    "--meter-accent": accent,
    "--move-width": `${coverage === null ? 0 : Math.min(100, coverage / 2 * 100)}%`,
    "--cost-left": "50%"
  } as CSSProperties;

  return (
    <div className={`move-cost-meter ${compact ? "compact" : ""}`} style={style}>
      {!compact ? (
        <div className="move-cost-status">
          {coverage === null
            ? "CALCULATING COST"
            : `${moveLabel} IS ${coverage.toFixed(1)}× EST. COST`}
        </div>
      ) : null}
      <div
        className="move-cost-track"
        aria-label={`Recent move ${percent(movePct, 3)}, estimated cost to cover ${percent(costPct, 3)}`}
      >
        <i />
        <b />
      </div>
      {!compact ? (
        <div className="move-cost-scale" aria-hidden="true">
          <span>0</span>
          <span>COST</span>
          <span>2×</span>
        </div>
      ) : null}
      <div className="move-cost-values">
        <span>{moveLabel} <strong>{percent(movePct, 3)}</strong></span>
        <span>EST. COST <strong>{percent(costPct, 3)}</strong></span>
      </div>
    </div>
  );
}
