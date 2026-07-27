import type {
  AcceptedTrade,
  AccountState,
  Market,
  MarketObservation,
  Quote,
  Session,
  Side,
  WalletBalances
} from "./types";

const TOKEN_KEY = "tick.session.token";
const DEV_USER = "funded-dev";

let sessionPromise: Promise<Session> | null = null;

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
    const token = path.startsWith("/api/auth/") ? null : await sessionToken();
    const response = await fetch(path, {
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

async function sessionToken(): Promise<string> {
  const current = localStorage.getItem(TOKEN_KEY);
  if (current) return current;
  return (await ensureSession()).token;
}

async function ensureSession(): Promise<Session> {
  if (!sessionPromise) {
    sessionPromise = json<Session>(
      "/api/auth/dev-session",
      { method: "POST", body: JSON.stringify({ userId: DEV_USER }) }
    ).then((session) => {
      localStorage.setItem(TOKEN_KEY, session.token);
      return session;
    });
  }
  return sessionPromise;
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

export const api = {
  session: ensureSession,

  state: () => json<AccountState>("/api/state", undefined, 6_000),

  balances: () => json<WalletBalances>("/api/wallet/balances", undefined, 12_000),

  markets: async (): Promise<Market[]> => {
    const response = await json<{ markets: Omit<Market, "observations" | "sequence">[] }>("/api/markets");
    return response.markets.map((market) => ({ ...market, observations: [], sequence: 0 }));
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

  open: (quoteId: string, idempotencyKey: string) =>
    json<AcceptedTrade>("/api/trade/open", {
      method: "POST",
      body: JSON.stringify({ quoteId, idempotencyKey })
    }),

  close: (positionId: string, idempotencyKey: string) =>
    json<AcceptedTrade>("/api/trade/close", {
      method: "POST",
      body: JSON.stringify({ positionId, idempotencyKey })
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
