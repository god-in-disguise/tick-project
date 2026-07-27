import { Radar } from "lucide-react";

import { percent, price } from "../format";
import { themeFor } from "../theme";
import type { Market } from "../types";

type Props = {
  markets: Market[];
  onMarket: (market: string) => void;
};

export function Dashboard({ markets, onMarket }: Props) {
  const tickerCounts = markets.reduce<Record<string, number>>((counts, market) => {
    counts[market.symbol] = (counts[market.symbol] ?? 0) + 1;
    return counts;
  }, {});

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <span>VOLATILITY SCANNER</span>
          <h1>Pulse</h1>
        </div>
        <Radar size={22} />
      </header>
      <div className="scanner-meta">
        <span>Markets moving now</span>
        <strong>{markets.filter((market) => market.openingAllowed).length} live</strong>
      </div>
      <section className="hot-market-list">
        {markets.map((market, index) => {
          const theme = themeFor(market.market);
          const ticker = tickerCounts[market.symbol] > 1
            ? market.market.replace(/-USD$/, "").replace(/-/g, " ")
            : market.symbol;
          return (
            <button key={market.market} className="market-row" onClick={() => onMarket(market.market)}>
              <span className="market-rank">{String(index + 1).padStart(2, "0")}</span>
              <span className="market-identity">
                <strong>{ticker}</strong>
                <small>{market.name} · {market.maxLeverage}x</small>
              </span>
              <span className="activity-track">
                <i
                  style={{
                    width: `${Math.max(8, Math.min(100, market.score / 2))}%`,
                    backgroundColor: theme.accent
                  }}
                />
              </span>
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
