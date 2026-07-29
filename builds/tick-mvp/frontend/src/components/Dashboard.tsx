import { ChartNoAxesCombined } from "lucide-react";

import { percent, price } from "../format";
import { buildMicroBars, describeMarket } from "../marketActivity";
import { themeFor } from "../theme";
import type { Market } from "../types";
import { PulseFeature } from "./PulseFeature";
import { TapeHeat } from "./TapeHeat";

type Props = {
  markets: Market[];
  onMarket: (market: string) => void;
};

export function Dashboard({ markets, onMarket }: Props) {
  const now = Date.now() / 1_000;
  const rows = markets.map((market) => ({
    market,
    pulse: describeMarket(market, buildMicroBars(market.observations, now), now)
  }));
  const featured = rows[0];
  const remaining = rows.slice(1);

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <span>VOLATILITY SCANNER</span>
          <h1>Pulse</h1>
        </div>
        <ChartNoAxesCombined size={22} />
      </header>
      <div className="scanner-meta">
        <span>Markets moving now</span>
        <strong>
          {rows.filter(
            ({ market, pulse }) => market.openingAllowed && pulse.heat !== "QUIET"
          ).length} active tapes
        </strong>
      </div>
      {featured ? (
        <PulseFeature
          market={featured.market}
          pulse={featured.pulse}
          onOpen={() => onMarket(featured.market.market)}
        />
      ) : null}
      {remaining.length ? (
        <div className="pulse-list-heading">
          <span>ALSO MOVING</span>
          <strong>LIVE RANKING</strong>
        </div>
      ) : null}
      <section className="hot-market-list">
        {remaining.map(({ market, pulse }, index) => {
          const theme = themeFor(market.market);
          const active = pulse.heat !== "QUIET" && market.openingAllowed;
          return (
            <button
              key={market.market}
              className={`market-row ${index === 0 && active ? "top-opportunity" : ""}`}
              onClick={() => onMarket(market.market)}
            >
              <span className="market-rank">{String(index + 2).padStart(2, "0")}</span>
              <span className="market-identity">
                <span className="market-identity-title">
                  <i style={{ backgroundColor: theme.accent }} />
                  <strong>{market.symbol}</strong>
                </span>
                <small className={active ? "covered" : ""}>
                  {pulse.heat} · 10s {percent(pulse.recentRangePct, 3)}
                </small>
              </span>
              <TapeHeat
                pulse={pulse}
                accent={theme.accent}
                compact
              />
              <span className="market-row-price">
                <strong>{price(market.price, true)}</strong>
                <small className={market.movePct >= 0 ? "positive" : "negative"}>
                  {percent(market.movePct)}
                </small>
              </span>
            </button>
          );
        })}
      </section>
    </main>
  );
}
