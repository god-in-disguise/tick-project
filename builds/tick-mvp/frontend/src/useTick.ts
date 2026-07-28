import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api, idempotencyKey } from "./api";
import type {
  AcceptedTrade,
  AccountState,
  ClosedResult,
  Market,
  MarketObservation,
  Position,
  Quote,
  Session,
  Side,
  TradeSettings,
  WalletBalances
} from "./types";

const SETTINGS_KEY = "tick.trade.settings";
const QUOTES_KEY = "tick.trade.quotes";
const ACTIVE_STATUSES = new Set(["opening", "open", "closing", "unknown"]);
const DEFAULT_SETTINGS: TradeSettings = {
  ticketUsd: 10,
  leverage: 500,
  maxLossUsd: 10,
  stopLossEnabled: true,
  takeProfitUsd: 10,
  takeProfitEnabled: false
};

type Quotes = { long: Quote | null; short: Quote | null };

function terminalLabel(position: Position, pnl: number | null = null): string {
  if (position.terminalReason === "liquidation") return "Liquidated";
  if (position.terminalReason === "stop_loss") return "Stopped";
  if (position.terminalReason === "take_profit") return "Target hit";
  if (pnl === null) return "Closed";
  return pnl >= 0 ? "Net profit" : "Net loss";
}

