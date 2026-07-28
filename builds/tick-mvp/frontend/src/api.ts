import type {
  AcceptedTrade,
  AccountState,
  DepositAddress,
  Market,
  MarketObservation,
  Quote,
  Session,
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

  me: () => json<{ user: Session["user"]; wallet: Session["wallet"] }>("/api/me"),

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
    options: { includeTape?: boolean; limit?: number } = {}
  ): Promise<Market[]> => {
    const query = new URLSearchParams();
    if (options.includeTape) {
      query.set("includeTape", "true");
      query.set("windowSeconds", "90");
    }
    if (options.limit) query.set("limit", String(options.limit));
    const suffix = query.size ? `?${query.toString()}` : "";
    const response = await json<{
      markets: Array<
        Omit<Market, "observations" | "sequence">
        & { observations?: MarketObservation[]; sequence?: number }
      >;
    }>(`/api/markets${suffix}`);
    return response.markets.map((market) => ({
      ...market,
      minLeverage: Number(market.minLeverage ?? 1),
      observations: (market.observations ?? []).map(observation),
      sequence: Number(market.sequence ?? 0)
    }));
  },

  chart: async (market: string): Promise<{ observations: MarketObservation[]; sequence: number; feedStatus: string }> => {
    const response = await json<{
      observations: MarketObservation[];
      lastSeq: number;
      feedStatus: string;
    }>(`/api/chart?market=${encodeURIComponent(market)}&windowSeconds=90`);
    return {
      observations: response.observations.map(observation),
      sequence: Number(response.lastSeq),
      feedStatus: response.feedStatus
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
