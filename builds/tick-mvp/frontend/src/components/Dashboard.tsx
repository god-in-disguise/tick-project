import { ChartNoAxesCombined } from "lucide-react";

import { percent, price } from "../format";
import { themeFor } from "../theme";
import type { Market } from "../types";

type Props = {
  markets: Market[];
  onMarket: (market: string) => void;
};

export function Dashboard({ markets, onMarket }: Props) {
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
          {markets.filter(
            (market) => market.openingAllowed && market.activitySurplusPct >= 0
          ).length} cost-covered
        </strong>
      </div>
      <section className="hot-market-list">
        {markets.map((market, index) => {
          const theme = themeFor(market.market);
          const covered = market.activitySurplusPct >= 0 && market.openingAllowed;
          return (
            <button key={market.market} className="market-row" onClick={() => onMarket(market.market)}>
              <span className="market-rank">{String(index + 1).padStart(2, "0")}</span>
              <span className="market-identity">
                <span className="market-identity-title">
                  <i style={{ backgroundColor: theme.accent }} />
                  <strong>{market.symbol}</strong>
                </span>
                <small className={covered ? "covered" : ""}>
                  {covered
                    ? `SURPLUS ${percent(market.activitySurplusPct, 3)}`
                    : `WAIT · ${percent(market.activitySurplusPct, 3)}`}
                </small>
              </span>
              <span className={`activity-track ${covered ? "covered" : ""}`}>
                <i
                  style={{
                    width: `${Math.max(8, Math.min(100, market.score / 2))}%`
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
