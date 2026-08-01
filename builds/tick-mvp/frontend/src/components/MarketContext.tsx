import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

import { buildMicroBars, describeMarket } from "../marketActivity";
import { liquidationThresholdCrossed } from "../positionPnl";
import type { Market, Position, Quote, Theme } from "../types";
import { TapeHeat } from "./TapeHeat";

type Props = {
  market: Market;
  position: Position | null;
  quote: Quote | null;
  estimatedNetPnl: number | null;
  theme: Theme;
  active?: boolean;
};

export function MarketContext({
  market,
  position,
  quote,
  estimatedNetPnl,
  theme,
  active = true
}: Props) {
  const [now, setNow] = useState(Date.now() / 1_000);
  useLayoutEffect(() => {
    if (!active) return;
    setNow(Date.now() / 1_000);
    const timer = window.setInterval(() => setNow(Date.now() / 1_000), 1_000);
    return () => window.clearInterval(timer);
  }, [active]);
  const bars = useMemo(
    () => buildMicroBars(market.observations, now),
    [market.observations, now]
  );
  const pulse = describeMarket(market, bars, now);
  const story = useStableStory(market.market, pulse.story);
  const storyTone = story.includes("90s LOW")
    ? "market-story-low"
    : story.includes("90s HIGH")
      ? "market-story-high"
      : "";

  if (position) {
    return (
      <PositionContext
        position={position}
        quote={quote}
        estimatedNetPnl={estimatedNetPnl}
        liquidationCrossed={liquidationThresholdCrossed(position, market.price)}
        accent={theme.accent}
      />
    );
  }

  return (
    <div className="market-context">
      <div className={`market-story ${storyTone}`}>
        <strong key={story}>{story}</strong>
      </div>
      <TapeHeat
        pulse={pulse}
        accent={theme.accent}
      />
    </div>
  );
}

function PositionContext({
  position,
  quote,
  estimatedNetPnl,
  liquidationCrossed,
  accent
}: {
  position: Position;
  quote: Quote | null;
  estimatedNetPnl: number | null;
  liquidationCrossed: boolean;
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
        <strong>
          {liquidationCrossed
            ? "LIQUIDATION THRESHOLD"
            : hasCostModel
              ? covered ? "COST COVERED" : "RECOVERING COST"
              : "POSITION LIVE"}
        </strong>
        <span>
          {liquidationCrossed
            ? "AWAITING VENUE"
            : `${hasCostModel && !covered ? `${Math.round(recovery)}% · ` : ""}${secondsOpen}s IN TRADE`}
        </span>
      </div>
      {hasCostModel && !liquidationCrossed ? (
        <div className="cost-recovery-track">
          <i />
        </div>
      ) : null}
    </div>
  );
}

function useStableStory(market: string, nextStory: string): string {
  const [story, setStory] = useState(nextStory);
  useLayoutEffect(() => {
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
