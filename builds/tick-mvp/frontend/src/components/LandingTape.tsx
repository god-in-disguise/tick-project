import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import { api } from "../api";
import { buildMicroBars, describeMarket } from "../marketActivity";
import type { Market, MarketObservation } from "../types";
import { themeFor } from "../theme";
import { MarketCanvas } from "./MarketCanvas";
import { TapeHeat } from "./TapeHeat";

const WINDOW_SECONDS = 90;

export function LandingTape() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.markets({ includeTape: true, limit: 10 })
      .then((next) => {
        if (!active || next.length === 0) return;
        const distinct = next.filter(
          (market, index) => next.findIndex((candidate) => candidate.symbol === market.symbol) === index
        ).slice(0, 3);
        setMarkets(distinct);
        setSelected((current) => current ?? distinct[0]?.market ?? null);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let active = true;
    const retained = markets.find((market) => market.market === selected);
    let sequence = retained?.sequence ?? 0;

    const bootstrap = async () => {
      try {
        const chart = await api.chart(selected);
        if (!active) return;
        sequence = chart.sequence;
        updateMarketTape(selected, chart.observations, chart.sequence, setMarkets);
      } catch {
        // The landing remains usable when the public tape is temporarily unavailable.
      }
    };

    const update = async () => {
      try {
        const tape = await api.tape(selected, sequence);
        if (!active) return;
        if (tape.resyncRequired) {
          await bootstrap();
          return;
        }
        sequence = tape.sequence;
        if (tape.observations.length === 0) return;
        setMarkets((current) => current.map((market) => (
          market.market === selected
            ? {
                ...market,
                price: tape.observations.at(-1)?.price ?? market.price,
                observations: trimObservations([...market.observations, ...tape.observations]),
                sequence: tape.sequence
              }
            : market
        )));
      } catch {
        // The next interval retries without replacing the last truthful frame.
      }
    };

    // The retained snapshot is painted immediately; this refresh runs behind it.
    void bootstrap();
    const interval = window.setInterval(() => void update(), 700);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [selected]);

  const activeMarket = markets.find((market) => market.market === selected) ?? markets[0] ?? null;
  const activeTheme = activeMarket ? themeFor(activeMarket.market) : null;
  const pulse = activeMarket
    ? describeMarket(
        activeMarket,
        buildMicroBars(activeMarket.observations, Date.now() / 1_000, 2, WINDOW_SECONDS)
      )
    : null;
  const style = activeTheme
    ? {
        "--landing-accent": activeTheme.accent,
        "--landing-glow": activeTheme.glow,
        "--landing-top": activeTheme.top,
        "--landing-bottom": activeTheme.bottom
      } as CSSProperties
    : undefined;

  return (
    <section className="landing-live-stage" style={style} aria-label="Live market preview">
      <div className="landing-live-meta">
        <span><i /> LIVE TAPE</span>
        <strong className={storyClass(pulse?.story)}>{pulse?.story ?? "CONNECTING"}</strong>
      </div>

      <div className="landing-live-identity">
        {activeMarket ? (
          <>
            <span>
              <strong>{activeMarket.symbol}</strong>
              <small>{activeMarket.name}</small>
            </span>
            <span>
              <strong>{formatPrice(activeMarket.price)}</strong>
              <small className={activeMarket.movePct >= 0 ? "positive" : "negative"}>
                {activeMarket.movePct >= 0 ? "+" : ""}{activeMarket.movePct.toFixed(2)}%
              </small>
            </span>
          </>
        ) : (
          <strong>CONNECTING TO LIVE MARKETS</strong>
        )}
      </div>

      <div className="landing-chart-frame">
        {markets.map((market) => (
          <MarketCanvas
            key={market.market}
            market={market}
            theme={themeFor(market.market)}
            entry={null}
            breakEven={null}
            stopLoss={null}
            takeProfit={null}
            liquidation={null}
            side={null}
            compact
            active={market.market === selected}
          />
        ))}
      </div>

      {pulse && activeTheme ? (
        <div className="landing-live-heat">
          <TapeHeat pulse={pulse} accent={activeTheme.accent} />
        </div>
      ) : null}

      <div className="landing-market-tabs" aria-label="Preview market">
        {markets.map((market) => (
          <button
            key={market.market}
            className={market.market === selected ? "active" : ""}
            style={{ "--tab-accent": themeFor(market.market).accent } as CSSProperties}
            type="button"
            onClick={() => setSelected(market.market)}
          >
            <strong><i />{market.symbol}</strong>
            <span className={market.movePct >= 0 ? "positive" : "negative"}>
              {market.movePct >= 0 ? "+" : ""}{market.movePct.toFixed(2)}%
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function storyClass(story: string | undefined): string {
  if (story?.includes("LOW")) return "is-low";
  if (story?.includes("HIGH")) return "is-high";
  return "";
}

function updateMarketTape(
  marketId: string,
  observations: MarketObservation[],
  sequence: number,
  setMarkets: React.Dispatch<React.SetStateAction<Market[]>>
) {
  setMarkets((current) => current.map((market) => (
    market.market === marketId
      ? {
          ...market,
          price: observations.at(-1)?.price ?? market.price,
          observations: trimObservations(observations),
          sequence
        }
      : market
  )));
}

function trimObservations(observations: MarketObservation[]): MarketObservation[] {
  if (observations.length === 0) return observations;
  const end = observations[observations.length - 1].receivedTs;
  const start = end - WINDOW_SECONDS;
  return observations.filter((observation) => observation.receivedTs >= start).slice(-360);
}

function formatPrice(value: number): string {
  if (value >= 1000) return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (value >= 10) return value.toFixed(2);
  return value.toFixed(4);
}
