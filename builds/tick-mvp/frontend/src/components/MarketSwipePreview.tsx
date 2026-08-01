import type { CSSProperties } from "react";

import { money, percent, price } from "../format";
import { themeFor } from "../theme";
import { effectiveTicketUsd } from "../tradeSettings";
import type { Market, TradeSettings } from "../types";
import { MarketCanvas } from "./MarketCanvas";
import { MarketContext } from "./MarketContext";

type Props = {
  market: Market;
  offset: -1 | 1;
  active: boolean;
  settings: TradeSettings;
};

export function MarketSwipePreview({
  market,
  offset,
  active,
  settings
}: Props) {
  const theme = themeFor(market.market);
  const amount = effectiveTicketUsd(settings, market);
  const style = {
    "--preview-origin": `${offset * 100}vw`
  } as CSSProperties;

  return (
    <div
      className={`market-swipe-preview ${active ? "is-active" : ""}`}
      style={style}
      aria-hidden="true"
    >
      <header className="trade-header market-page-header">
        <div className="market-heading">
          <div className="market-name">
            <div className="market-name-row">
              <strong>{market.symbol}</strong>
              <b className="leverage-chip">{settings.leverage}x</b>
            </div>
            <span className="market-full-name">{market.name}</span>
            <div className="market-price-row">
              <b>{price(market.price)}</b>
              <span className={market.movePct >= 0 ? "positive" : "negative"}>
                {percent(market.movePct)}
              </span>
            </div>
          </div>
        </div>
      </header>

      <section className="chart-stage">
        <MarketContext
          market={market}
          position={null}
          quote={null}
          estimatedNetPnl={null}
          theme={theme}
          active={active}
        />
        <MarketCanvas
          market={market}
          theme={theme}
          entry={null}
          breakEven={null}
          stopLoss={null}
          takeProfit={null}
          liquidation={null}
          side={null}
          mode="live"
          active={active}
          animate={false}
          windowSeconds={90}
        />
        <div className="execution-dock preview-execution-dock">
          <div className="terms">
            <PreviewTerm label="Amount" value={money(amount)} />
            <PreviewTerm label="Leverage" value={`${settings.leverage}x`} />
            <PreviewTerm label="Exposure" value={money(amount * Math.min(settings.leverage, market.maxLeverage))} />
            <PreviewTerm label="Est. cost" value="Quoting" />
          </div>
        </div>
      </section>
    </div>
  );
}

function PreviewTerm({ label, value }: { label: string; value: string }) {
  return (
    <div className="term">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
