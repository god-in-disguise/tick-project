export type Direction = "up" | "down";
export type Side = "long" | "short";
export type Tab = "dashboard" | "trade" | "profile";
export type AssetClass = "CRYPTO" | "STOCK" | "INDEX" | "COMMODITY" | "FX";

export type Theme = {
  accent: string;
  glow: string;
  top: string;
  bottom: string;
};

export type MarketSummary = {
  pair: string;
  symbol: string;
  name: string;
  assetClass: AssetClass;
  feedLabel: string;
  price: number;
  move: number;
  activeTapePct: number;
  feeHurdlePct: number;
  activitySurplusPct: number;
  tradability: number;
  score: number;
  cooling: boolean;
  maxLeverage: number;
  suggestedLeverage: number;
  open: boolean;
  points: number[];
};

export type Market = MarketSummary & {
  points: number[];
  sequence: number;
  theme: Theme;
};

export type Position = {
  pair: string;
  pairId: number | null;
  idx: number | null;
  side: Side;
  entry: number;
  mark: number;
  collateral: number;
  leverage: number;
  pnl: number;
  grossPnl: number;
  estimatedNetPnl: number;
  estimatedOpenCostUsd: number;
  estimatedCloseCostUsd: number;
  estimatedAllInCostUsd: number;
  ticketUsd: number;
  estimatedLiquidationPrice: number | null;
  pnlEstimated: boolean;
  roePct: number;
  openedAt: number;
  optimistic?: boolean;
  closeAvailable?: boolean;
};

export type ExecutionStatus = "created" | "opening" | "open" | "closing" | "closed" | "failed" | "unknown";

export type Execution = {
  id: string;
  idempotencyKey: string;
  action: "open" | "close";
  venue: string;
  pair: string;
  side: Side | null;
  quoteId: string | null;
  ticketUsd: number | null;
  leverage: number | null;
  status: ExecutionStatus;
  balanceBefore: number | null;
  balanceAfter: number | null;
  txHash: string | null;
  realizedWalletDelta: number | null;
  position: Position | null;
  result: Record<string, unknown> | null;
  error: string | null;
  createdAt: number;
  updatedAt: number;
};

export type AccountState = {
  venue: string;
  address: string;
  balances: {
    eth?: number;
    usdc?: number;
    allowance?: number | string;
  };
  positions: Position[];
  execution: Execution | null;
  lastExecution: Execution | null;
  localTestOverrideEnabled: boolean;
  accountUpdatedAt: number | null;
};

export type TradeQuote = {
  quoteId: string;
  venue: string;
  pair: string;
  side: Side;
  ticketUsd: number;
  leverage: number;
  requestedLeverage?: number;
  leverageNormalized?: boolean;
  notionalUsd: number;
  activeCollateralUsd: number;
  collateralAtRiskUsd: number;
  price: number;
  estimatedOpenCostUsd: number;
  estimatedAllInCostUsd: number;
  estimatedLiquidationPrice: number | null;
  feeHurdlePct: number;
  slippageBps: number;
  expiresAt: number;
  marketOpen: boolean;
  openingAllowed: boolean;
  marketTradeable: boolean;
  localTestOverride: boolean;
  activitySurplusPct: number;
  tradability: number;
  marketState: string;
};

export type TapeTick = {
  sequence: number;
  time: number;
  mid: number;
  bid: number;
  ask: number;
  open: boolean;
  unchanged?: boolean;
};

export type TapeResponse = {
  pair: string;
  sequence: number;
  ticks: TapeTick[];
  latest: TapeTick | null;
  stale: boolean;
  error: string | null;
};

export type ChartResponse = {
  pair: string;
  points: number[];
  ticks: TapeTick[];
};

export type MarketsResponse = {
  timestamp: number;
  markets: MarketSummary[];
  stale: boolean;
};

export type HistoryResponse = {
  trades: Execution[];
};

export type Quotes = {
  long: TradeQuote | null;
  short: TradeQuote | null;
};