export function useTick(initialSession: Session) {
  const [session] = useState<Session>(initialSession);
  const [state, setState] = useState<AccountState | null>(null);
  const [balances, setBalances] = useState<WalletBalances | null>(null);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [activeMarketId, setActiveMarketId] = useState("");
  const [quotes, setQuotes] = useState<Quotes>({ long: null, short: null });
  const [settings, setSettingsState] = useState<TradeSettings>(readSettings);
  const [busyAction, setBusyAction] = useState<Side | "close" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closedResult, setClosedResult] = useState<ClosedResult | null>(null);
  const sequences = useRef<Record<string, number>>({});
  const chartRequests = useRef(new Map<string, Promise<void>>());
  const tapeBusy = useRef(new Set<string>());
  const stateBusy = useRef(false);
  const actionBusy = useRef(false);
  const quoteCache = useRef<Record<string, Quote>>(readQuotes());
  const shownReconciliations = useRef(new Set<string>());
  const pendingReconciliations = useRef(new Set<string>());
  const stateInitialized = useRef(false);
  const errorTimer = useRef<number | null>(null);
  const resultTimer = useRef<number | null>(null);

  const rememberQuote = useCallback((quote: Quote) => {
    quoteCache.current[quote.quoteId] = quote;
    const recent = Object.fromEntries(Object.entries(quoteCache.current).slice(-20));
    localStorage.setItem(QUOTES_KEY, JSON.stringify(recent));
  }, []);

  const activePosition = useMemo(
    () => state?.positions.find((position) => ACTIVE_STATUSES.has(position.status)) ?? null,
    [state]
  );
  const routedMarkets = useMemo(
    () => routeMarkets(markets, settings.leverage),
    [markets, settings.leverage]
  );

  const activeMarket = useMemo(
    () => {
      if (activePosition) {
        return markets.find((market) => market.market === activePosition.market) ?? null;
      }
      if (!activeMarketId) return null;
      const exact = routedMarkets.find((market) => market.market === activeMarketId);
      if (exact) return exact;
      const previous = markets.find((market) => market.market === activeMarketId);
      return routedMarkets.find((market) => market.symbol === previous?.symbol) ?? routedMarkets[0] ?? null;
    },
    [activeMarketId, activePosition, markets, routedMarkets]
  );

  const activeQuote = activePosition?.quoteId ? quoteCache.current[activePosition.quoteId] ?? null : null;
  const estimatedNetPnl = useMemo(
    () => positionNetPnl(activePosition, activeMarket, activeQuote),
    [activeMarket?.price, activePosition, activeQuote]
  );
  const busy = Boolean(
    busyAction
    || activePosition?.status === "opening"
    || activePosition?.status === "closing"
  );

  const showError = useCallback((cause: unknown) => {
    const message = cause instanceof Error ? cause.message : String(cause);
    setError(message);
    if (errorTimer.current) window.clearTimeout(errorTimer.current);
    errorTimer.current = window.setTimeout(() => setError(null), 4_000);
  }, []);

  const loadMarketChart = useCallback((marketId: string) => {
    const current = chartRequests.current.get(marketId);
    if (current) return current;
    const request = api.chart(marketId)
      .then((chart) => {
        sequences.current[marketId] = Math.max(sequences.current[marketId] ?? 0, chart.sequence);
        setMarkets((markets) =>
          markets.map((market) =>
            market.market === marketId
              && chart.sequence >= market.sequence
              ? {
                  ...market,
                  price: chart.observations.at(-1)?.price ?? market.price,
                  observations: chart.observations,
                  sequence: chart.sequence,
                  feedStatus: chart.feedStatus as Market["feedStatus"]
                }
              : market
          )
        );
      })
      .finally(() => {
        chartRequests.current.delete(marketId);
      });
    chartRequests.current.set(marketId, request);
    return request;
  }, []);

  const refreshState = useCallback(async () => {
    if (stateBusy.current) return;
    stateBusy.current = true;
    try {
      const next = await api.state();
      setState(next);
      setBusyAction(null);
      if (!stateInitialized.current) {
        for (const reconciliation of next.reconciliations) {
          shownReconciliations.current.add(reconciliation.id);
        }
        stateInitialized.current = true;
        return;
      }
      const terminal = next.positions.find(
        (position) => position.status === "closed" || position.status === "liquidated"
      );
      if (terminal) {
        const reconciliation = next.reconciliations.find((item) => item.positionId === terminal.id);
        if (reconciliation && !shownReconciliations.current.has(reconciliation.id)) {
          const pnl = reconciliation.walletDeltaUsd;
          if (pnl === null || reconciliation.status !== "wallet_reconciled") {
            if (!pendingReconciliations.current.has(reconciliation.id)) {
              pendingReconciliations.current.add(reconciliation.id);
              setClosedResult({
                id: reconciliation.id,
                label: terminalLabel(terminal),
                pnl: null,
                market: terminal.market,
                reason: terminal.terminalReason
              });
            }
            return;
          }
          pendingReconciliations.current.delete(reconciliation.id);
          shownReconciliations.current.add(reconciliation.id);
          setClosedResult({
            id: reconciliation.id,
            label: terminalLabel(terminal, pnl),
            pnl,
            market: terminal.market,
            reason: terminal.terminalReason
          });
          if (resultTimer.current) window.clearTimeout(resultTimer.current);
          resultTimer.current = window.setTimeout(
            () => setClosedResult((current) => current?.id === reconciliation.id ? null : current),
            terminal.terminalReason === "liquidation" ? 4_600 : 3_800
          );
          void refreshBalances();
        }
      }
    } catch (cause) {
      showError(cause);
    } finally {
      stateBusy.current = false;
    }
  }, [showError]);

  const refreshBalances = useCallback(async () => {
    try {
      setBalances(await api.balances());
    } catch (cause) {
      showError(cause);
    }
  }, [showError]);

  useEffect(() => {
    let alive = true;
    const bootstrap = async () => {
      try {
        const nextMarkets = await api.markets({ includeTape: true });
        if (!alive) return;
        for (const market of nextMarkets) {
          sequences.current[market.market] = market.sequence;
        }
        setMarkets(nextMarkets);
        const firstMarket = routeMarkets(nextMarkets, settings.leverage)[0]?.market;
        if (firstMarket) {
          setActiveMarketId(firstMarket);
          const selected = nextMarkets.find((market) => market.market === firstMarket);
          if (!selected?.observations.length) {
            void loadMarketChart(firstMarket).catch(showError);
          }
        }
        await Promise.all([refreshState(), refreshBalances()]);
      } catch (cause) {
        showError(cause);
      }
    };
    void bootstrap();
    return () => {
      alive = false;
      if (errorTimer.current) window.clearTimeout(errorTimer.current);
      if (resultTimer.current) window.clearTimeout(resultTimer.current);
    };
  }, [loadMarketChart, refreshBalances, refreshState, showError]);

  useEffect(() => {
    const marketTimer = window.setInterval(async () => {
      try {
        const incoming = await api.markets();
        setMarkets((current) => mergeMarketSummaries(current, incoming));
      } catch (cause) {
        showError(cause);
      }
    }, 5_000);
    const balanceTimer = window.setInterval(refreshBalances, 5_000);
    return () => {
      window.clearInterval(marketTimer);
      window.clearInterval(balanceTimer);
    };
  }, [refreshBalances, refreshState, showError]);

  useEffect(() => {
    const controller = new AbortController();
    let reconnectTimer: number | null = null;
    const connect = () => {
      api.stateEvents(refreshState, controller.signal).catch((cause) => {
        if (controller.signal.aborted) return;
        showError(cause);
        reconnectTimer = window.setTimeout(connect, 1_000);
      });
    };
    connect();
    const recoveryTimer = window.setInterval(refreshState, 3_000);
    return () => {
      controller.abort();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      window.clearInterval(recoveryTimer);
    };
  }, [refreshState, showError]);

  useEffect(() => {
    if (!activeMarket || activeMarket.observations.length) return;
    void loadMarketChart(activeMarket.market).catch(showError);
  }, [activeMarket?.market, activeMarket?.observations.length, loadMarketChart, showError]);

  useEffect(() => {
    if (!activeMarket || routedMarkets.length < 2) return;
    const index = routedMarkets.findIndex((market) => market.market === activeMarket.market);
    if (index < 0) return;
    const neighborIds = new Set<string>();
    const previous = routedMarkets[(index - 1 + routedMarkets.length) % routedMarkets.length];
    const next = routedMarkets[(index + 1) % routedMarkets.length];
    if (previous) neighborIds.add(previous.market);
    if (next) neighborIds.add(next.market);

    const warmNeighbors = () => {
      const cutoff = Date.now() / 1_000 - 2.5;
      for (const marketId of neighborIds) {
        const market = routedMarkets.find((candidate) => candidate.market === marketId);
        if (!market || (market.observations.at(-1)?.receivedTs ?? 0) >= cutoff) continue;
        void loadMarketChart(market.market).catch(showError);
      }
    };
    warmNeighbors();
    const timer = window.setInterval(warmNeighbors, 2_500);
    return () => window.clearInterval(timer);
  }, [activeMarket?.market, loadMarketChart, showError]);

  useEffect(() => {
    if (!activeMarket) return;
    const marketId = activeMarket.market;
    const poll = async () => {
      if (tapeBusy.current.has(marketId)) return;
      tapeBusy.current.add(marketId);
      try {
        const result = await api.tape(marketId, sequences.current[marketId] ?? 0);
        if (result.resyncRequired) {
          const chart = await api.chart(marketId);
          sequences.current[marketId] = chart.sequence;
          setMarkets((current) =>
            updateMarketTape(current, marketId, chart.observations, chart.sequence, chart.feedStatus)
          );
        } else {
          sequences.current[marketId] = Math.max(sequences.current[marketId] ?? 0, result.sequence);
          setMarkets((current) =>
            updateMarketTape(current, marketId, result.observations, result.sequence, result.feedStatus)
          );
        }
      } catch (cause) {
        showError(cause);
      } finally {
        tapeBusy.current.delete(marketId);
      }
    };
    void poll();
    const timer = window.setInterval(poll, 200);
    return () => window.clearInterval(timer);
  }, [activeMarket?.market, showError]);

  useEffect(() => {
    if (!activeMarket || activePosition) {
      setQuotes({ long: null, short: null });
      return;
    }
    let canceled = false;
    let quoteBlocked = false;
    const refresh = async () => {
      if (quoteBlocked) return;
      const leverage = Math.min(settings.leverage, activeMarket.maxLeverage);
      const maxLossUsd = settings.stopLossEnabled ? settings.maxLossUsd : null;
      const takeProfitUsd = settings.takeProfitEnabled ? settings.takeProfitUsd : null;
      try {
        const [long, short] = await Promise.all([
          api.quote(activeMarket.market, "long", settings.ticketUsd, leverage, maxLossUsd, takeProfitUsd),
          api.quote(activeMarket.market, "short", settings.ticketUsd, leverage, maxLossUsd, takeProfitUsd)
        ]);
        if (!canceled) {
          rememberQuote(long);
          rememberQuote(short);
          setQuotes({ long, short });
        }
      } catch (cause) {
        if (!canceled) {
          if (cause instanceof ApiError && cause.status === 422) {
            quoteBlocked = true;
            setQuotes({ long: null, short: null });
          }
          showError(cause);
        }
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 3_500);
    return () => {
      canceled = true;
      window.clearInterval(timer);
    };
  }, [
    activeMarket?.market,
    activePosition?.id,
    rememberQuote,
    settings.leverage,
    settings.maxLossUsd,
    settings.stopLossEnabled,
    settings.takeProfitEnabled,
    settings.takeProfitUsd,
    settings.ticketUsd,
    showError
  ]);

  const setSettings = useCallback((next: TradeSettings) => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
    setSettingsState(next);
  }, []);

  const open = useCallback(async (side: Side) => {
    if (!activeMarket || activePosition || actionBusy.current) return;
    if (balances?.usdc !== null && balances?.usdc !== undefined && balances.usdc < settings.ticketUsd) {
      showError(new Error("Insufficient spendable USDC"));
      return;
    }
    actionBusy.current = true;
    setClosedResult(null);
    setBusyAction(side);
    try {
      let quote = side === "long" ? quotes.long : quotes.short;
      const leverage = Math.min(settings.leverage, activeMarket.maxLeverage);
      const maxLossUsd = settings.stopLossEnabled ? settings.maxLossUsd : null;
      const takeProfitUsd = settings.takeProfitEnabled ? settings.takeProfitUsd : null;
      if (
        !quote ||
        new Date(quote.expiresAt).getTime() < Date.now() + 650 ||
        !quoteMatchesSettings(quote, settings.ticketUsd, leverage, maxLossUsd, takeProfitUsd)
      ) {
        quote = await api.quote(
          activeMarket.market,
          side,
          settings.ticketUsd,
          leverage,
          maxLossUsd,
          takeProfitUsd
        );
        rememberQuote(quote);
      }
      if (!quote.openingAllowed) throw new Error("This market is not accepting opens");
      const accepted = await api.open(quote.quoteId, idempotencyKey("open"));
      applyAccepted(accepted, setState);
      void refreshState();
    } catch (cause) {
      setBusyAction(null);
      showError(cause);
      void refreshState();
    } finally {
      actionBusy.current = false;
    }
  }, [activeMarket, activePosition, balances?.usdc, quotes, refreshState, rememberQuote, settings, showError]);

  const close = useCallback(async () => {
    if (!activePosition || actionBusy.current) return;
    actionBusy.current = true;
    setBusyAction("close");
    try {
      const accepted = await api.close(activePosition.id, idempotencyKey("close"));
      applyAccepted(accepted, setState);
      void refreshState();
    } catch (cause) {
      setBusyAction(null);
      showError(cause);
      void refreshState();
    } finally {
      actionBusy.current = false;
    }
  }, [activePosition, refreshState, showError]);

  const selectMarket = useCallback((marketId: string) => {
    if (activePosition || busy) return;
    const target = routedMarkets.find((market) => market.market === marketId);
    if (!target) return;
    setClosedResult(null);
    setActiveMarketId(target.market);

    const latest = target.observations.at(-1);
    if (!latest || latest.receivedTs < Date.now() / 1_000 - 1.5) {
      void loadMarketChart(target.market).catch(showError);
    }
  }, [activePosition, busy, loadMarketChart, routedMarkets, showError]);

  const shiftMarket = useCallback((offset: number) => {
    if (!activeMarket || activePosition || busy) return;
    const index = routedMarkets.findIndex((market) => market.market === activeMarket.market);
    const next = routedMarkets[
      (index + offset + routedMarkets.length) % routedMarkets.length
    ];
    if (next) selectMarket(next.market);
  }, [activeMarket, activePosition, busy, routedMarkets, selectMarket]);

  return {
    session,
    state,
    balances,
    markets: routedMarkets,
    activeMarket,
    activePosition,
    activeQuote,
    quotes,
    settings,
    setSettings,
    estimatedNetPnl,
    busy,
    busyAction,
    error,
    closedResult,
    refreshBalances,
    open,
    close,
    shiftMarket,
    selectMarket
  };
}

