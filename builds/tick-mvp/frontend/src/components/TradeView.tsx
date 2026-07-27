import { useRef, useState } from "react";

import { distance, money, percent, price, signedMoney } from "../format";
import { themeFor } from "../theme";
import type {
  ClosedResult,
  Market,
  Position,
  Quote,
  Side,
  TradeSettings,
  WalletBalances
} from "../types";
import { MarketCanvas } from "./MarketCanvas";

type Props = {
  market: Market;
  position: Position | null;
  quote: Quote | null;
  quotes: { long: Quote | null; short: Quote | null };
  balances: WalletBalances | null;
  settings: TradeSettings;
  estimatedNetPnl: number | null;
  busy: boolean;
  busyAction: Side | "close" | null;
  error: string | null;
  closedResult: ClosedResult | null;
  onOpen: (side: Side) => void;
  onClose: () => void;
  onShift: (offset: number) => void;
};

type Cue = "LONG" | "SHORT" | "CLOSE" | "WAIT" | "LOCKED";

export function TradeView(props: Props) {
  const theme = themeFor(props.market.market);
  const [cue, setCue] = useState<Cue | null>(null);
  const pointer = useRef<{ id: number; x: number; y: number } | null>(null);
  const cueTimer = useRef<number | null>(null);
  const leverage = Math.min(props.settings.leverage, props.market.maxLeverage);
  const previewQuote = props.quotes.long ?? props.quotes.short;
  const cost = previewQuote?.estimatedRoundTripCostUsd ?? 0;
  const positionOpening = props.position?.status === "opening";
  const positionClosing = props.position?.status === "closing" || props.busyAction === "close";

  const flash = (next: Cue) => {
    setCue(next);
    if (cueTimer.current) window.clearTimeout(cueTimer.current);
    cueTimer.current = window.setTimeout(() => setCue(null), 520);
    navigator.vibrate?.(next === "WAIT" || next === "LOCKED" ? 14 : 8);
  };

  const release = (event: React.PointerEvent<HTMLElement>) => {
    const start = pointer.current;
    pointer.current = null;
    if (!start || start.id !== event.pointerId) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    const horizontal = Math.abs(dx);
    const vertical = Math.abs(dy);

    if (horizontal > 48 && horizontal > vertical * 1.15) {
      if (props.position || props.busy) return flash("LOCKED");
      navigator.vibrate?.(5);
      if (dx < 0) {
        props.onShift(1);
      } else {
        props.onShift(-1);
      }
      return;
    }

    if (vertical <= 54 || vertical <= horizontal * 1.12) return;
    if (props.busy) return flash("WAIT");
    const side: Side = dy < 0 ? "long" : "short";
    if (props.position) {
      if (props.position.side !== side) return flash("LOCKED");
      flash("CLOSE");
      props.onClose();
      return;
    }
    flash(side === "long" ? "LONG" : "SHORT");
    props.onOpen(side);
  };

  return (
    <main
      className="trade-view"
      style={{ backgroundColor: theme.top }}
      onPointerDown={(event) => {
        pointer.current = { id: event.pointerId, x: event.clientX, y: event.clientY };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerUp={release}
      onPointerCancel={() => {
        pointer.current = null;
      }}
    >
      <header className="trade-header">
        <div className="market-heading">
          <div className="market-name">
            <div className="market-name-row">
              <strong>{props.market.symbol}</strong>
              <b style={{ color: theme.glow }}>{leverage}x</b>
              <span>{props.market.name}</span>
            </div>
            <div className="market-price-row">
              <b>{price(props.market.price)}</b>
              <span className={props.market.movePct >= 0 ? "positive" : "negative"}>
                {percent(props.market.movePct)}
              </span>
            </div>
          </div>
        </div>
        <div className="balance-chip">
          <span>Balance</span>
          <strong>{money(props.balances?.usdc)}</strong>
        </div>
      </header>

      <section className="chart-stage">
        <MarketCanvas
          market={props.market}
          theme={theme}
          entry={props.position?.entryPrice ?? null}
          stopLoss={props.position?.stopLossPrice ?? props.quote?.stopLossPrice ?? null}
          takeProfit={props.position?.takeProfitPrice ?? props.quote?.takeProfitPrice ?? null}
          liquidation={props.position?.liquidationPrice ?? props.quote?.liquidationPrice ?? null}
          side={props.position?.side ?? null}
        />

        {props.position ? (
          <div className="pnl-panel">
            <span>
              {positionClosing ? "CLOSING" : positionOpening ? "OPENING" : props.position.side.toUpperCase()} · {props.position.leverage}x
            </span>
            {positionClosing ? (
              <strong>Exiting</strong>
            ) : positionOpening || props.estimatedNetPnl === null ? (
              <strong>Opening</strong>
            ) : (
              <strong className={props.estimatedNetPnl >= 0 ? "positive" : "negative"}>
                {signedMoney(props.estimatedNetPnl)}
              </strong>
            )}
            <small>
              {positionClosing ? "venue close sent" : positionOpening ? "venue confirmation" : "estimated net"}
            </small>
          </div>
        ) : props.busyAction === "long" || props.busyAction === "short" ? (
          <div className="pnl-panel">
            <span>{props.busyAction.toUpperCase()} · {leverage}x</span>
            <strong>Opening</strong>
            <small>order accepted</small>
          </div>
        ) : null}

        {cue ? (
          <div className={`gesture-cue ${cue === "LONG" ? "positive" : cue === "SHORT" ? "negative" : ""}`}>
            {cue}
          </div>
        ) : null}

        {props.closedResult ? (
          <div
            className={`result-pop result-${props.closedResult.reason ?? "closed"}`}
            role="status"
          >
            <div className="result-copy">
              <span>{props.closedResult.label}</span>
              <small>{props.closedResult.market}</small>
            </div>
            <strong
              className={
                props.closedResult.pnl === null
                  ? ""
                  : props.closedResult.pnl >= 0
                    ? "positive"
                    : "negative"
              }
            >
              {props.closedResult.pnl === null ? "Settling" : signedMoney(props.closedResult.pnl)}
            </strong>
            <small className="result-state">
              {props.closedResult.pnl === null ? "venue confirmed" : "final net"}
            </small>
          </div>
        ) : null}

        {props.error ? <div className="error-toast">{props.error}</div> : null}

        <div className="execution-dock">
          <div className="terms">
            {props.position ? (
              <>
                <Term label="Collateral" value={money(props.position.ticketUsd)} />
                <Term label="SL away" value={distance(props.market.price, props.position.stopLossPrice)} />
                <Term label="TP away" value={distance(props.market.price, props.position.takeProfitPrice)} />
                <Term label="Liq away" value={distance(props.market.price, props.position.liquidationPrice)} />
              </>
            ) : (
              <>
                <Term label="Collateral" value={money(props.settings.ticketUsd)} />
                <Term label="Stop loss" value={props.settings.stopLossEnabled ? money(props.settings.maxLossUsd) : "Off"} />
                <Term label="Take profit" value={props.settings.takeProfitEnabled ? money(props.settings.takeProfitUsd) : "Off"} />
                <Term label="Est. cost" value={money(cost)} />
              </>
            )}
          </div>
          {props.position ? (
            <button className="close-button" disabled={props.busy} onClick={props.onClose}>
              {positionOpening ? "Confirming" : positionClosing ? "Closing" : "Close"}
            </button>
          ) : null}
        </div>
      </section>
    </main>
  );
}

function Term({ label, value }: { label: string; value: string }) {
  return (
    <div className="term">
      <span>{label}</span>
      <strong>{value === "0.00000" ? "--" : value}</strong>
    </div>
  );
}
