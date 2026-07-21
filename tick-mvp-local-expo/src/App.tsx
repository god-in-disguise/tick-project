import React, { useEffect, useMemo, useRef, useState } from "react";
import { StatusBar, Text, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import { api } from "./api";
import { MARKET_REFRESH_MS, QUOTE_REFRESH_MS, STATE_POLL_MS, TAPE_POLL_MS, TICKET_USD } from "./config";
import {
  allowedLeverage,
  chartPointsFromTicks,
  compactChartPoints,
  idempotencyKey,
  mergeTicks,
  seedChartPoints,
  sideForDirection,
  toMarket
} from "./market";
import type { AccountState, ChartPoint, Direction, Execution, FeedStatus, Market, Position, Quotes, Tab, TradeQuote } from "./types";
import { BottomNav } from "./components/BottomNav";
import { Dashboard } from "./components/Dashboard";
import { Profile } from "./components/Profile";
import { TradeScreen } from "./components/TradeScreen";
import { styles } from "./styles";

type ClosedResult = {
  id: string;
  pair: string;
  pnl: number | null;
  grossPnl: number | null;
  costDrag: number | null;
  durationSeconds: number;
  label: string;
} | null;

const emptyQuotes: Quotes = { long: null, short: null };

export default function App() {
  return (
    <SafeAreaProvider>
      <TickApp />
    </SafeAreaProvider>
  );
}

function TickApp() {
  const [tab, setTab] = useState<Tab>("trade");
  const [markets, setMarkets] = useState<Market[]>([]);
  const [activePair, setActivePair] = useState("");
  const [account, setAccount] = useState<AccountState | null>(null);
  const [quotes, setQuotes] = useState<Quotes>(emptyQuotes);
  const [history, setHistory] = useState<Execution[]>([]);
  const [leveragePreset, setLeveragePreset] = useState(100);
  const [pendingExecution, setPendingExecution] = useState<Execution | null>(null);
  const [closedResult, setClosedResult] = useState<ClosedResult>(null);
  const [submitting, setSubmitting] = useState<"long" | "short" | "close" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tapeStale, setTapeStale] = useState(false);
  const [tapeStatus, setTapeStatus] = useState<FeedStatus>("resyncing");
  const tapeInFlight = useRef<Record<string, boolean>>({});
  const quoteRequests = useRef<Record<string, Promise<Quotes>>>({});
  const currentQuoteKey = useRef("");
  const activePairRef = useRef("");
  const chartLoads = useRef<Record<string, { status: "loading" | "loaded"; at: number }>>({});
  const tapeSequence = useRef<Record<string, number>>({});
  const stateInFlight = useRef(false);
  const stateSocket = useRef<WebSocket | null>(null);
  const stateSocketReconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateSocketClosed = useRef(false);
  const quotesRef = useRef<Quotes>(emptyQuotes);
  const lastExecutionRef = useRef("");
  const actionInFlight = useRef(false);
  const positionRef = useRef<Position | null>(null);
  const lastForcedMarkRefresh = useRef(0);
  const errorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedResultTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const market = useMemo(
    () => markets.find((item) => item.pair === activePair) ?? markets[0],
    [activePair, markets]
  );
  const pendingPosition = pendingExecution?.action === "open" && ["created", "opening"].includes(pendingExecution.status)
    ? pendingExecution.position
    : null;
  const position = account?.positions[0] ?? pendingPosition ?? null;
  positionRef.current = position;
  const marketForScreen = useMemo(() => {
    if (!market || !position || position.pair !== market.pair || tapeStatus === "live") return market;
    if (!Number.isFinite(position.mark) || position.mark <= 0) return market;
    return { ...market, price: position.mark };
  }, [market, position, tapeStatus]);
  const livePosition = useMemo(() => {
    if (!position || !marketForScreen || position.pair !== marketForScreen.pair || !position.entry) return position;
    const direction = position.side === "long" ? 1 : -1;
    const price = tapeStatus === "live" ? marketForScreen.price : position.mark;
    const move = ((price - position.entry) / position.entry) * direction;
    const grossPnl = position.collateral * position.leverage * move;
    const estimatedAllInCostUsd = position.estimatedAllInCostUsd || position.estimatedOpenCostUsd + position.estimatedCloseCostUsd;
    return {
      ...position,
      mark: price,
      grossPnl,
      estimatedAllInCostUsd,
      estimatedNetPnl: grossPnl - estimatedAllInCostUsd,
      roePct: position.collateral ? (grossPnl / position.collateral) * 100 : 0
    };
  }, [marketForScreen?.price, position, tapeStatus]);
  const execution = account?.execution ?? pendingExecution;
  const maxLeverage = market?.maxLeverage ?? 25;
  const leverage = allowedLeverage(leveragePreset, maxLeverage);
  currentQuoteKey.current = market ? `${market.pair}:${leverage}` : "";
  activePairRef.current = market?.pair ?? "";

  useEffect(() => {
    if (!market) return;
    setLeveragePreset(market.suggestedLeverage || market.maxLeverage || 100);
  }, [market?.pair]);

  useEffect(() => {
    stateSocketClosed.current = false;
    refreshMarkets();
    refreshState();
    refreshHistory();
    connectStateStream();
    const marketTimer = setInterval(refreshMarkets, MARKET_REFRESH_MS);
    const stateTimer = setInterval(refreshState, STATE_POLL_MS);
    return () => {
      stateSocketClosed.current = true;
      if (stateSocketReconnectTimer.current) clearTimeout(stateSocketReconnectTimer.current);
      stateSocket.current?.close();
      clearInterval(marketTimer);
      clearInterval(stateTimer);
      if (errorTimer.current) clearTimeout(errorTimer.current);
      if (closedResultTimer.current) clearTimeout(closedResultTimer.current);
      if (stateRefreshTimer.current) clearTimeout(stateRefreshTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!market) return;
    loadChart(market.pair);
    const index = markets.findIndex((item) => item.pair === market.pair);
    for (const offset of [-1, 1]) {
      const neighbor = markets[(index + offset + markets.length) % markets.length];
      if (neighbor) loadChart(neighbor.pair);
    }
  }, [market?.pair, markets.length]);

  useEffect(() => {
    if (!market) return;
    pollTape(market.pair);
    const timer = setInterval(() => pollTape(market.pair), TAPE_POLL_MS);
    return () => clearInterval(timer);
  }, [market?.pair]);

  useEffect(() => {
    if (!market || position || isBusy(execution)) return;
    quotesRef.current = emptyQuotes;
    setQuotes(emptyQuotes);
    refreshQuotes(market.pair, leverage);
    const timer = setInterval(() => refreshQuotes(market.pair, leverage), QUOTE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [market?.pair, leverage, position?.pair, execution?.status]);

  useEffect(() => {
    if (position && activePair !== position.pair) setActivePair(position.pair);
  }, [position?.pair]);

  async function refreshMarkets() {
    try {
      const response = await api.markets();
      if (!response.markets.length) return;
      setMarkets((current) => {
        const previous = new Map(current.map((item) => [item.pair, item]));
        const incoming = response.markets.map((item) => toMarket(item, previous.get(item.pair)));
        if (!current.length) return incoming;
        const updated = new Map(incoming.map((item) => [item.pair, item]));
        const stable = current.map((item) => updated.get(item.pair) ?? item);
        for (const item of incoming) if (!stable.some((existing) => existing.pair === item.pair)) stable.push(item);
        return stable;
      });
      setActivePair((current) => current || response.markets[0].pair);
    } catch (cause) {
      showError(cause);
    }
  }

  async function refreshState(force = false) {
    if (stateInFlight.current && !force) return;
    stateInFlight.current = true;
    try {
      const next = await api.state(force);
      applyAccountState(next);
    } catch (cause) {
      showError(cause, false);
    } finally {
      stateInFlight.current = false;
    }
  }

  function applyAccountState(next: AccountState) {
    setAccount(next);
    setSubmitting(null);
    if (next.execution) setPendingExecution(next.execution);
    if (!next.execution && next.lastExecution && ["closed", "failed"].includes(next.lastExecution.status)) {
      setPendingExecution((current) => current?.id === next.lastExecution?.id ? null : current);
    }
    handleLastExecution(next.lastExecution);
  }

  function connectStateStream() {
    if (stateSocketClosed.current) return;
    if (stateSocket.current && stateSocket.current.readyState <= 1) return;
    const socket = new WebSocket(api.stateStreamUrl());
    stateSocket.current = socket;

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(String(event.data)) as { type?: string; state?: AccountState };
        if (message.type === "state" && message.state) applyAccountState(message.state);
      } catch (cause) {
        showError(cause, false);
      }
    };
    socket.onerror = () => undefined;
    socket.onclose = () => {
      if (stateSocket.current === socket) stateSocket.current = null;
      if (stateSocketClosed.current) return;
      if (stateSocketReconnectTimer.current) clearTimeout(stateSocketReconnectTimer.current);
      stateSocketReconnectTimer.current = setTimeout(connectStateStream, 900);
    };
  }

  async function refreshHistory() {
    try {
      const response = await api.history();
      setHistory(response.trades);
    } catch (cause) {
      showError(cause, false);
    }
  }

  async function loadChart(pair: string, force = false) {
    const normalized = pair.toUpperCase().replace("/", "-");
    const currentLoad = chartLoads.current[normalized];
    if (currentLoad?.status === "loading") return;
    if (!force && currentLoad?.status === "loaded" && Date.now() - currentLoad.at < 15000) return;
    chartLoads.current[normalized] = { status: "loading", at: Date.now() };
    try {
      const chart = await api.chart(normalized);
      setMarkets((current) => current.map((item) => {
        if (item.pair !== normalized) return item;
        const observationPoints: ChartPoint[] = chart.observations
          ?.map((point) => ({
            time: point.receivedTs,
            price: Number(point.price),
            seq: point.seq,
            unchanged: point.unchanged
          }))
          .filter((point) => Number.isFinite(point.price) && point.price > 0 && Number.isFinite(point.time)) ?? [];
        const tickPoints = chartPointsFromTicks(chart.ticks);
        const source = observationPoints.length ? observationPoints : tickPoints.length ? tickPoints : seedChartPoints(chart.points, item.price);
        const chartPoints = compactChartPoints(source);
        const lastSequence = chart.lastSeq ?? chart.ticks[chart.ticks.length - 1]?.sequence ?? item.sequence;
        tapeSequence.current[normalized] = Math.max(tapeSequence.current[normalized] ?? 0, lastSequence);
        return {
          ...item,
          points: chartPoints.map((point) => point.price),
          chartPoints,
          sequence: Math.max(item.sequence, lastSequence)
        };
      }));
      chartLoads.current[normalized] = { status: "loaded", at: Date.now() };
    } catch (cause) {
      delete chartLoads.current[normalized];
      showError(cause, false);
    }
  }

  async function pollTape(pair: string) {
    const normalized = pair.toUpperCase().replace("/", "-");
    if (tapeInFlight.current[normalized]) return;
    tapeInFlight.current[normalized] = true;
    try {
      const response = await api.tape(normalized, tapeSequence.current[normalized] ?? 0);
      const feedStatus = response.feedStatus ?? (response.stale ? "stale" : "live");
      if (activePairRef.current === normalized) {
        setTapeStale(response.stale);
        setTapeStatus(feedStatus);
      }
      const activePosition = positionRef.current;
      if (
        activePosition?.pair === normalized
        && feedStatus !== "live"
        && Date.now() - lastForcedMarkRefresh.current > 1000
      ) {
        lastForcedMarkRefresh.current = Date.now();
        void refreshState(true);
      }
      const lastReturnedSequence = response.ticks[response.ticks.length - 1]?.sequence;
      const nextSequence = lastReturnedSequence ?? response.sequence;
      tapeSequence.current[normalized] = Math.max(nextSequence, tapeSequence.current[normalized] ?? 0);
      if (response.resyncRequired) void loadChart(normalized, true);
      setMarkets((items) => items.map((item) => item.pair === normalized ? mergeTicks(item, response.ticks, nextSequence) : item));
    } catch (cause) {
      if (activePairRef.current === normalized) setTapeStale(true);
      showError(cause, false);
    } finally {
      tapeInFlight.current[normalized] = false;
    }
  }

  async function refreshQuotes(pair: string, selectedLeverage: number): Promise<Quotes> {
    const key = `${pair}:${selectedLeverage}`;
    const pending = quoteRequests.current[key];
    if (pending) return pending;

    const request = Promise.all([
      api.quote(pair, "long", TICKET_USD, selectedLeverage),
      api.quote(pair, "short", TICKET_USD, selectedLeverage)
    ]).then(([long, short]) => {
      const next = { long, short };
      if (currentQuoteKey.current === key) {
        quotesRef.current = next;
        setQuotes(next);
      }
      return next;
    });
    quoteRequests.current[key] = request;
    try {
      return await request;
    } catch (cause) {
      showError(cause, false);
      return quotesRef.current;
    } finally {
      delete quoteRequests.current[key];
    }
  }

  async function open(direction: Direction) {
    if (!market || position || isBusy(execution) || actionInFlight.current) return;
    clearError();
    clearClosedResult();
    const side = sideForDirection(direction);
    actionInFlight.current = true;
    setSubmitting(side);
    let accepted = false;
    try {
      let quote = side === "long" ? quotes.long : quotes.short;
      if (!quote || quote.pair !== market.pair || !quoteMatchesLeverage(quote, leverage) || quote.expiresAt < Date.now() / 1000 + 0.6) {
        const refreshed = await refreshQuotes(market.pair, leverage);
        quote = side === "long" ? refreshed.long : refreshed.short;
      }
      if (!quote) throw new Error("Live terms are unavailable");
      if (!quote.openingAllowed) throw new Error("Market is closed");
      const next = await api.open(quote.quoteId, idempotencyKey("open", market.pair));
      accepted = true;
      setPendingExecution({ ...next, status: next.status === "created" ? "opening" : next.status });
      scheduleStateRefresh(120);
    } catch (cause) {
      showError(cause);
      await refreshState(true);
    } finally {
      actionInFlight.current = false;
      if (!accepted) setSubmitting(null);
    }
  }

  async function close() {
    if (!position || isBusy(execution) || actionInFlight.current) return;
    clearError();
    clearClosedResult();
    actionInFlight.current = true;
    setSubmitting("close");
    let accepted = false;
    try {
      const closingPosition = position;
      const next = await api.close(position.pair, idempotencyKey("close", position.pair));
      accepted = true;
      setPendingExecution({
        ...next,
        status: next.status === "created" ? "closing" : next.status,
        position: next.position ?? closingPosition
      });
      scheduleStateRefresh(120);
    } catch (cause) {
      showError(cause);
      await refreshState(true);
    } finally {
      actionInFlight.current = false;
      if (!accepted) setSubmitting(null);
    }
  }

  function selectMarket(pair: string) {
    if (position || isBusy(execution) || actionInFlight.current) return;
    clearClosedResult();
    setActivePair(pair);
    setTab("trade");
  }

  function shiftMarket(offset: number) {
    if (!market || position || isBusy(execution) || actionInFlight.current) return;
    clearClosedResult();
    const index = markets.findIndex((item) => item.pair === market.pair);
    const next = markets[(index + offset + markets.length) % markets.length];
    if (next) setActivePair(next.pair);
  }

  function handleLastExecution(last: Execution | null) {
    if (!last) return;
    const key = `${last.id}:${last.status}:${last.updatedAt}:${last.realizedWalletDelta ?? "settling"}`;
    if (key === lastExecutionRef.current) return;
    lastExecutionRef.current = key;
    if (last.status === "failed" || last.status === "unknown") showError(new Error(last.error || `Execution ${last.status}`));
    const result = last.result as {
      status?: string;
      durationSeconds?: number;
      position?: Partial<Pick<Position, "pnl" | "grossPnl" | "estimatedAllInCostUsd">>;
    } | null;
    const externalOpenFinalized = (
      last.action === "open"
      && last.status === "closed"
      && ["liquidated", "external_closed"].includes(String(result?.status ?? ""))
    );
    if ((last.action === "close" || externalOpenFinalized) && last.status === "closed") {
      if (closedResultTimer.current) clearTimeout(closedResultTimer.current);
      const liquidated = isLiquidatedResult(result);
      const grossPnl = liquidated ? null : realizedGrossPnl(result, last.position);
      const closedLabel = liquidated
        ? "Liquidated"
        : last.realizedWalletDelta === null
          ? "Closed"
          : last.realizedWalletDelta >= 0
            ? "Net profit"
            : "Net loss";
      setClosedResult({
        id: last.id,
        pair: last.pair,
        pnl: last.realizedWalletDelta,
        grossPnl,
        costDrag: liquidated ? null : costDrag(last.realizedWalletDelta, grossPnl, result, last.position),
        durationSeconds: result?.durationSeconds ?? 0,
        label: closedLabel
      });
      const visibleMs = last.realizedWalletDelta === null ? 10000 : liquidated ? 5600 : 3200;
      closedResultTimer.current = setTimeout(
        () => setClosedResult((current) => current?.id === last.id ? null : current),
        visibleMs
      );
      refreshHistory();
    }
  }

  function clearClosedResult() {
    if (closedResultTimer.current) {
      clearTimeout(closedResultTimer.current);
      closedResultTimer.current = null;
    }
    setClosedResult(null);
  }

  function scheduleStateRefresh(delayMs: number) {
    if (stateRefreshTimer.current) clearTimeout(stateRefreshTimer.current);
    stateRefreshTimer.current = setTimeout(() => {
      stateRefreshTimer.current = null;
      void refreshState(true);
    }, delayMs);
  }

  function showError(cause: unknown, visible = true) {
    if (!visible && isAbortError(cause)) return;
    if (!visible && error) return;
    const message = cause instanceof Error ? cause.message : String(cause);
    setError(message);
    if (errorTimer.current) clearTimeout(errorTimer.current);
    errorTimer.current = setTimeout(() => setError(null), visible ? 4500 : 2200);
  }

  function clearError() {
    if (errorTimer.current) clearTimeout(errorTimer.current);
    setError(null);
  }

  if (!market) {
    return (
      <SafeAreaView style={styles.root}>
        <StatusBar barStyle="light-content" />
        <View style={styles.loading}>
          <Text style={styles.loadingBrand}>TICK</Text>
          <Text style={styles.loadingText}>{error ?? "Connecting to live markets"}</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" />
      <View style={styles.app}>
        <View style={styles.content}>
          {tab === "trade" ? (
            <TradeScreen
              market={marketForScreen}
              balance={account?.balances.usdc ?? 0}
              leverage={leverage}
              position={livePosition}
              execution={execution}
              submitting={submitting}
              quotes={quotes}
              closedResult={closedResult}
              error={error}
              tapeStale={tapeStale}
              tapeStatus={tapeStatus}
              onOpen={open}
              onClose={close}
              onNext={() => shiftMarket(1)}
              onPrevious={() => shiftMarket(-1)}
            />
          ) : null}
          {tab === "dashboard" ? <Dashboard markets={markets} history={history} onMarket={selectMarket} /> : null}
          {tab === "profile" ? (
            <Profile
              state={account}
              ticketUsd={TICKET_USD}
              leverage={leverage}
              maxLeverage={maxLeverage}
              onLeverage={setLeveragePreset}
            />
          ) : null}
        </View>
        <BottomNav tab={tab} onTab={setTab} />
      </View>
    </SafeAreaView>
  );
}

function quoteMatchesLeverage(quote: TradeQuote, requestedLeverage: number): boolean {
  return (
    quote.leverage === requestedLeverage
    || (quote.leverageNormalized === true && quote.requestedLeverage === requestedLeverage)
  );
}

function isBusy(execution: Execution | null): boolean {
  return execution?.status === "created" || execution?.status === "opening" || execution?.status === "closing" || execution?.status === "unknown";
}

function isLiquidatedResult(result: { status?: string } | null): boolean {
  return result?.status === "liquidated";
}

function realizedGrossPnl(
  result: { position?: Partial<Pick<Position, "pnl" | "grossPnl">> } | null,
  position: Position | null
): number | null {
  const raw = result?.position?.pnl ?? result?.position?.grossPnl ?? position?.pnl ?? position?.grossPnl;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function costDrag(
  netPnl: number | null,
  grossPnl: number | null,
  result: { position?: Partial<Pick<Position, "estimatedAllInCostUsd">> } | null,
  position: Position | null
): number | null {
  if (netPnl !== null && grossPnl !== null) {
    const drag = grossPnl - netPnl;
    return Number.isFinite(drag) ? drag : null;
  }
  const estimate = Number(result?.position?.estimatedAllInCostUsd ?? position?.estimatedAllInCostUsd);
  return Number.isFinite(estimate) ? estimate : null;
}

function isAbortError(cause: unknown): boolean {
  if (!(cause instanceof Error)) return false;
  return cause.name === "AbortError" || cause.message.toLowerCase().includes("aborted");
}
