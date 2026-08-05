export type Side = "long" | "short";
export type FeedStatus = "live" | "delayed" | "stale" | "disconnected" | "resyncing";
export type PositionStatus = "opening" | "open" | "closing" | "closed" | "liquidated" | "unknown";
export type TradingMode = "live" | "demo";
export type VenueMode = "gtrade" | "flash";

export type MarketObservation = {
  seq: number;
  receivedTs: number;
  price: number;
  unchanged: boolean;
};

export type MarketBar = {
  bucketTs: number;
  open: number;
  high: number;
  low: number;
  close: number;
  sampleCount: number;
  firstSeq: number;
  lastSeq: number;
  source: string;
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
  minPositionSizeUsd: number;
  minCollateralUsd?: number;
  minLeverage: number;
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
  activeVenue: VenueMode;
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
  onchainUsdc: number | null;
  gasChargesUsdc: number;
  spendableUsdc: number | null;
  gtradeAllowanceUsdc: number | null;
  venue: VenueMode;
  network: string;
  venueReady: boolean;
  source: string;
  unavailableReason: string | null;
  tradingMode: TradingMode;
  profileSeason: number;
};

export type TradingProfile = {
  mode: TradingMode;
  season: number;
  startingBalanceUsd: number | null;
  balanceUsd: number | null;
  resetCount: number;
  lastResetAt: string | null;
};

export type DemoReset = {
  profile: TradingProfile;
  endedSeason: number;
  endingBalanceUsd: number;
  realizedPnlUsd: number;
  tradeCount: number;
  winCount: number;
  resetAt: string;
};

export type DepositAddress = {
  chainId: number;
  asset: "USDC";
  address: string;
  walletId: string;
};

export type Withdrawal = {
  id: string;
  userId: string;
  walletId: string;
  asset: string;
  amount: number;
  destinationAddress: string;
  status: string;
  txHash: string | null;
  createdAt: string;
  updatedAt: string;
};

export type Quote = {
  quoteId: string;
  tradingMode: TradingMode;
  profileSeason: number;
  venue: string;
  market: string;
  side: Side;
  ticketUsd: number;
  leverage: number;
  notionalUsd: number;
  maxLossUsd: number | null;
  takeProfitUsd: number | null;
  estimatedOpenCostUsd: number;
  estimatedCloseCostUsd: number;
  estimatedRoundTripCostUsd: number;
  liquidationPrice: number | null;
  stopLossPrice: number | null;
  takeProfitPrice: number | null;
  openingAllowed: boolean;
  createdAt: string;
  expiresAt: string;
};

export type Position = {
  id: string;
  tradingMode: TradingMode;
  profileSeason: number;
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
  takeProfitPrice: number | null;
  liquidationPrice: number | null;
  venueEstimatedNetPnlUsd?: number | null;
  terminalReason: "manual_close" | "external_close" | "take_profit" | "stop_loss" | "liquidation" | null;
  createdAt: string;
  updatedAt: string;
  openedAt: string | null;
};

export type Intent = {
  id: string;
  tradingMode: TradingMode;
  profileSeason: number;
  action: "open" | "close";
  status: string;
  positionId: string | null;
  market: string;
  createdAt: string;
  updatedAt: string;
};

export type ExecutionAttempt = {
  id: string;
  tradingMode: TradingMode;
  profileSeason: number;
  tradeIntentId: string;
  action: "open" | "close";
  status: string;
  txHash: string | null;
  error: string | null;
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
  tradingProfile: TradingProfile | null;
  positions: Position[];
  intents: Intent[];
  executionAttempts: ExecutionAttempt[];
  reconciliations: Reconciliation[];
  withdrawals: Withdrawal[];
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
  reason: Position["terminalReason"];
  reconciliationStatus?: string;
};

export type TradeSettings = {
  amountMode: "fixed" | "minimum" | "custom";
  ticketUsd: number;
  leverage: number;
  maxLossUsd: number;
  stopLossEnabled: boolean;
  takeProfitUsd: number;
  takeProfitEnabled: boolean;
};

export type Theme = {
  accent: string;
  glow: string;
  top: string;
  bottom: string;
};
