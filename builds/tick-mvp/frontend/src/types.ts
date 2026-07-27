export type Side = "long" | "short";
export type FeedStatus = "live" | "delayed" | "stale" | "disconnected" | "resyncing";
export type PositionStatus = "opening" | "open" | "closing" | "closed" | "liquidated" | "unknown";

export type MarketObservation = {
  seq: number;
  receivedTs: number;
  price: number;
  unchanged: boolean;
};

export type Market = {
  market: string;
  symbol: string;
  name: string;
  assetClass: string;
  price: number;
  movePct: number;
  activeTapePct: number;
  feeHurdlePct: number;
  activitySurplusPct: number;
  maxLeverage: number;
  suggestedLeverage: number;
  openingAllowed: boolean;
  feedStatus: FeedStatus;
  lastMarketTickAgeMs: number | null;
  score: number;
  observations: MarketObservation[];
  sequence: number;
};

export type User = {
  id: string;
  email: string;
  displayName: string | null;
};

export type Wallet = {
  id: string;
  address: string;
  chainId: number;
};

export type Session = {
  token: string;
  userId: string;
  walletAddress: string | null;
  user: User | null;
  wallet: Wallet | null;
};

export type WalletBalances = {
  chainId: number;
  address: string;
  nativeEth: number | null;
  usdc: number | null;
  gtradeAllowanceUsdc: number | null;
  source: string;
  unavailableReason: string | null;
};

export type Quote = {
  quoteId: string;
  venue: string;
  market: string;
  side: Side;
  ticketUsd: number;
  leverage: number;
  notionalUsd: number;
  maxLossUsd: number | null;
  estimatedOpenCostUsd: number;
  estimatedCloseCostUsd: number;
  estimatedRoundTripCostUsd: number;
  liquidationPrice: number | null;
  stopLossPrice: number | null;
  openingAllowed: boolean;
  createdAt: string;
  expiresAt: string;
};

export type Position = {
  id: string;
  venue: string;
  market: string;
  side: Side;
  status: PositionStatus;
  quoteId: string | null;
  ticketUsd: number;
  leverage: number;
  notionalUsd: number;
  entryPrice: number | null;
  stopLossPrice: number | null;
  liquidationPrice: number | null;
  createdAt: string;
  updatedAt: string;
  openedAt: string | null;
};

export type Intent = {
  id: string;
  action: "open" | "close";
  status: string;
  positionId: string | null;
  market: string;
  createdAt: string;
  updatedAt: string;
};

export type ExecutionAttempt = {
  id: string;
  tradeIntentId: string;
  action: "open" | "close";
  status: string;
  txHash: string | null;
  createdAt: string;
  updatedAt: string;
};

export type Reconciliation = {
  id: string;
  positionId: string;
  status: string;
  venueRealizedPnlUsd: number | null;
  walletDeltaUsd: number | null;
  differenceUsd: number | null;
  createdAt: string;
  updatedAt: string;
};

export type AccountState = {
  user: User | null;
  wallet: Wallet | null;
  positions: Position[];
  intents: Intent[];
  executionAttempts: ExecutionAttempt[];
  reconciliations: Reconciliation[];
};

export type AcceptedTrade = {
  intent: Intent;
  executionAttempt: ExecutionAttempt;
  position: Position | null;
  job: { jobId: string | null; queued: boolean } | null;
};

export type ClosedResult = {
  id: string;
  label: string;
  pnl: number | null;
  market: string;
};

export type TradeSettings = {
  ticketUsd: number;
  leverage: number;
  maxLossUsd: number;
};

export type Theme = {
  accent: string;
  glow: string;
  top: string;
  bottom: string;
};