function updateMarketTape(
  markets: Market[],
  marketId: string,
  observations: MarketObservation[],
  sequence: number,
  feedStatus: string
): Market[] {
  if (!observations.length && !feedStatus) return markets;
  return markets.map((market) => {
    if (market.market !== marketId) return market;
    const bySequence = new Map(market.observations.map((point) => [point.seq, point]));
    for (const point of observations) bySequence.set(point.seq, point);
    const cutoff = Date.now() / 1000 - 95;
    const merged = [...bySequence.values()]
      .filter((point) => point.receivedTs >= cutoff)
      .sort((left, right) => left.receivedTs - right.receivedTs || left.seq - right.seq);
    const latest = merged.at(-1);
    return {
      ...market,
      price: latest?.price ?? market.price,
      observations: merged,
      sequence: Math.max(market.sequence, sequence),
      feedStatus: feedStatus as Market["feedStatus"]
    };
  });
}

function mergeMarketSummaries(current: Market[], incoming: Market[]): Market[] {
  if (!current.length) return incoming;
  const updates = new Map(incoming.map((market) => [market.market, market]));
  const stable = current.map((market) => {
    const next = updates.get(market.market);
    return next ? { ...market, ...next, observations: market.observations, sequence: market.sequence } : market;
  });
  for (const market of incoming) {
    if (!stable.some((item) => item.market === market.market)) stable.push(market);
  }
  return stable;
}

