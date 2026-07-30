import { Maximize2, Minimize2, WalletCards } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api";
import { distance, money, percent, price, signedMoney } from "../format";
import { themeFor } from "../theme";
import type {
  ClosedResult,
  Market,
  MarketBar,
  MarketObservation,
  Position,
  Quote,
  Side,
  TradeSettings,
  WalletBalances
} from "../types";
import { GestureGuide } from "./GestureGuide";
import { MarketCanvas } from "./MarketCanvas";
import { MarketContext } from "./MarketContext";
import { MarketSwipePreview } from "./MarketSwipePreview";
import { useTradeSwipe } from "./useTradeSwipe";
import type { SwipeAction, SwipeCue } from "./useTradeSwipe";

type Props = {
  userId: string;
  markets: Market[];
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

type Cue = SwipeCue;
type ChartMode = "live" | "context";
type ChartTransition = "expanding" | "collapsing";
type ContextSnapshot = {
  bars: MarketBar[];
  observations: MarketObservation[];
  actualWindowSeconds: number;
  partial: boolean;
  fetchedAt: number;
};

const CONTEXT_SECONDS = 60 * 60;
const CHART_TRANSITION_MS = 1_200;
const contextCache = new Map<string, ContextSnapshot>();

export function TradeView(props: Props) {
  const theme = themeFor(props.market.market);
  const [cue, setCue] = useState<Cue | null>(null);
  const [chartMode, setChartMode] = useState<ChartMode>("live");
  const [chartTransition, setChartTransition] = useState<ChartTransition | null>(null);
  const [context, setContext] = useState<ContextSnapshot | null>(
    () => contextCache.get(props.market.market) ?? null
  );
  const [contextLoading, setContextLoading] = useState(false);
  const cueTimer = useRef<number | null>(null);
  const chartTransitionTimer = useRef<number | null>(null);
  const previewQuote = [props.quotes.long, props.quotes.short].find(
    (quote) => quote?.market === props.market.market
  ) ?? null;
  const leverage = props.position?.leverage ?? previewQuote?.leverage ?? props.settings.leverage;
  const cost = previewQuote?.estimatedRoundTripCostUsd ?? 0;
  const amount = previewQuote?.ticketUsd ?? props.settings.ticketUsd;
  const exposure = previewQuote?.notionalUsd ?? amount * leverage;
  const costPct = amount > 0 ? cost / amount * 100 : 0;
  const available = props.balances?.spendableUsdc ?? props.balances?.usdc;
  const needsFunding = available !== null && available !== undefined && available < amount;
  const positionOpening = props.position?.status === "opening";
  const positionClosing = props.position?.status === "closing" || props.busyAction === "close";
  const executionPending = positionOpening || positionClosing || props.busy;
  const positionCost = props.position ? props.quote?.estimatedRoundTripCostUsd ?? 0 : 0;
  const breakEven = props.position?.entryPrice && props.position.notionalUsd > 0 && positionCost > 0
    ? props.position.entryPrice * (
      1 + (props.position.side === "long" ? 1 : -1) * positionCost / props.position.notionalUsd
    )
    : null;
  const chartObservations = useMemo(
    () => morphObservations(context, props.market),
    [context, props.market.market, props.market.price, props.market.sequence]
  );
  const contextRange = useMemo(
    () => hourRange(context, props.market.price),
    [context, props.market.price]
  );

  useEffect(() => {
    let canceled = false;
    setChartMode("live");
    setChartTransition(null);
    if (chartTransitionTimer.current) window.clearTimeout(chartTransitionTimer.current);
    const cached = contextCache.get(props.market.market) ?? null;
    setContext(cached);

    const load = async () => {
      if (!cached || Date.now() - cached.fetchedAt > 30_000) setContextLoading(true);
      try {
        const chart = await api.chart(props.market.market, CONTEXT_SECONDS);
        if (canceled) return;
        const next = {
          bars: chart.bars,
          observations: chart.observations,
          actualWindowSeconds: chart.actualWindowSeconds,
          partial: chart.partial,
          fetchedAt: Date.now()
        };
        contextCache.set(props.market.market, next);
        setContext(next);
      } catch {
        // LIVE remains usable if context history has not finished loading.
      } finally {
        if (!canceled) setContextLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(load, 30_000);
    return () => {
      canceled = true;
      window.clearInterval(timer);
    };
  }, [props.market.market]);

  useEffect(() => () => {
    if (chartTransitionTimer.current) window.clearTimeout(chartTransitionTimer.current);
  }, []);

  const toggleChartWindow = () => {
    if (!context || chartTransition) return;
    const nextMode: ChartMode = chartMode === "live" ? "context" : "live";
    setChartTransition(nextMode === "context" ? "expanding" : "collapsing");
    setChartMode(nextMode);
    if (chartTransitionTimer.current) window.clearTimeout(chartTransitionTimer.current);
    chartTransitionTimer.current = window.setTimeout(() => {
      setChartTransition(null);
      chartTransitionTimer.current = null;
    }, CHART_TRANSITION_MS);
  };

  const flash = (next: Cue) => {
    setCue(next);
    if (cueTimer.current) window.clearTimeout(cueTimer.current);
    cueTimer.current = window.setTimeout(() => setCue(null), 520);
    navigator.vibrate?.(next === "WAIT" || next === "LOCKED" ? 14 : 8);
  };

  const swipe = useTradeSwipe({
    marketId: props.market.market,
    positionSide: props.position?.side ?? null,
    busy: props.busy,
    needsFunding,
    onOpen: props.onOpen,
    onClose: props.onClose,
    onShift: props.onShift,
    onFund: props.onFund,
    onCue: flash,
    onChartDoubleTap: toggleChartWindow
  });
  const previousMarket = adjacentMarket(props.markets, props.market.market, -1);
  const nextMarket = adjacentMarket(props.markets, props.market.market, 1);

  return (
    <main
      ref={swipe.rootRef}
      className="trade-view"
      {...swipe.handlers}
    >
      <SwipeActionLayer action={swipe.action} />
      <div className="trade-header-shell" aria-hidden="true" />
      <button
        className="balance-summary trade-balance-fixed"
        type="button"
        aria-label={`Available balance ${money(available)}. Deposit USDC`}
        onClick={props.onFund}
        onPointerDown={(event) => event.stopPropagation()}
      >
        <WalletCards aria-hidden="true" />
        <strong>{money(available)}</strong>
      </button>
      {previousMarket ? (
        <MarketSwipePreview
          market={previousMarket}
          offset={-1}
          active={swipe.previewOffset === -1}
          settings={props.settings}
        />
      ) : null}
      {nextMarket ? (
        <MarketSwipePreview
          market={nextMarket}
          offset={1}
          active={swipe.previewOffset === 1}
          settings={props.settings}
        />
      ) : null}
      <div className="trade-scene">
      <header className="trade-header market-page-header">
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
      </header>

      <section
        className={[
          "chart-stage",
          `chart-${chartMode}`,
          chartTransition ? `chart-transition-${chartTransition}` : ""
        ].filter(Boolean).join(" ")}
      >
        <button
          type="button"
          className={[
            "chart-mode-button",
            chartMode === "context" ? "is-context" : "",
            chartTransition ? "is-transitioning" : ""
          ].filter(Boolean).join(" ")}
          aria-label={
            chartTransition === "expanding"
              ? "Opening one hour chart"
              : chartTransition === "collapsing"
                ? "Returning to live chart"
                : chartMode === "live"
                  ? "Zoom out chart"
                  : "Zoom in chart"
          }
          disabled={(chartMode === "live" && !context) || chartTransition !== null}
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            toggleChartWindow();
          }}
        >
          {chartMode === "live" ? <Maximize2 aria-hidden="true" /> : <Minimize2 aria-hidden="true" />}
          <span>
            {chartTransition === "expanding"
              ? "EXPANDING"
              : chartTransition === "collapsing"
                ? "COLLAPSING"
                : chartMode === "live"
                  ? contextLoading ? "LOADING" : "ZOOM OUT"
                  : "ZOOM IN"}
          </span>
          <small>
            {chartTransition === "expanding"
              ? "1H"
              : chartTransition === "collapsing"
                ? "90S"
                : chartMode === "live"
                  ? "1H"
                  : "90S"}
          </small>
        </button>
        {chartMode === "live" && !chartTransition ? (
          <MarketContext
            key={`context-${props.market.market}`}
            market={props.market}
            position={props.position}
            quote={props.quote}
            estimatedNetPnl={props.estimatedNetPnl}
            theme={theme}
          />
        ) : chartMode === "context" && !chartTransition && context ? (
          <>
            <div className="context-caption">
              <strong>1H CONTEXT</strong>
              <span>{coverageLabel(context)} collected</span>
            </div>
            {contextRange ? <HourRangeRail range={contextRange} accent={theme.accent} /> : null}
          </>
        ) : null}
        <MarketCanvas
          key={`chart-${props.market.market}`}
          market={props.market}
          theme={theme}
          entry={props.position?.entryPrice ?? null}
          breakEven={breakEven}
          stopLoss={props.position?.stopLossPrice ?? props.quote?.stopLossPrice ?? null}
          takeProfit={props.position?.takeProfitPrice ?? props.quote?.takeProfitPrice ?? null}
          liquidation={props.position?.liquidationPrice ?? props.quote?.liquidationPrice ?? null}
          side={props.position?.side ?? null}
          mode="live"
          active
          windowSeconds={
            chartMode === "context" && context
              ? contextWindowSeconds(context)
              : 90
          }
          windowTransitionMs={CHART_TRANSITION_MS}
          ariaWindowLabel={chartMode === "context" ? "one hour context" : "live price"}
          observations={chartObservations}
          bars={context?.bars}
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

        {props.error ? (
          fundingError(props.error) ? (
            <div className="funding-prompt" role="alert">
              <span>
                <strong>Add USDC to trade</strong>
                <small>Your amount is larger than the available balance.</small>
              </span>
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={props.onFund}
              >
                Deposit
              </button>
            </div>
          ) : <div className="error-toast">{props.error}</div>
        ) : null}

        {!props.position && !props.busy ? (
          <GestureGuide userId={props.userId} />
        ) : null}

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
      </div>
    </main>
  );
}

function SwipeActionLayer({ action }: { action: SwipeAction | null }) {
  if (!action) return <div className="swipe-action-layer" aria-hidden="true" />;
  const prefix = action.label === "WAIT"
    ? "EXECUTION BUSY"
    : action.label === "POSITION LOCKED"
      ? "POSITION OPEN"
      : action.armed
        ? "RELEASE TO"
        : "PULL TO";

  return (
    <div
      className={[
        "swipe-action-layer",
        `swipe-action-${action.direction}`,
        action.armed ? "is-armed" : "",
        action.blocked ? "is-blocked" : ""
      ].filter(Boolean).join(" ")}
      aria-hidden="true"
    >
      <div className="swipe-action-content">
        <span>{prefix}</span>
        <strong>{action.label}</strong>
        <div className="swipe-action-progress"><i /></div>
      </div>
    </div>
  );
}

function adjacentMarket(markets: Market[], currentMarket: string, offset: -1 | 1): Market | null {
  if (markets.length < 2) return null;
  const currentIndex = markets.findIndex((market) => market.market === currentMarket);
  if (currentIndex < 0) return null;
  return markets[(currentIndex + offset + markets.length) % markets.length] ?? null;
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

function fundingError(message: string): boolean {
  return /insufficient.*usdc|usdc.*balance/i.test(message);
}

type HourRange = {
  high: number;
  low: number;
  current: number;
  positionPct: number;
};

function contextLine(snapshot: ContextSnapshot | null, market: Market): MarketObservation[] {
  if (!snapshot) return [];
  if (!snapshot.bars.length) {
    return sampleObservations(snapshot.observations, 260);
  }

  const limit = 260;
  const groupSize = Math.max(1, Math.ceil(snapshot.bars.length / limit));
  const observations: MarketObservation[] = [];
  for (let index = 0; index < snapshot.bars.length; index += groupSize) {
    const group = snapshot.bars.slice(index, index + groupSize);
    const last = group[group.length - 1];
    observations.push({
      seq: last.lastSeq,
      receivedTs: last.bucketTs,
      price: last.close,
      unchanged: false
    });
  }

  const latest = observations[observations.length - 1];
  const now = Date.now() / 1000;
  if (!latest || market.sequence > latest.seq || now - latest.receivedTs > 1) {
    observations.push({
      seq: market.sequence,
      receivedTs: now,
      price: market.price,
      unchanged: latest?.price === market.price
    });
  }
  return observations;
}

function morphObservations(
  snapshot: ContextSnapshot | null,
  market: Market
): MarketObservation[] {
  const context = contextLine(snapshot, market);
  const liveStart = market.observations[0]?.receivedTs ?? Number.POSITIVE_INFINITY;
  return [
    ...context.filter((observation) => observation.receivedTs < liveStart),
    ...market.observations
  ];
}

function sampleObservations(observations: MarketObservation[], limit: number): MarketObservation[] {
  if (observations.length <= limit) return observations;
  const step = Math.ceil(observations.length / limit);
  const sampled = observations.filter((_, index) => index % step === 0);
  const latest = observations[observations.length - 1];
  if (sampled[sampled.length - 1]?.seq !== latest.seq) sampled.push(latest);
  return sampled;
}

function hourRange(snapshot: ContextSnapshot | null, current: number): HourRange | null {
  if (!snapshot) return null;
  const highs = snapshot.bars.length
    ? snapshot.bars.map((bar) => bar.high)
    : snapshot.observations.map((observation) => observation.price);
  const lows = snapshot.bars.length
    ? snapshot.bars.map((bar) => bar.low)
    : snapshot.observations.map((observation) => observation.price);
  if (!highs.length || !lows.length) return null;

  const high = Math.max(current, ...highs);
  const low = Math.min(current, ...lows);
  const span = high - low;
  return {
    high,
    low,
    current,
    positionPct: span > 0 ? Math.max(0, Math.min(100, (current - low) / span * 100)) : 50
  };
}

function contextWindowSeconds(snapshot: ContextSnapshot): number {
  const barCoverage = snapshot.bars.length > 1
    ? snapshot.bars[snapshot.bars.length - 1].bucketTs - snapshot.bars[0].bucketTs
    : 0;
  const coverage = barCoverage > 0 ? barCoverage : snapshot.actualWindowSeconds;
  return Math.max(60, Math.min(CONTEXT_SECONDS, coverage + 3));
}

function coverageLabel(snapshot: ContextSnapshot): string {
  const seconds = contextWindowSeconds(snapshot);
  if (seconds >= 59 * 60) return "full hour";
  if (seconds >= 120) return `${Math.floor(seconds / 60)}M`;
  return `${Math.floor(seconds)}S`;
}

function HourRangeRail({ range, accent }: { range: HourRange; accent: string }) {
  const markerTop = 100 - range.positionPct;
  return (
    <div
      className="hour-range-rail"
      style={{ "--range-accent": accent } as React.CSSProperties}
      aria-label={`Current price is ${Math.round(range.positionPct)} percent through the collected range`}
    >
      <div className="hour-range-label hour-range-high">
        <strong>1H HIGH</strong>
        <span>{price(range.high, true)}</span>
      </div>
      <div className="hour-range-track">
        <i style={{ top: `${markerTop}%` }} />
      </div>
      <div className="hour-range-label hour-range-low">
        <strong>1H LOW</strong>
        <span>{price(range.low, true)}</span>
      </div>
    </div>
  );
}
