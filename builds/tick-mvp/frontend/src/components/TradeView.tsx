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
import { MarketContext } from "./MarketContext";

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
  onFund: () => void;
};

type Cue = "LONG" | "SHORT" | "CLOSE" | "WAIT" | "LOCKED";

export function TradeView(props: Props) {
  const theme = themeFor(props.market.market);
  const [cue, setCue] = useState<Cue | null>(null);
  const pointer = useRef<{ id: number; x: number; y: number } | null>(null);
  const cueTimer = useRef<number | null>(null);
  const previewQuote = [props.quotes.long, props.quotes.short].find(
    (quote) => quote?.market === props.market.market
  ) ?? null;
  const leverage = props.position?.leverage ?? previewQuote?.leverage ?? props.settings.leverage;
  const cost = previewQuote?.estimatedRoundTripCostUsd ?? 0;
  const amount = previewQuote?.ticketUsd ?? props.settings.ticketUsd;
  const exposure = previewQuote?.notionalUsd ?? amount * leverage;
  const costPct = amount > 0 ? cost / amount * 100 : 0;
  const positionOpening = props.position?.status === "opening";
  const positionClosing = props.position?.status === "closing" || props.busyAction === "close";
  const executionPending = positionOpening || positionClosing || props.busy;
  const positionCost = props.position ? props.quote?.estimatedRoundTripCostUsd ?? 0 : 0;
  const breakEven = props.position?.entryPrice && props.position.notionalUsd > 0 && positionCost > 0
    ? props.position.entryPrice * (
      1 + (props.position.side === "long" ? 1 : -1) * positionCost / props.position.notionalUsd
    )
    : null;

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
              <b className="leverage-chip">{leverage}x</b>
            </div>
            <span className="market-full-name">{props.market.name}</span>
            <div className="market-price-row">
              <b>{price(props.market.price)}</b>
              <span className={props.market.movePct >= 0 ? "positive" : "negative"}>
                {percent(props.market.movePct)}
              </span>
            </div>
          </div>
        </div>
        <div className="balance-summary">
          <span>AVAILABLE</span>
          <strong>{money(props.balances?.usdc)}</strong>
          {(props.balances?.usdc ?? 0) <= 0 ? (
            <button type="button" onClick={props.onFund}>Add funds</button>
          ) : null}
        </div>
      </header>

      <section className="chart-stage">
        <MarketContext
          market={props.market}
          position={props.position}
          quote={props.quote}
          estimatedNetPnl={props.estimatedNetPnl}
          theme={theme}
        />
        <MarketCanvas
          market={props.market}
          theme={theme}
          entry={props.position?.entryPrice ?? null}
          breakEven={breakEven}
          stopLoss={props.position?.stopLossPrice ?? props.quote?.stopLossPrice ?? null}
          takeProfit={props.position?.takeProfitPrice ?? props.quote?.takeProfitPrice ?? null}
          liquidation={props.position?.liquidationPrice ?? props.quote?.liquidationPrice ?? null}
          side={props.position?.side ?? null}
        />

        {props.position ? (
          <div className={`pnl-panel ${executionPending ? "execution-pending" : ""}`}>
            <span>
              {positionClosing ? "CLOSING" : positionOpening ? "OPENING" : props.position.side.toUpperCase()} · {props.position.leverage}x
            </span>
            {positionClosing ? (
              <strong>Exiting</strong>
            ) : positionOpening || props.estimatedNetPnl === null ? (
              <strong>Matching</strong>
            ) : (
              <strong className={props.estimatedNetPnl >= 0 ? "positive" : "negative"}>
                {signedMoney(props.estimatedNetPnl)}
              </strong>
            )}
            {executionPending ? <ExecutionProgress /> : null}
            <small>
              {positionClosing
                ? "position remains exposed"
                : positionOpening
                  ? "waiting for venue execution"
                  : "estimated net if closed now"}
            </small>
          </div>
        ) : props.busyAction === "long" || props.busyAction === "short" ? (
          <div className="pnl-panel execution-pending">
            <span>{props.busyAction.toUpperCase()} · {leverage}x</span>
            <strong>Submitting</strong>
            <ExecutionProgress />
            <small>sending execution request</small>
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
              {props.closedResult.pnl === null ? "Finalizing" : signedMoney(props.closedResult.pnl)}
            </strong>
            <small className="result-state">
              {props.closedResult.pnl === null ? "closed · finalizing result" : "final net"}
            </small>
          </div>
        ) : null}

        {props.error ? <div className="error-toast">{props.error}</div> : null}

        <div className="execution-dock">
          <div className="terms">
            {props.position ? (
              <>
                <Term label="Amount" value={money(props.position.ticketUsd)} />
                <Term label="SL away" value={distance(props.market.price, props.position.stopLossPrice)} />
                <Term label="TP away" value={distance(props.market.price, props.position.takeProfitPrice)} />
                <Term label="Liq away" value={distance(props.market.price, props.position.liquidationPrice)} />
              </>
            ) : (
              <>
                <Term label="Amount" value={money(amount)} />
                <Term label="Leverage" value={`${leverage}x`} />
                <Term label="Exposure" value={money(exposure)} />
                <Term
                  label="Est. cost"
                  value={money(cost)}
                  detail={cost > 0 ? `${costPct.toFixed(1)}% of amount` : undefined}
                />
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

function Term({
  label,
  value,
  detail
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <div className="term">
      <span>{label}</span>
      <strong>{value === "0.00000" ? "--" : value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function ExecutionProgress() {
  return (
    <div className="execution-progress" aria-hidden="true">
      <i />
    </div>
  );
}
