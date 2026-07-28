import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Market, MarketObservation } from "../types";
import { themeFor } from "../theme";
import { MarketCanvas } from "./MarketCanvas";

const WINDOW_SECONDS = 90;

export function LandingTape() {
  const sequenceRef = useRef(0);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [observations, setObservations] = useState<MarketObservation[]>([]);

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

    const bootstrap = async () => {
      try {
        const chart = await api.chart(selected);
        if (!active) return;
        sequenceRef.current = chart.sequence;
        setObservations(chart.observations);
      } catch {
        // The landing remains usable when the public tape is temporarily unavailable.
      }
    };

    const update = async () => {
      try {
        const tape = await api.tape(selected, sequenceRef.current);
        if (!active) return;
        if (tape.resyncRequired) {
          await bootstrap();
          return;
        }
        sequenceRef.current = tape.sequence;
        if (tape.observations.length === 0) return;
        setObservations((current) => trimObservations([...current, ...tape.observations]));
      } catch {
        // The next interval retries without replacing the last truthful frame.
      }
    };

    setObservations(retained?.observations ?? []);
    sequenceRef.current = retained?.sequence ?? 0;
    if (!retained?.observations.length) void bootstrap();
    const interval = window.setInterval(() => void update(), 700);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [selected, markets]);

  const activeMarket = markets.find((market) => market.market === selected) ?? markets[0] ?? null;
  const previewMarket = activeMarket
    ? {
        ...activeMarket,
        price: observations.at(-1)?.price ?? activeMarket.price,
        observations,
        sequence: sequenceRef.current
      }
    : null;

  return (
    <section className="landing-live-stage" aria-label="Live market preview">
      <div className="landing-live-meta">
        <span><i /> LIVE TAPE</span>
        {activeMarket ? (
          <strong>
            {activeMarket.symbol}
            <b>{formatPrice(activeMarket.price)}</b>
          </strong>
        ) : (
          <strong>CONNECTING</strong>
        )}
      </div>
      {previewMarket ? (
        <MarketCanvas
          market={previewMarket}
          theme={themeFor(previewMarket.market)}
          entry={null}
          breakEven={null}
          stopLoss={null}
          takeProfit={null}
          liquidation={null}
          side={null}
          compact
        />
      ) : null}
      <div className="landing-market-tabs" aria-label="Preview market">
        {markets.map((market) => (
          <button
            key={market.market}
            className={market.market === selected ? "active" : ""}
            type="button"
            onClick={() => setSelected(market.market)}
          >
            <strong>{market.symbol}</strong>
            <span className={market.movePct >= 0 ? "positive" : "negative"}>
              {market.movePct >= 0 ? "+" : ""}{market.movePct.toFixed(2)}%
            </span>
          </button>
        ))}
      </div>
    </section>
  );
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