function routeMarkets(markets: Market[], desiredLeverage: number): Market[] {
  const bySymbol = new Map<string, Market[]>();
  for (const market of markets) {
    const group = bySymbol.get(market.symbol) ?? [];
    group.push(market);
    bySymbol.set(market.symbol, group);
  }
  return [...bySymbol.values()]
    .map((routes) => {
      const eligible = routes.filter(
        (route) =>
          desiredLeverage >= (route.minLeverage ?? 1)
          && desiredLeverage <= route.maxLeverage
      );
      return [...eligible].sort((left, right) => {
        if (left.feeHurdlePct !== right.feeHurdlePct) {
          return left.feeHurdlePct - right.feeHurdlePct;
        }
        return right.score - left.score;
      })[0] ?? null;
    })
    .filter((market): market is Market => Boolean(market))
    .sort((left, right) => right.score - left.score);
}

function positionNetPnl(position: Position | null, market: Market | null, quote: Quote | null): number | null {
  if (!position?.entryPrice || !market || position.market !== market.market) return null;
  const estimatedCost = quote?.estimatedRoundTripCostUsd ?? 0;
  const latestObservation = market.observations.at(-1);
  const positionConfirmedAt = Date.parse(position.openedAt ?? position.updatedAt) / 1_000;
  if (!latestObservation || latestObservation.receivedTs < positionConfirmedAt) {
    return -estimatedCost;
  }
  const direction = position.side === "long" ? 1 : -1;
  const gross = ((market.price - position.entryPrice) / position.entryPrice) * position.notionalUsd * direction;
  return gross - estimatedCost;
}

