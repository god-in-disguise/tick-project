import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api, idempotencyKey } from "./api";
import type {
  AcceptedTrade,
  AccountState,
  ClosedResult,
  Market,
  MarketBar,
  MarketObservation,
  Position,
  Quote,
  Session,
  Side,
  TradeSettings,
  TradingMode,
  VenueMode,
  WalletBalances
} from "./types";
import { effectiveTicketUsd, minimumTicketUsd, ticketMeetsMarketMinimum } from "./tradeSettings";
import { positionNetPnl } from "./positionPnl";

const SETTINGS_KEY = "tick.trade.settings.v2";
const LEGACY_SETTINGS_KEY = "tick.trade.settings";
const QUOTES_KEY = "tick.trade.quotes";
const ACTIVE_STATUSES = new Set(["opening", "open", "closing", "unknown"]);
const LIVE_TAPE_WINDOW_SECONDS = 90;
const MIN_LIVE_TAPE_COVERAGE_SECONDS = 75;
const MAX_LIVE_TICK_AGE_SECONDS = 1.5;
const MAX_BOOTSTRAP_RETRY_DELAY_MS = 2_000;
const DEFAULT_SETTINGS: TradeSettings = {
  amountMode: "fixed",
  ticketUsd: 10,
  leverage: 500,
  maxLossUsd: 10,
  stopLossEnabled: false,
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
  const initialVenue = initialSession.user?.activeVenue ?? "gtrade";
  const [session] = useState<Session>(initialSession);
  const [state, setState] = useState<AccountState | null>(null);
  const [balances, setBalances] = useState<WalletBalances | null>(null);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [activeMarketId, setActiveMarketId] = useState("");
  const [quotes, setQuotes] = useState<Quotes>({ long: null, short: null });
  const [settings, setSettingsState] = useState<TradeSettings>(
    () => settingsForVenue(readSettings(), initialVenue)
  );
  const [activeVenue, setActiveVenue] = useState<VenueMode>(initialVenue);
  const [busyAction, setBusyAction] = useState<Side | "close" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closedResult, setClosedResult] = useState<ClosedResult | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const sequences = useRef<Record<string, number>>({});
  const chartRequests = useRef(new Map<string, Promise<void>>());
  const tapeHydrationAt = useRef<Record<string, number>>({});
  const tapeBusy = useRef(new Set<string>());
  const stateBusy = useRef(false);
  const actionBusy = useRef(false);
  const quoteCache = useRef<Record<string, Quote>>(readQuotes());
  const shownReconciliations = useRef(new Set<string>());
  const shownExecutionFailures = useRef(new Set<string>());
  const pendingReconciliations = useRef(new Set<string>());
  const stateInitialized = useRef(false);
  const errorTimer = useRef<number | null>(null);
  const resultTimer = useRef<number | null>(null);
  const backgroundFailures = useRef(0);
  const resumeGraceUntil = useRef(Date.now() + 6_000);
  const venueSwitchTarget = useRef<VenueMode | null>(null);

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
    () => routeMarkets(markets, settings.leverage, activeVenue === "flash"),
    [activeVenue, markets, settings.leverage]
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
  const watchedMarketIds = useMemo(() => {
    if (!activeMarket || routedMarkets.length < 2) return activeMarket ? [activeMarket.market] : [];
    const index = routedMarkets.findIndex((market) => market.market === activeMarket.market);
    if (index < 0) return [activeMarket.market];
    return [...new Set([
      activeMarket.market,
      routedMarkets[(index - 1 + routedMarkets.length) % routedMarkets.length]?.market,
      routedMarkets[(index + 1) % routedMarkets.length]?.market
    ].filter((marketId): marketId is string => Boolean(marketId)))];
  }, [activeMarket?.market, routedMarkets.map((market) => market.market).join("|")]);

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

  const markBackgroundSuccess = useCallback(() => {
    backgroundFailures.current = 0;
  }, []);

  const showBackgroundError = useCallback((cause: unknown) => {
    if (
      document.visibilityState !== "visible"
      || Date.now() < resumeGraceUntil.current
    ) {
      return;
    }
    backgroundFailures.current += 1;
    if (backgroundFailures.current < 3) return;
    backgroundFailures.current = 0;
    showError(cause);
  }, [showError]);

  const loadMarketChart = useCallback((marketId: string) => {
    const current = chartRequests.current.get(marketId);
    if (current) return current;
    const request = api.chart(marketId)
      .then((chart) => {
        markBackgroundSuccess();
        sequences.current[marketId] = Math.max(sequences.current[marketId] ?? 0, chart.sequence);
        setMarkets((markets) =>
          updateMarketTape(
            markets,
            marketId,
            chartTapeObservations(chart.bars, chart.observations),
            chart.sequence,
            chart.feedStatus
          )
        );
      })
      .finally(() => {
        chartRequests.current.delete(marketId);
      });
    chartRequests.current.set(marketId, request);
    return request;
  }, [markBackgroundSuccess]);

  const refreshState = useCallback(async () => {
    if (stateBusy.current) return;
    stateBusy.current = true;
    try {
      const next = await api.state();
      markBackgroundSuccess();
      setState(next);
      if (next.user?.activeVenue && venueSwitchTarget.current === null) {
        setActiveVenue(next.user.activeVenue);
      }
      if (
        next.tradingProfile?.mode === "demo"
        && typeof next.tradingProfile.balanceUsd === "number"
      ) {
        setBalances((current) => current ? {
          ...current,
          usdc: next.tradingProfile?.balanceUsd ?? 0,
          spendableUsdc: next.tradingProfile?.balanceUsd ?? 0,
          tradingMode: "demo",
          profileSeason: next.tradingProfile?.season ?? 1,
          source: "demo_ledger"
        } : current);
      }
      setBusyAction(null);
      if (!stateInitialized.current) {
        for (const reconciliation of next.reconciliations) {
          shownReconciliations.current.add(reconciliation.id);
        }
        for (const execution of next.executionAttempts) {
          if (execution.status === "failed") shownExecutionFailures.current.add(execution.id);
        }
        stateInitialized.current = true;
        return;
      }
      const failedExecution = next.executionAttempts.find(
        (execution) =>
          execution.status === "failed"
          && !shownExecutionFailures.current.has(execution.id)
      );
      if (failedExecution) {
        shownExecutionFailures.current.add(failedExecution.id);
        showError(new Error(executionFailureMessage(failedExecution.error)));
      }
      const terminal = next.positions.find(
        (position) => position.status === "closed" || position.status === "liquidated"
      );
      if (terminal) {
        const reconciliation = next.reconciliations.find((item) => item.positionId === terminal.id);
        if (reconciliation && !shownReconciliations.current.has(reconciliation.id)) {
          const pnl = reconciliation.walletDeltaUsd;
          const hasFinalWalletResult = pnl !== null && [
            "wallet_observed",
            "wallet_reconciled",
            "mismatched"
          ].includes(reconciliation.status);
          if (!hasFinalWalletResult) {
            if (!pendingReconciliations.current.has(reconciliation.id)) {
              pendingReconciliations.current.add(reconciliation.id);
              setClosedResult({
                id: reconciliation.id,
                label: terminalLabel(terminal),
                pnl: null,
                market: terminal.market,
                reason: terminal.terminalReason,
                reconciliationStatus: reconciliation.status
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
            reason: terminal.terminalReason,
            reconciliationStatus: reconciliation.status
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
      showBackgroundError(cause);
    } finally {
      stateBusy.current = false;
    }
  }, [markBackgroundSuccess, showBackgroundError, showError]);

  const refreshBalances = useCallback(async () => {
    try {
      setBalances(await api.balances());
      markBackgroundSuccess();
    } catch (cause) {
      showBackgroundError(cause);
    }
  }, [markBackgroundSuccess, showBackgroundError]);

  useEffect(() => {
    let alive = true;
    const bootstrap = async () => {
      let failures = 0;
      while (alive) {
        try {
          const nextMarkets = await api.markets({ includeTape: true, venue: activeVenue });
          if (!alive) return;
          const firstMarket = routeMarkets(
            nextMarkets,
            settings.leverage,
            activeVenue === "flash"
          )[0]?.market;
          if (!firstMarket) throw new Error("No tradeable markets are available");
          markBackgroundSuccess();
          for (const market of nextMarkets) {
            sequences.current[market.market] = market.sequence;
          }
          setMarkets(nextMarkets);
          setActiveMarketId(firstMarket);
          const selected = nextMarkets.find((market) => market.market === firstMarket);
          if (!selected?.observations.length) {
            void loadMarketChart(firstMarket).catch(showBackgroundError);
          }
          await Promise.all([refreshState(), refreshBalances()]);
          setError(null);
          return;
        } catch (cause) {
          failures += 1;
          if (failures >= 4) showError(cause);
          const delay = Math.min(500 * 2 ** (failures - 1), MAX_BOOTSTRAP_RETRY_DELAY_MS);
          await new Promise((resolve) => window.setTimeout(resolve, delay));
        }
      }
    };
    void bootstrap();
    return () => {
      alive = false;
      if (errorTimer.current) window.clearTimeout(errorTimer.current);
      if (resultTimer.current) window.clearTimeout(resultTimer.current);
    };
  }, [
    loadMarketChart,
    markBackgroundSuccess,
    refreshBalances,
    refreshState,
    activeVenue,
    showBackgroundError,
    showError
  ]);

  useEffect(() => {
    const marketTimer = window.setInterval(async () => {
      try {
        const incoming = await api.markets({ venue: activeVenue });
        markBackgroundSuccess();
        setMarkets((current) => mergeMarketSummaries(current, incoming));
      } catch (cause) {
        showBackgroundError(cause);
      }
    }, 5_000);
    const balanceTimer = window.setInterval(refreshBalances, 5_000);
    return () => {
      window.clearInterval(marketTimer);
      window.clearInterval(balanceTimer);
    };
  }, [activeVenue, markBackgroundSuccess, refreshBalances, showBackgroundError]);

  useEffect(() => {
    const controller = new AbortController();
    let reconnectTimer: number | null = null;
    const connect = async () => {
      try {
        await api.stateEvents(refreshState, controller.signal);
      } catch {
        // iOS suspends long-lived streams in the background; polling remains authoritative.
      }
      if (controller.signal.aborted) return;
      void refreshState();
      reconnectTimer = window.setTimeout(connect, 1_000);
    };
    void connect();
    const recoveryTimer = window.setInterval(refreshState, 3_000);
    return () => {
      controller.abort();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      window.clearInterval(recoveryTimer);
    };
  }, [refreshState]);

  useEffect(() => {
    const now = Date.now();
    for (const marketId of watchedMarketIds) {
      const market = markets.find((candidate) => candidate.market === marketId);
      const lastHydration = tapeHydrationAt.current[marketId] ?? 0;
      if (market && tapeNeedsHydration(market) && now - lastHydration >= 15_000) {
        tapeHydrationAt.current[marketId] = now;
        void loadMarketChart(marketId).catch(showBackgroundError);
      }
    }
  }, [watchedMarketIds.join("|"), loadMarketChart, markets, showBackgroundError]);

  useEffect(() => {
    if (!watchedMarketIds.length) return;
    const poll = async () => {
      const requestKey = watchedMarketIds.join("|");
      if (tapeBusy.current.has(requestKey)) return;
      tapeBusy.current.add(requestKey);
      try {
        const results = await api.tapes(
          watchedMarketIds.map((marketId) => ({
            market: marketId,
            since: sequences.current[marketId] ?? 0
          }))
        );
        markBackgroundSuccess();
        const deltas = results.filter((result) => !result.resyncRequired);
        for (const result of deltas) {
          sequences.current[result.market] = Math.max(
            sequences.current[result.market] ?? 0,
            result.sequence
          );
        }
        setMarkets((current) => deltas.reduce(
          (next, result) => updateMarketTape(
            next,
            result.market,
            result.observations,
            result.sequence,
            result.feedStatus
          ),
          current
        ));
        for (const result of results) {
          if (result.resyncRequired) void loadMarketChart(result.market).catch(showBackgroundError);
        }
      } catch (cause) {
        showBackgroundError(cause);
      } finally {
        tapeBusy.current.delete(requestKey);
      }
    };
    void poll();
    const timer = window.setInterval(poll, 250);
    return () => window.clearInterval(timer);
  }, [watchedMarketIds.join("|"), loadMarketChart, markBackgroundSuccess, showBackgroundError]);

  useEffect(() => {
    if (!activeMarket || activePosition) {
      setQuotes({ long: null, short: null });
      return;
    }
    let canceled = false;
    let quoteBlocked = false;
    const refresh = async () => {
      if (quoteBlocked) return;
      if (!ticketMeetsMarketMinimum(settings, activeMarket)) {
        setQuotes({ long: null, short: null });
        return;
      }
      const leverage = Math.min(settings.leverage, activeMarket.maxLeverage);
      const ticketUsd = effectiveTicketUsd(settings, activeMarket);
      const maxLossUsd = settings.stopLossEnabled ? settings.maxLossUsd : null;
      const takeProfitUsd = settings.takeProfitEnabled ? settings.takeProfitUsd : null;
      try {
        const [long, short] = await Promise.all([
          api.quote(activeMarket.market, "long", ticketUsd, leverage, maxLossUsd, takeProfitUsd),
          api.quote(activeMarket.market, "short", ticketUsd, leverage, maxLossUsd, takeProfitUsd)
        ]);
        if (!canceled) {
          markBackgroundSuccess();
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
          showBackgroundError(cause);
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
    markBackgroundSuccess,
    rememberQuote,
    settings.leverage,
    settings.amountMode,
    settings.maxLossUsd,
    settings.stopLossEnabled,
    settings.takeProfitEnabled,
    settings.takeProfitUsd,
    settings.ticketUsd,
    showBackgroundError
  ]);

  useEffect(() => {
    let hidden = document.visibilityState === "hidden";
    const resume = () => {
      if (document.visibilityState === "hidden") {
        hidden = true;
        return;
      }
      if (!hidden) return;
      hidden = false;
      resumeGraceUntil.current = Date.now() + 4_000;
      backgroundFailures.current = 0;
      setError(null);
      void api.markets({ includeTape: true, venue: activeVenue })
        .then((nextMarkets) => {
          for (const market of nextMarkets) {
            sequences.current[market.market] = market.sequence;
          }
          setMarkets(nextMarkets);
          markBackgroundSuccess();
        })
        .catch(showBackgroundError);
      void refreshState();
      void refreshBalances();
    };
    document.addEventListener("visibilitychange", resume);
    return () => document.removeEventListener("visibilitychange", resume);
  }, [activeVenue, markBackgroundSuccess, refreshBalances, refreshState, showBackgroundError]);

  const setSettings = useCallback((next: TradeSettings) => {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
    setSettingsState(next);
  }, []);

  const reloadProfileState = useCallback(async () => {
    stateInitialized.current = false;
    shownReconciliations.current.clear();
    shownExecutionFailures.current.clear();
    pendingReconciliations.current.clear();
    setClosedResult(null);
    setQuotes({ long: null, short: null });
    const [nextState, nextBalances] = await Promise.all([
      api.state(),
      api.balances()
    ]);
    setState(nextState);
    setBalances(nextBalances);
  }, []);

  const switchTradingMode = useCallback(async (mode: TradingMode) => {
    if (profileBusy) return false;
    if (state?.tradingProfile?.mode === mode) return true;
    setProfileBusy(true);
    try {
      await api.switchTradingMode(mode);
      await reloadProfileState();
      return true;
    } catch (cause) {
      showError(cause);
      return false;
    } finally {
      setProfileBusy(false);
    }
  }, [profileBusy, reloadProfileState, showError, state?.tradingProfile?.mode]);

  const switchVenue = useCallback(async (venue: VenueMode) => {
    if (profileBusy) return false;
    if (activeVenue === venue) return true;
    const previousVenue = activeVenue;
    const previousSettings = settings;
    const nextSettings = settingsForVenue(settings, venue);
    venueSwitchTarget.current = venue;
    setActiveVenue(venue);
    if (nextSettings !== settings) setSettings(nextSettings);
    setProfileBusy(true);
    try {
      const [, nextMarkets] = await Promise.all([
        api.switchVenue(venue),
        api.markets({ venue })
      ]);
      const firstMarket = routeMarkets(
        nextMarkets,
        nextSettings.leverage,
        venue === "flash"
      )[0]?.market;
      if (!firstMarket) throw new Error(`No ${venue} markets are available`);
      sequences.current = {};
      for (const market of nextMarkets) sequences.current[market.market] = market.sequence;
      setMarkets(nextMarkets);
      setActiveMarketId(firstMarket);
      void loadMarketChart(firstMarket).catch(showBackgroundError);
      void reloadProfileState()
        .catch(showBackgroundError)
        .finally(() => {
          if (venueSwitchTarget.current === venue) venueSwitchTarget.current = null;
        });
      return true;
    } catch (cause) {
      venueSwitchTarget.current = null;
      setActiveVenue(previousVenue);
      if (nextSettings !== previousSettings) setSettings(previousSettings);
      showError(cause);
      return false;
    } finally {
      setProfileBusy(false);
    }
  }, [
    activeVenue,
    loadMarketChart,
    profileBusy,
    reloadProfileState,
    setSettings,
    settings,
    showBackgroundError,
    showError
  ]);

  const resetDemo = useCallback(async () => {
    if (profileBusy) return;
    setProfileBusy(true);
    try {
      await api.resetDemo();
      await reloadProfileState();
    } catch (cause) {
      showError(cause);
    } finally {
      setProfileBusy(false);
    }
  }, [profileBusy, reloadProfileState, showError]);

  const open = useCallback(async (side: Side) => {
    if (!activeMarket || activePosition || actionBusy.current) return;
    const ticketUsd = effectiveTicketUsd(settings, activeMarket);
    if (!ticketMeetsMarketMinimum(settings, activeMarket)) {
      showError(new Error(
        `${activeMarket.symbol} needs at least $${minimumTicketUsd(activeMarket, settings.leverage).toFixed(2)}. Choose MIN or CUSTOM in your preset.`
      ));
      return;
    }
    const spendableUsdc = balances?.spendableUsdc ?? balances?.usdc;
    if (spendableUsdc !== null && spendableUsdc !== undefined && spendableUsdc < ticketUsd) {
      showError(new Error(
        state?.tradingProfile?.mode === "demo"
          ? "Demo balance is too low. Reset the season in Me."
          : "Insufficient spendable USDC"
      ));
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
        !quoteMatchesSettings(quote, ticketUsd, leverage, maxLossUsd, takeProfitUsd)
      ) {
        quote = await api.quote(
          activeMarket.market,
          side,
          ticketUsd,
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
  }, [
    activeMarket,
    activePosition,
    balances?.spendableUsdc,
    balances?.usdc,
    quotes,
    refreshState,
    rememberQuote,
    settings,
    activeVenue,
    state?.tradingProfile?.mode,
    showError
  ]);

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

    if (tapeNeedsHydration(target)) {
      void loadMarketChart(target.market).catch(showBackgroundError);
    }
  }, [activePosition, busy, loadMarketChart, routedMarkets, showBackgroundError]);

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
    activeVenue,
    setSettings,
    estimatedNetPnl,
    busy,
    busyAction,
    error,
    closedResult,
    profileBusy,
    refreshBalances,
    switchTradingMode,
    switchVenue,
    resetDemo,
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
    const cutoff = Date.now() / 1000 - (LIVE_TAPE_WINDOW_SECONDS + 5);
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

function tapeNeedsHydration(market: Market, now = Date.now() / 1_000): boolean {
  const first = market.observations[0];
  const latest = market.observations.at(-1);
  if (!first || !latest) return true;
  const coverageSeconds = Math.max(0, latest.receivedTs - first.receivedTs);
  return (
    now - latest.receivedTs > MAX_LIVE_TICK_AGE_SECONDS
    || coverageSeconds < MIN_LIVE_TAPE_COVERAGE_SECONDS
  );
}

function chartTapeObservations(
  bars: MarketBar[],
  observations: MarketObservation[]
): MarketObservation[] {
  const bySequence = new Map<number, MarketObservation>();
  for (const bar of bars) {
    bySequence.set(bar.lastSeq, {
      seq: bar.lastSeq,
      receivedTs: bar.bucketTs,
      price: bar.close,
      unchanged: bar.open === bar.close && bar.high === bar.low
    });
  }
  for (const observation of observations) bySequence.set(observation.seq, observation);
  return [...bySequence.values()].sort(
    (left, right) => left.receivedTs - right.receivedTs || left.seq - right.seq
  );
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

function routeMarkets(
  markets: Market[],
  desiredLeverage: number,
  executableOnly = false
): Market[] {
  const bySymbol = new Map<string, Market[]>();
  for (const market of markets) {
    const group = bySymbol.get(market.symbol) ?? [];
    group.push(market);
    bySymbol.set(market.symbol, group);
  }
  return [...bySymbol.values()]
    .map((routes) => {
      const leverageEligible = routes.filter(
        (route) =>
          desiredLeverage >= (route.minLeverage ?? 1)
          && desiredLeverage <= route.maxLeverage
      );
      const executable = leverageEligible.filter((route) => route.openingAllowed);
      const eligible = executable.length || executableOnly ? executable : leverageEligible;
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

function settingsForVenue(settings: TradeSettings, venue: VenueMode): TradeSettings {
  if (venue !== "flash") return settings;
  const leverage = settings.leverage >= 500 ? 500 : 100;
  if (
    settings.leverage === leverage
    && !settings.stopLossEnabled
    && !settings.takeProfitEnabled
  ) {
    return settings;
  }
  return {
    ...settings,
    leverage,
    stopLossEnabled: false,
    takeProfitEnabled: false
  };
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
    const current = localStorage.getItem(SETTINGS_KEY);
    if (current) return { ...DEFAULT_SETTINGS, ...JSON.parse(current) };

    const legacy = JSON.parse(localStorage.getItem(LEGACY_SETTINGS_KEY) ?? "{}");
    const migrated = {
      ...DEFAULT_SETTINGS,
      ...legacy,
      stopLossEnabled: false
    };
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(migrated));
    return migrated;
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

function executionFailureMessage(error: string | null): string {
  const detail = error?.toLowerCase() ?? "";
  if (detail.includes("delegat") || detail.includes("allowance") || detail.includes("wallet")) {
    return "Wallet setup did not complete. No position was opened.";
  }
  if (detail.includes("revert")) {
    return "The venue rejected the open. No position was created.";
  }
  return "The trade did not open. No position was created.";
}

function readQuotes(): Record<string, Quote> {
  try {
    return JSON.parse(localStorage.getItem(QUOTES_KEY) ?? "{}");
  } catch {
    return {};
  }
}
