import { API_BASE, API_TOKEN } from "./config";
import type {
  AccountState,
  ChartResponse,
  Execution,
  HistoryResponse,
  MarketsResponse,
  Side,
  TapeResponse,
  TradeQuote
} from "./types";

async function request<T>(path: string, options?: RequestInit, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        "X-Tick-Token": API_TOKEN,
        ...(options?.headers ?? {})
      },
      signal: controller.signal
    });
    const text = await response.text();
    const body = text ? JSON.parse(text) : {};
    if (!response.ok) throw new Error(body.detail || `request failed (${response.status})`);
    return body as T;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  stateStreamUrl: () => `${API_BASE.replace(/^http/, "ws")}/ws/state?token=${encodeURIComponent(API_TOKEN)}`,
  markets: () => request<MarketsResponse>("/api/markets", undefined, 20000),
  state: (force = false) => request<AccountState>(`/api/state${force ? "?force=true" : ""}`, undefined, force ? 20000 : 8000),
  chart: (pair: string) => request<ChartResponse>(`/api/chart?pair=${encodeURIComponent(pair)}&minutes=20`, undefined, 20000),
  tape: (pair: string, since: number) =>
    request<TapeResponse>(`/api/tape?pair=${encodeURIComponent(pair)}&since=${since}`, undefined, 4000),
  quote: (pair: string, side: Side, ticketUsd: number, leverage: number, softStopLossUsd?: number) =>
    request<TradeQuote>(
      "/api/trade/quote",
      { method: "POST", body: JSON.stringify({ pair, side, ticketUsd, leverage, softStopLossUsd }) },
      12000
    ),
  open: (quoteId: string, idempotencyKey: string) =>
    request<Execution>(
      "/api/trade/open",
      { method: "POST", body: JSON.stringify({ quoteId, idempotencyKey }) },
      12000
    ),
  close: (pair: string, idempotencyKey: string) =>
    request<Execution>(
      "/api/trade/close",
      { method: "POST", body: JSON.stringify({ pair, idempotencyKey }) },
      12000
    ),
  approve: (amount?: number) =>
    request<Record<string, unknown>>(
      "/api/approve",
      { method: "POST", body: JSON.stringify(amount === undefined ? {} : { amount }) },
      20000
    ),
  history: () => request<HistoryResponse>("/api/history")
};
