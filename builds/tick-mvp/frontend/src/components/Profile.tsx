import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Check,
  ChevronRight,
  Copy,
  History,
  LogOut,
  RefreshCw,
  RotateCcw,
  Settings2,
  X
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { QRCodeSVG } from "qrcode.react";

import { api, idempotencyKey } from "../api";
import { money, shortAddress, signedMoney } from "../format";
import { effectiveTicketUsd } from "../tradeSettings";
import type {
  AccountState,
  Market,
  Session,
  TradeSettings,
  TradingMode,
  VenueMode,
  WalletBalances
} from "../types";

type Props = {
  session: Session | null;
  state: AccountState | null;
  balances: WalletBalances | null;
  market: Market;
  settings: TradeSettings;
  estimatedNetPnl: number | null;
  depositRequested: boolean;
  onDepositRequestHandled: () => void;
  onSettings: (settings: TradeSettings) => void;
  onTrade: () => void;
  onSignOut: () => void;
  onBalances: () => Promise<void>;
  profileBusy: boolean;
  onTradingMode: (mode: TradingMode) => Promise<boolean>;
  activeVenue: VenueMode;
  onVenue: (venue: VenueMode) => Promise<boolean>;
  onResetDemo: () => Promise<void>;
};

export function Profile(props: Props) {
  const [walletAction, setWalletAction] = useState<"deposit" | "withdraw" | null>(null);
  const [withdrawAmount, setWithdrawAmount] = useState("");
  const [withdrawAddress, setWithdrawAddress] = useState("");
  const [walletBusy, setWalletBusy] = useState(false);
  const [balanceBusy, setBalanceBusy] = useState(false);
  const [walletMessage, setWalletMessage] = useState<string | null>(null);
  const [addressCopied, setAddressCopied] = useState(false);
  const [editingPreset, setEditingPreset] = useState(false);
  const [customAmountText, setCustomAmountText] = useState(String(props.settings.ticketUsd));
  const [confirmingDemoReset, setConfirmingDemoReset] = useState(false);
  const [historyFilter, setHistoryFilter] = useState<"all" | "wins" | "losses" | "liquidations">("all");
  const leverageOptions = (props.activeVenue === "flash"
    ? [100, 500]
    : [25, 50, 75, 100, 200, 250, 500, 1000]).filter(
    (value) => value >= props.market.minLeverage && value <= props.market.maxLeverage
  );
  const address = props.balances?.address ?? props.state?.wallet?.address ?? props.session?.walletAddress;
  const activePosition = props.state?.positions.find(
    (position) =>
      position.status === "opening"
      || position.status === "open"
      || position.status === "closing"
      || position.status === "unknown"
  ) ?? null;
  const completed = props.state?.positions.filter(
    (position) => position.status === "closed" || position.status === "liquidated"
  ) ?? [];
  const history = completed
    .map((position) => ({
      position,
      reconciliation: props.state?.reconciliations.find((item) => item.positionId === position.id)
    }))
    .sort(
      (left, right) =>
        Date.parse(right.position.updatedAt) - Date.parse(left.position.updatedAt)
    );
  const settled = history.filter(
    (item) => typeof item.reconciliation?.walletDeltaUsd === "number"
  );
  const netPnl = settled.reduce(
    (total, item) => total + (item.reconciliation?.walletDeltaUsd ?? 0),
    0
  );
  const wins = settled.filter((item) => (item.reconciliation?.walletDeltaUsd ?? 0) > 0).length;
  const winRate = settled.length ? Math.round(wins / settled.length * 100) : 0;
  const displayName = props.session?.user?.displayName || "TICK trader";
  const available = props.balances?.spendableUsdc ?? props.balances?.usdc ?? 0;
  const withdrawable = props.activeVenue === "flash"
    ? available + (props.balances?.onchainUsdc ?? 0)
    : available;
  const profile = props.state?.tradingProfile;
  const resolvedTicketUsd = effectiveTicketUsd(props.settings, props.market);
  const demoMode = profile?.mode === "demo";
  const network = props.activeVenue === "flash"
    ? "Solana"
    : props.activeVenue === "avantis"
      ? "Base"
      : "Arbitrum One";
  const venueLabel = props.activeVenue === "flash"
    ? "Flash Trade"
    : props.activeVenue === "avantis"
      ? "Avantis"
      : "gTrade";
  const withdrawalUnavailable = props.activeVenue === "avantis";
  const filteredHistory = useMemo(
    () => history.filter(({ position, reconciliation }) => {
      const pnl = reconciliation?.walletDeltaUsd;
      if (historyFilter === "wins") return typeof pnl === "number" && pnl > 0;
      if (historyFilter === "losses") return typeof pnl === "number" && pnl <= 0;
      if (historyFilter === "liquidations") return position.terminalReason === "liquidation";
      return true;
    }),
    [history, historyFilter]
  );

  useEffect(() => {
    if (!props.depositRequested) return;
    setWalletAction("deposit");
    props.onDepositRequestHandled();
  }, [props.depositRequested, props.onDepositRequestHandled]);

  useEffect(() => {
    setCustomAmountText(String(props.settings.ticketUsd));
  }, [props.settings.ticketUsd]);

  const withdraw = async (event: FormEvent) => {
    event.preventDefault();
    const amount = Number(withdrawAmount.replace(",", "."));
    if (!Number.isFinite(amount) || amount <= 0) return;
    setWalletBusy(true);
    setWalletMessage(null);
    try {
      const request = await api.withdraw(amount, withdrawAddress.trim(), idempotencyKey("withdraw"));
      setWalletMessage(`Withdrawal ${request.status}`);
      setWithdrawAmount("");
      setWithdrawAddress("");
      await props.onBalances();
    } catch (cause) {
      setWalletMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setWalletBusy(false);
    }
  };

  const copyAddress = async () => {
    if (!address) return;
    try {
      await copyText(address);
      setAddressCopied(true);
      setWalletMessage("Address copied");
      window.setTimeout(() => setAddressCopied(false), 1_800);
    } catch {
      setWalletMessage("Press and hold the address to copy it");
    }
  };

  const refreshBalance = async () => {
    if (balanceBusy) return;
    setBalanceBusy(true);
    try {
      await props.onBalances();
    } finally {
      setBalanceBusy(false);
    }
  };

  return (
    <main className="page profile-page">
      <header className="page-header">
        <div>
          <span>ACCOUNT</span>
          <h1>{displayName}</h1>
        </div>
      </header>

      <section className="performance-strip">
        <div>
          <span>Net PnL</span>
          <strong className={netPnl > 0 ? "positive" : netPnl < 0 ? "negative" : ""}>
            {signedMoney(netPnl)}
          </strong>
        </div>
        <div>
          <span>Trades</span>
          <strong>{settled.length}</strong>
        </div>
        <div>
          <span>Win rate</span>
          <strong>{winRate}%</strong>
        </div>
      </section>

      <section className="wallet-summary">
        <div className="wallet-summary-heading">
          <span>{demoMode ? "Demo balance" : "Available to trade"}</span>
          <button
            type="button"
            onClick={() => void refreshBalance()}
            disabled={balanceBusy}
            aria-label="Refresh balance"
            title="Refresh balance"
          >
            <RefreshCw className={balanceBusy ? "spinning" : ""} size={15} />
          </button>
        </div>
        <strong>{money(available)}</strong>
        {props.activeVenue !== "gtrade" && (props.balances?.onchainUsdc ?? 0) > 0 && !props.balances?.venueReady ? (
          <div className="flash-funding-status">
            <span>Preparing {venueLabel} balance</span>
            <strong>{money(props.balances?.onchainUsdc ?? 0)} received</strong>
          </div>
        ) : null}
        {demoMode ? (
          <div className="demo-season-summary">
            <span>Season {profile?.season ?? 1}</span>
            <strong>Started at {money(profile?.startingBalanceUsd ?? 1000)}</strong>
          </div>
        ) : (
          <>
            <div className="wallet-actions">
              <button
                className="primary"
                type="button"
                onClick={() => setWalletAction("deposit")}
              >
                <ArrowDownToLine size={16} />
                Deposit
              </button>
              <button
                type="button"
                disabled={withdrawable <= 0 || withdrawalUnavailable}
                onClick={() => setWalletAction("withdraw")}
                title={withdrawalUnavailable ? `${venueLabel} withdrawals are still manual in testing mode` : undefined}
              >
                <ArrowUpFromLine size={16} />
                Withdraw
              </button>
            </div>
            <button
              className="wallet-detail-button"
              type="button"
              onClick={copyAddress}
              title="Copy deposit address"
            >
              <span>Wallet &amp; network</span>
              <strong>{network} · {shortAddress(address ?? undefined)}</strong>
              {addressCopied ? <Check size={13} /> : <Copy size={13} />}
            </button>
          </>
        )}
      </section>

      <div className="section-heading preset-heading">
        <div>
          <Settings2 size={15} />
          <strong>Active preset</strong>
        </div>
        <span>Applied to every gesture</span>
      </div>
      <button className="preset-summary" type="button" onClick={() => setEditingPreset(true)}>
        <span className="preset-primary">
          <small>AMOUNT</small>
          <strong>{props.settings.amountMode === "minimum" ? "Minimum" : money(props.settings.ticketUsd)}</strong>
          {props.settings.amountMode === "minimum" ? (
            <em>{money(resolvedTicketUsd)} on {props.market.symbol}</em>
          ) : null}
        </span>
        <span>
          <small>LEVERAGE</small>
          <strong>{props.settings.leverage}x</strong>
          {props.settings.leverage >= 500 ? <em>Experimental</em> : null}
        </span>
        <span>
          <small>LOSS LIMIT</small>
          <strong>{props.settings.stopLossEnabled ? money(props.settings.maxLossUsd) : "Off"}</strong>
        </span>
        <ChevronRight size={18} />
      </button>

      {activePosition ? (
        <>
          <div className="section-heading active-trade-heading">
            <div>
              <span className="live-indicator" aria-hidden="true" />
              <strong>Active trade</strong>
            </div>
            <span>Live position</span>
          </div>
          <button className="active-trade-card" type="button" onClick={props.onTrade}>
            <span className="active-trade-identity">
              <small>{activePosition.status.toUpperCase()}</small>
              <strong>{positionSymbol(activePosition.market)}</strong>
              <em>{activePosition.leverage}x</em>
            </span>
            <span className={`active-trade-side ${activePosition.side}`}>
              {activePosition.side === "long" ? "↑ LONG" : "↓ SHORT"}
            </span>
            <span className="active-trade-result">
              <small>EST. NET</small>
              <strong
                className={
                  typeof props.estimatedNetPnl !== "number"
                    ? ""
                    : props.estimatedNetPnl >= 0
                      ? "positive"
                      : "negative"
                }
              >
                {activePosition.status === "closing"
                  ? "Exiting"
                  : typeof props.estimatedNetPnl === "number"
                    ? signedMoney(props.estimatedNetPnl)
                    : "Matching"}
              </strong>
            </span>
            <ChevronRight size={18} />
          </button>
        </>
      ) : null}

      <div className="section-heading history-heading">
        <div>
          <History size={15} />
          <strong>History</strong>
        </div>
        <span>Net wallet result</span>
      </div>
      <div className="history-filters" role="tablist" aria-label="Trade history filters">
        {(["all", "wins", "losses", "liquidations"] as const).map((filter) => (
          <button
            key={filter}
            className={historyFilter === filter ? "active" : ""}
            type="button"
            onClick={() => setHistoryFilter(filter)}
          >
            {filter === "liquidations" ? "Liquidated" : filter}
          </button>
        ))}
      </div>
      <section className="trade-history">
        {filteredHistory.length ? filteredHistory.slice(0, 20).map(({ position, reconciliation }) => {
          const pnl = reconciliation?.walletDeltaUsd;
          return (
            <div className="history-row" key={position.id}>
              <span className={`history-side ${position.side}`}>
                {position.side === "long" ? "↑ LONG" : "↓ SHORT"}
              </span>
              <span className="history-market">
                <strong>{position.market}</strong>
                <small>{position.leverage}x · {formatDate(position.updatedAt)}</small>
              </span>
              <span className="history-result">
                <strong className={pnl === null || pnl === undefined ? "" : pnl >= 0 ? "positive" : "negative"}>
                  {pnl === null || pnl === undefined ? "Finalizing" : signedMoney(pnl)}
                </strong>
                <small>{historyStatus(position.status, position.terminalReason)}</small>
              </span>
            </div>
          );
        }) : (
          <div className="empty-history">No completed trades yet</div>
        )}
      </section>

      <div className="section-heading utility-heading">
        <strong>Settings</strong>
      </div>
      <section className="account-facts">
        <div><span>Network</span><strong>{network}</strong></div>
        <div><span>Execution</span><strong>{venueLabel}</strong></div>
        <div><span>Account</span><strong>Invite protected</strong></div>
        <div><span>Email</span><strong>Not linked</strong></div>
      </section>
      <section className="trading-mode-setting venue-mode-setting">
        <div>
          <strong>Venue</strong>
          <span>
            {props.activeVenue === "flash"
              ? "Fast BTC and ETH execution. Separate Solana USDC balance."
              : "Broader markets with venue stop loss and take profit."}
          </span>
        </div>
        <div className={`venue-option-list ${props.profileBusy ? "is-switching" : ""}`} role="group" aria-label="Venue">
          {enabledVenues().map((venue) => (
            <button
              key={venue}
              type="button"
              className={props.activeVenue === venue ? "active" : ""}
              disabled={props.profileBusy || Boolean(activePosition)}
              aria-busy={props.profileBusy && props.activeVenue !== venue}
              onClick={() => void props.onVenue(venue)}
            >
              <strong>{venue === "gtrade" ? "gTrade" : venue === "flash" ? "Flash" : "Avantis"}</strong>
              <span>
                {venue === "gtrade"
                  ? "Broad 500x route · fixed open and close fees"
                  : venue === "flash"
                    ? "Fastest tested fills · separate Solana balance"
                    : "Lower losing-trade cost · slower keeper fill · profit share on wins"}
              </span>
            </button>
          ))}
        </div>
      </section>
      <section className="trading-mode-setting">
        <div>
          <strong>Trading mode</strong>
          <span>Live funds and demo score stay separate.</span>
        </div>
        <div className="trading-mode-control" role="group" aria-label="Trading mode">
          {(["live", "demo"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              className={profile?.mode === mode ? "active" : ""}
              disabled={props.profileBusy}
              onClick={() => void props.onTradingMode(mode)}
            >
              {mode}
            </button>
          ))}
        </div>
        {demoMode ? (
          <button
            className="reset-demo-button"
            type="button"
            disabled={props.profileBusy || Boolean(activePosition)}
            onClick={() => setConfirmingDemoReset(true)}
          >
            <RotateCcw size={15} />
            Reset demo season
          </button>
        ) : null}
      </section>
      <button className="sign-out-button" type="button" onClick={props.onSignOut}>
        <LogOut size={16} />
        Sign out
      </button>

      {confirmingDemoReset ? createPortal(
        <div
          className="wallet-sheet-backdrop"
          role="presentation"
          onPointerDown={(event) => {
            if (event.target === event.currentTarget) setConfirmingDemoReset(false);
          }}
        >
          <section
            className="wallet-sheet demo-reset-sheet"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="demo-reset-title"
            aria-describedby="demo-reset-description"
          >
            <button
              className="wallet-sheet-close"
              type="button"
              aria-label="Cancel demo reset"
              onClick={() => setConfirmingDemoReset(false)}
            >
              <X size={20} />
            </button>
            <span className="wallet-sheet-kicker">DEMO SEASON</span>
            <h2 id="demo-reset-title">Start over?</h2>
            <p id="demo-reset-description">
              Your demo balance returns to $1,000. This season's trades and score are cleared.
            </p>
            <div className="demo-reset-actions">
              <button
                type="button"
                className="demo-reset-cancel"
                onClick={() => setConfirmingDemoReset(false)}
              >
                Keep season
              </button>
              <button
                type="button"
                className="demo-reset-confirm"
                disabled={props.profileBusy}
                onClick={async () => {
                  await props.onResetDemo();
                  setConfirmingDemoReset(false);
                }}
              >
                <RotateCcw size={15} />
                Reset to $1,000
              </button>
            </div>
          </section>
        </div>,
        document.body
      ) : null}

      {editingPreset ? createPortal(
        <div className="wallet-sheet-backdrop" role="presentation">
          <section className="wallet-sheet preset-sheet" role="dialog" aria-modal="true">
            <button
              className="wallet-sheet-close"
              type="button"
              aria-label="Close preset"
              onClick={() => setEditingPreset(false)}
            >
              <X size={20} />
            </button>
            <span className="wallet-sheet-kicker">ACTIVE PRESET</span>
            <h2>Trade preset</h2>
            <p>Applied automatically when you open a position.</p>
            <div className="settings-group">
              <section className="preset-control-group">
                <span className="preset-group-label">POSITION</span>
                <label>Trade amount</label>
                <div className="segmented amount-segmented">
                  <button
                    type="button"
                    className={props.settings.amountMode === "fixed" ? "active" : ""}
                    onClick={() => props.onSettings({ ...props.settings, amountMode: "fixed", ticketUsd: 10 })}
                  >
                    $10
                  </button>
                  <button
                    type="button"
                    className={props.settings.amountMode === "minimum" ? "active" : ""}
                    onClick={() => props.onSettings({ ...props.settings, amountMode: "minimum" })}
                  >
                    MIN
                  </button>
                  <button
                    type="button"
                    className={props.settings.amountMode === "custom" ? "active" : ""}
                    onClick={() => props.onSettings({ ...props.settings, amountMode: "custom" })}
                  >
                    CUSTOM
                  </button>
                </div>
                {props.settings.amountMode === "custom" ? (
                  <label className="custom-amount-field">
                    <span>Custom amount</span>
                    <span className="custom-amount-input">
                      <span>$</span>
                      <input
                        type="number"
                        inputMode="decimal"
                        min="0.01"
                        step="0.01"
                        value={customAmountText}
                        onChange={(event) => {
                          const nextText = event.currentTarget.value;
                          setCustomAmountText(nextText);
                          const value = Number(nextText);
                          if (Number.isFinite(value) && value > 0) {
                            props.onSettings({
                              ...props.settings,
                              amountMode: "custom",
                              ticketUsd: value
                            });
                          }
                        }}
                        onBlur={() => {
                          if (!Number.isFinite(Number(customAmountText)) || Number(customAmountText) <= 0) {
                            setCustomAmountText(String(props.settings.ticketUsd));
                          }
                        }}
                      />
                    </span>
                  </label>
                ) : null}

                <label>Leverage</label>
                <div className="segmented" role="group" aria-label="Leverage">
                  {leverageOptions.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={props.settings.leverage === value ? "active" : ""}
                      aria-pressed={props.settings.leverage === value}
                      onClick={() => props.onSettings({ ...props.settings, leverage: value })}
                    >
                      {value}x
                    </button>
                  ))}
                </div>
              </section>

              <section className="preset-control-group protection-group">
                <span className="preset-group-label">PROTECTION</span>
                <ProtectionSelector
                  label="Stop loss"
                  enabled={props.settings.stopLossEnabled}
                  disabled={props.activeVenue === "flash"}
                  helper={props.activeVenue === "flash"
                    ? "Unavailable on the Flash canary"
                    : "Loss budget · placed on venue"}
                  value={props.settings.maxLossUsd}
                  onOff={() =>
                    props.onSettings({
                      ...props.settings,
                      stopLossEnabled: false
                    })
                  }
                  onValue={(value) =>
                    props.onSettings({
                      ...props.settings,
                      stopLossEnabled: true,
                      maxLossUsd: value
                    })
                  }
                />

                <ProtectionSelector
                  label="Take profit"
                  enabled={props.settings.takeProfitEnabled}
                  disabled={props.activeVenue === "flash"}
                  helper={props.activeVenue === "flash"
                    ? "Unavailable on the Flash canary"
                    : "Profit target · placed on venue"}
                  value={props.settings.takeProfitUsd}
                  onOff={() =>
                    props.onSettings({
                      ...props.settings,
                      takeProfitEnabled: false
                    })
                  }
                  onValue={(value) =>
                    props.onSettings({
                      ...props.settings,
                      takeProfitEnabled: true,
                      takeProfitUsd: value
                    })
                  }
                />
              </section>
            </div>
          </section>
        </div>,
        document.body
      ) : null}

      {walletAction ? createPortal(
        <div className="wallet-sheet-backdrop" role="presentation">
          <section className="wallet-sheet" role="dialog" aria-modal="true">
            <button
              className="wallet-sheet-close"
              type="button"
              aria-label="Close wallet"
              onClick={() => {
                setWalletAction(null);
                setWalletMessage(null);
              }}
            >
              <X size={20} />
            </button>
            {walletAction === "deposit" ? (
              <>
                <span className="wallet-sheet-kicker">{network.toUpperCase()}</span>
                <h2>Deposit USDC</h2>
                <p>
                  {props.activeVenue === "flash"
                    ? "Send native Solana USDC. TICK supplies setup SOL and moves the deposit into your Flash account automatically."
                    : props.activeVenue === "avantis"
                      ? "Send native USDC on Base. TICK supplies setup ETH and enables delegated Avantis execution automatically."
                      : "Send native USDC on Arbitrum to your TICK wallet."}
                </p>
                {address ? (
                  <div className="deposit-qr">
                    <QRCodeSVG
                      value={address}
                      size={174}
                      bgColor="#f2f8f6"
                      fgColor="#071011"
                      level="M"
                    />
                  </div>
                ) : null}
                <div className="wallet-address-full">
                  <span>{address ?? "Address unavailable"}</span>
                  <button
                    type="button"
                    onClick={copyAddress}
                    disabled={!address}
                    aria-label={addressCopied ? "Address copied" : "Copy deposit address"}
                  >
                    {addressCopied ? <Check size={16} /> : <Copy size={16} />}
                    {addressCopied ? "Copied" : "Copy"}
                  </button>
                </div>
              </>
            ) : (
              <>
                <span className="wallet-sheet-kicker">{network.toUpperCase()}</span>
                <h2>Withdraw USDC</h2>
                <p>
                  USDC is sent on {props.activeVenue === "flash" ? "Solana" : "Arbitrum One"}.
                </p>
                <form className="withdraw-form" onSubmit={withdraw}>
                  <label>
                    Amount
                    <div className="amount-input">
                      <input
                        type="text"
                        inputMode="decimal"
                        pattern="[0-9]+([.][0-9]{1,6})?"
                        placeholder="0.00"
                        value={withdrawAmount}
                        onChange={(event) => {
                          const normalized = event.target.value.replace(/,/g, ".");
                          if (/^\d*\.?\d{0,6}$/.test(normalized)) {
                            setWithdrawAmount(normalized);
                          }
                        }}
                        required
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setWithdrawAmount(
                            String(Math.max(0, withdrawable))
                          )
                        }
                      >
                        MAX
                      </button>
                    </div>
                  </label>
                  <label>
                    Destination
                    <input
                      type="text"
                      autoCapitalize="none"
                      autoCorrect="off"
                      placeholder={props.activeVenue === "flash" ? "Solana address" : "0x..."}
                      value={withdrawAddress}
                      onChange={(event) => setWithdrawAddress(event.target.value)}
                      required
                    />
                  </label>
                  <button type="submit" disabled={walletBusy}>
                    {walletBusy ? "Submitting" : "Withdraw"}
                  </button>
                </form>
              </>
            )}
            {walletMessage ? <span className="wallet-message">{walletMessage}</span> : null}
          </section>
        </div>,
        document.body
      ) : null}
    </main>
  );
}