function applyAccepted(
  accepted: AcceptedTrade,
  setState: React.Dispatch<React.SetStateAction<AccountState | null>>
) {
  setState((current) => {
    if (!current) return current;
    const positions = accepted.position
      ? [accepted.position, ...current.positions.filter((item) => item.id !== accepted.position?.id)]
      : current.positions;
    return {
      ...current,
      positions,
      intents: [accepted.intent, ...current.intents.filter((item) => item.id !== accepted.intent.id)],
      executionAttempts: [
        accepted.executionAttempt,
        ...current.executionAttempts.filter((item) => item.id !== accepted.executionAttempt.id)
      ]
    };
  });
}

function readSettings(): TradeSettings {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? "{}") };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function quoteMatchesSettings(
  quote: Quote,
  ticketUsd: number,
  leverage: number,
  maxLossUsd: number | null,
  takeProfitUsd: number | null
): boolean {
  return (
    Number(quote.ticketUsd) === ticketUsd &&
    Number(quote.leverage) === leverage &&
    nullableNumber(quote.maxLossUsd) === maxLossUsd &&
    nullableNumber(quote.takeProfitUsd) === takeProfitUsd
  );
}

function nullableNumber(value: number | null): number | null {
  return value === null ? null : Number(value);
}

function readQuotes(): Record<string, Quote> {
  try {
    return JSON.parse(localStorage.getItem(QUOTES_KEY) ?? "{}");
  } catch {
    return {};
  }
}
