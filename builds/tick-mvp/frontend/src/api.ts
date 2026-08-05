import type {
  AcceptedTrade,
  AccountState,
  DemoReset,
  DepositAddress,
  Market,
  MarketBar,
  MarketObservation,
  Quote,
  Session,
  TradingMode,
  VenueMode,
  TradingProfile,
  Side,
  WalletBalances,
  Withdrawal
} from "./types";

const TOKEN_KEY = "tick.session.v2.token";
const SESSION_KEY = "tick.session.v2";
const API_BASE = String(import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function json<T>(path: string, init?: RequestInit, timeoutMs = 10_000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const token = path.startsWith("/api/auth/") ? null : localStorage.getItem(TOKEN_KEY);
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {})
      },
      signal: controller.signal
    });
    const text = await response.text();
    let body: unknown = {};
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        throw new Error(
          response.ok
            ? "TICK received an invalid server response"
            : `TICK backend unavailable (${response.status})`
        );
      }
    }
    if (!response.ok) {
      const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : null;
      throw new ApiError(
        typeof detail === "string" ? detail : `Request failed (${response.status})`,
        response.status
      );
    }
    return normalizeNumbers(body) as T;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") {
      throw new Error("TICK connection timed out");
    }
    throw cause;
  } finally {
    window.clearTimeout(timeout);
  }
}

function normalizeNumbers(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeNumbers);
  if (!value || typeof value !== "object") return value;
  const source = value as Record<string, unknown>;
  const output: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(source)) {
    if (
      typeof item === "string"
      && item.trim() !== ""
      && /^-?\d+(?:\.\d+)?$/.test(item)
      && !key.toLowerCase().includes("id")
      && !key.toLowerCase().includes("hash")
      && !key.toLowerCase().includes("address")
    ) {
      output[key] = Number(item);
    } else {
      output[key] = normalizeNumbers(item);
    }
  }
  return output;
}

function observation(raw: MarketObservation): MarketObservation {
  return {
    seq: Number(raw.seq),
    receivedTs: Number(raw.receivedTs),
    price: Number(raw.price),
    unchanged: Boolean(raw.unchanged)
  };
}

function persistSession(session: Session): Session {
  localStorage.setItem(TOKEN_KEY, session.token);
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function storedSession(): Session | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    const token = localStorage.getItem(TOKEN_KEY);
    if (!raw || !token) return null;
    return { ...JSON.parse(raw), token } as Session;
  } catch {
    clearSession();
    return null;
  }
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(SESSION_KEY);
}

