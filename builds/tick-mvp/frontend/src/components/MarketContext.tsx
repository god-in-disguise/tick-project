import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

import { buildMicroBars, describeMarket } from "../marketActivity";
import type { Market, Position, Quote, Theme } from "../types";
import { MoveCostMeter } from "./MoveCostMeter";

type Props = {
  market: Market;
  position: Position | null;
  quote: Quote | null;
  estimatedNetPnl: number | null;
  theme: Theme;
};

export function MarketContext({ market, position, quote, estimatedNetPnl, theme }: Props) {
  const bars = useMemo(
    () => buildMicroBars(market.observations, Date.now() / 1_000),
    [market.observations]
  );
  const pulse = describeMarket(market, bars);
  const story = useStableStory(market.market, pulse.story);

  if (position) {
    return (
      <PositionContext
        position={position}
        quote={quote}
        estimatedNetPnl={estimatedNetPnl}
        accent={theme.accent}
      />
    );
  }

  return (
    <div className="market-context">
      <div className="market-story">
        <strong key={story}>{story}</strong>
        <span>PACE {pulse.pace}</span>
      </div>
      <MoveCostMeter
        movePct={market.activeTapePct}
        costPct={market.feeHurdlePct}
        accent={theme.accent}
      />
    </div>
  );
}

function PositionContext({
  position,
  quote,
  estimatedNetPnl,
  accent
}: {
  position: Position;
  quote: Quote | null;
  estimatedNetPnl: number | null;
  accent: string;
}) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  const cost = quote?.estimatedRoundTripCostUsd ?? 0;
  const hasCostModel = cost > 0;
  const grossMovement = estimatedNetPnl === null ? null : estimatedNetPnl + cost;
  const recovery = cost > 0 && grossMovement !== null
    ? Math.max(0, Math.min(100, grossMovement / cost * 100))
    : 0;
  const covered = hasCostModel && estimatedNetPnl !== null && estimatedNetPnl >= 0;
  const openedAt = Date.parse(position.openedAt ?? position.updatedAt);
  const secondsOpen = Number.isFinite(openedAt)
    ? Math.max(0, Math.floor((now - openedAt) / 1_000))
    : 0;
  const style = {
    "--meter-accent": accent,
    "--recovery-width": `${covered ? 100 : recovery}%`
  } as CSSProperties;

  return (
    <div className="market-context position-context" style={style}>
      <div className="market-story">
        <strong>{hasCostModel ? covered ? "COST COVERED" : "RECOVERING COST" : "POSITION LIVE"}</strong>
        <span>{secondsOpen}s IN TRADE</span>
      </div>
      {hasCostModel ? (
        <div className="cost-recovery-track">
          <i />
        </div>
      ) : null}
    </div>
  );
}

function useStableStory(market: string, nextStory: string): string {
  const [story, setStory] = useState(nextStory);
  useEffect(() => {
    setStory(nextStory);
  }, [market]);
  useEffect(() => {
    if (nextStory === story) return;
    const urgent = nextStory.includes("STALE")
      || nextStory.includes("DELAYED")
      || nextStory.includes("PAUSED");
    if (urgent) {
      setStory(nextStory);
      return;
    }
    const timer = window.setTimeout(() => setStory(nextStory), 1_200);
    return () => window.clearTimeout(timer);
  }, [nextStory, story]);
  return story;
}