function enabledVenues(): VenueMode[] {
  const configured = String(import.meta.env.VITE_ENABLED_VENUES ?? "gtrade,avantis")
    .split(",")
    .map((venue) => venue.trim())
    .filter((venue): venue is VenueMode =>
      venue === "gtrade" || venue === "flash" || venue === "avantis"
    );
  return configured.length ? configured : ["gtrade", "avantis"];
}

async function copyText(value: string): Promise<void> {
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Local-network iOS PWAs often reject the Clipboard API; use the
      // synchronous selection fallback while the tap gesture is still active.
    }
  }

  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.inset = "0 auto auto -9999px";
  textarea.style.fontSize = "16px";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, value.length);
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("clipboard unavailable");
}

function ProtectionSelector({
  label,
  enabled,
  disabled = false,
  helper,
  value,
  onOff,
  onValue
}: {
  label: string;
  enabled: boolean;
  disabled?: boolean;
  helper: string;
  value: number;
  onOff: () => void;
  onValue: (value: number) => void;
}) {
  return (
    <div className={`protection-setting ${enabled ? "enabled" : "disabled"}`}>
      <div>
        <label>{label}</label>
        <small>{helper}</small>
      </div>
      <div className="protection-options" role="group" aria-label={label}>
        <button
          className={!enabled ? "active" : ""}
          type="button"
          disabled={disabled}
          aria-pressed={!enabled}
          onClick={onOff}
        >
          Off
        </button>
        {[5, 10, 20, 50].map((option) => (
          <button
            key={option}
            className={enabled && value === option ? "active" : ""}
            type="button"
            disabled={disabled}
            aria-label={`${label} $${option}`}
            aria-pressed={enabled && value === option}
            onClick={() => onValue(option)}
          >
            ${option}
          </button>
        ))}
      </div>
    </div>
  );
}

function formatDate(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return "--";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(timestamp);
}

function positionSymbol(market: string): string {
  const normalized = market.toUpperCase().split(/[/-]/)[0];
  return normalized.replace("DEGEN", "") || market;
}

function historyStatus(
  status: string,
  reason: "manual_close" | "external_close" | "take_profit" | "stop_loss" | "liquidation" | null
): string {
  if (reason === "liquidation" || status === "liquidated") return "Liquidated";
  if (reason === "stop_loss") return "Stop hit";
  if (reason === "take_profit") return "Take profit";
  if (status === "closed") return "Closed";
  return status;
}
