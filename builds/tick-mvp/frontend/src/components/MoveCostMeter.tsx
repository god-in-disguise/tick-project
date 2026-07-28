import type { CSSProperties } from "react";

import { percent } from "../format";

type Props = {
  movePct: number;
  costPct: number;
  accent: string;
  compact?: boolean;
};

export function MoveCostMeter({ movePct, costPct, accent, compact = false }: Props) {
  const move = Math.max(0, movePct);
  const cost = Math.max(0, costPct);
  const scale = Math.max(move, cost, 0.0001) * 1.12;
  const style = {
    "--meter-accent": accent,
    "--move-width": `${Math.min(100, move / scale * 100)}%`,
    "--cost-left": `${Math.min(96, cost / scale * 100)}%`
  } as CSSProperties;

  return (
    <div className={`move-cost-meter ${compact ? "compact" : ""}`} style={style}>
      <div className="move-cost-values">
        <span>MOVE <strong>{percent(movePct, 3)}</strong></span>
        <span>COST <strong>{percent(costPct, 3)}</strong></span>
      </div>
      <div
        className="move-cost-track"
        aria-label={`Move ${percent(movePct, 3)}, estimated cost ${percent(costPct, 3)}`}
      >
        <i />
        <b />
      </div>
    </div>
  );
}