export const api = {
  inviteSession: (accessCode: string) =>
    json<Session>("/api/auth/invite", {
      method: "POST",
      body: JSON.stringify({ accessCode })
    }).then(persistSession),

  me: () => json<{
    user: Session["user"];
    wallet: Session["wallet"];
    tradingProfile: TradingProfile;
  }>("/api/me"),

  switchTradingMode: (mode: TradingMode) =>
    json<TradingProfile>("/api/trading-profile/mode", {
      method: "POST",
      body: JSON.stringify({ mode })
    }),

  switchVenue: (venue: VenueMode) =>
    json<{ venue: VenueMode; wallet: Session["wallet"] }>("/api/venue-mode", {
      method: "POST",
      body: JSON.stringify({ venue })
    }),

  resetDemo: () =>
    json<DemoReset>("/api/trading-profile/demo/reset", {
      method: "POST"
    }),

  state: () => json<AccountState>("/api/state", undefined, 6_000),

  stateEvents: async (
    onStateChange: () => void,
    signal: AbortSignal
  ): Promise<void> => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) throw new ApiError("missing session", 401);
    const response = await fetch(`${API_BASE}/api/events`, {
      headers: { Authorization: `Bearer ${token}` },
      signal
    });
    if (!response.ok || !response.body) {
      throw new ApiError(`Live state unavailable (${response.status})`, response.status);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (frame.includes("event: state")) onStateChange();
      }
    }
  },

  balances: () => json<WalletBalances>("/api/wallet/balances", undefined, 12_000),

  depositAddress: () => json<DepositAddress>("/api/wallet/deposit-address"),

  withdrawals: async () => {
    const response = await json<{ withdrawals: Withdrawal[] }>("/api/wallet/withdrawals");
    return response.withdrawals;
  },

  withdraw: (amount: number, destinationAddress: string, requestKey: string) =>
    json<Withdrawal>("/api/wallet/withdrawals", {
      method: "POST",
      body: JSON.stringify({
        asset: "USDC",
        amount,
        destinationAddress,
        idempotencyKey: requestKey
      })
    }),

  markets: async (
    options: { includeTape?: boolean; limit?: number; venue?: VenueMode } = {}
  ): Promise<Market[]> => {
    const query = new URLSearchParams();
    if (options.includeTape) {
      query.set("includeTape", "true");
      query.set("windowSeconds", "90");
    }
    if (options.limit) query.set("limit", String(options.limit));
    if (options.venue) query.set("venue", options.venue);
    const suffix = query.size ? `?${query.toString()}` : "";
    const response = await json<{
      markets: Array<
        Omit<Market, "observations" | "sequence">
        & { observations?: MarketObservation[]; sequence?: number }
      >;
    }>(`/api/markets${suffix}`);
    return response.markets.map((market) => ({
      ...market,
      price: Number(market.price),
      movePct: Number(market.movePct),
      activeTapePct: Number(market.activeTapePct),
      feeHurdlePct: Number(market.feeHurdlePct ?? 0),
      activitySurplusPct: Number(market.activitySurplusPct ?? 0),
      minPositionSizeUsd: Number(market.minPositionSizeUsd ?? 0),
      minCollateralUsd: Number(market.minCollateralUsd ?? 0),
      minLeverage: Number(market.minLeverage ?? 1),
      maxLeverage: Number(market.maxLeverage),
      suggestedLeverage: Number(market.suggestedLeverage),
      lastMarketTickAgeMs: market.lastMarketTickAgeMs === null
        ? null
        : Number(market.lastMarketTickAgeMs),
      score: Number(market.score),
      observations: (market.observations ?? []).map(observation),
      sequence: Number(market.sequence ?? 0)
    }));
  },

  chart: async (
    market: string,
    windowSeconds = 90
  ): Promise<{
    observations: MarketObservation[];
    bars: MarketBar[];
    sequence: number;
    feedStatus: string;
    requestedWindowSeconds: number;
    actualWindowSeconds: number;
    partial: boolean;
    serverNow: number;
  }> => {
    const response = await json<{
      observations: MarketObservation[];
      bars?: MarketBar[];
      lastSeq: number;
      feedStatus: string;
      requestedWindowSeconds: number;
      actualWindowSeconds: number;
      partial: boolean;
      serverNow: number;
    }>(`/api/chart?market=${encodeURIComponent(market)}&windowSeconds=${windowSeconds}`);
    return {
      observations: response.observations.map(observation),
      bars: (response.bars ?? []).map((bar) => ({
        bucketTs: Number(bar.bucketTs),
        open: Number(bar.open),
        high: Number(bar.high),
        low: Number(bar.low),
        close: Number(bar.close),
        sampleCount: Number(bar.sampleCount),
        firstSeq: Number(bar.firstSeq),
        lastSeq: Number(bar.lastSeq),
        source: bar.source
      })),
      sequence: Number(response.lastSeq),
      feedStatus: response.feedStatus,
      requestedWindowSeconds: Number(response.requestedWindowSeconds),
      actualWindowSeconds: Number(response.actualWindowSeconds),
      partial: Boolean(response.partial),
      serverNow: Number(response.serverNow)
    };
  },

  tape: async (market: string, since: number): Promise<{
    observations: MarketObservation[];
    sequence: number;
    feedStatus: string;
    resyncRequired: boolean;
  }> => {
    const response = await json<{
      observations: MarketObservation[];
      sequence: number;
      feedStatus: string;
      resyncRequired: boolean;
    }>(`/api/tape?market=${encodeURIComponent(market)}&since=${since}`, undefined, 3_000);
    return {
      ...response,
      observations: response.observations.map(observation),
      sequence: Number(response.sequence)
    };
  },

  tapes: async (
    requests: Array<{ market: string; since: number }>
  ): Promise<Array<{
    market: string;
    observations: MarketObservation[];
    sequence: number;
    feedStatus: string;
    resyncRequired: boolean;
  }>> => {
    const query = new URLSearchParams();
    for (const request of requests) {
      query.append("market", request.market);
      query.append("since", String(request.since));
    }
    const response = await json<{
      tapes: Array<{
        market: string;
        observations: MarketObservation[];
        sequence: number;
        feedStatus: string;
        resyncRequired: boolean;
      }>;
    }>(`/api/tapes?${query.toString()}`, undefined, 3_000);
    return response.tapes.map((tape) => ({
      ...tape,
      sequence: Number(tape.sequence),
      observations: tape.observations.map(observation)
    }));
  },

  quote: (
    market: string,
    side: Side,
    ticketUsd: number,
    leverage: number,
    maxLossUsd: number | null,
    takeProfitUsd: number | null
  ) =>
    json<Quote>("/api/trade/quote", {
      method: "POST",
      body: JSON.stringify({ market, side, ticketUsd, leverage, maxLossUsd, takeProfitUsd })
    }),

  open: (quoteId: string, requestKey: string) =>
    json<AcceptedTrade>("/api/trade/open", {
      method: "POST",
      body: JSON.stringify({ quoteId, idempotencyKey: requestKey })
    }),

  close: (positionId: string, requestKey: string) =>
    json<AcceptedTrade>("/api/trade/close", {
      method: "POST",
      body: JSON.stringify({ positionId, idempotencyKey: requestKey })
    })
};

export function idempotencyKey(action: string): string {
  const randomUuid = globalThis.crypto?.randomUUID?.();
  if (randomUuid) return `${action}-${randomUuid}`;

  const entropy = new Uint8Array(12);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(entropy);
  } else {
    for (let index = 0; index < entropy.length; index += 1) {
      entropy[index] = Math.floor(Math.random() * 256);
    }
  }
  const suffix = Array.from(entropy, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${action}-${Date.now().toString(36)}-${suffix}`;
}
