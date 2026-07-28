import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Check,
  ChevronRight,
  Copy,
  History,
  LogOut,
  RefreshCw,
  Settings2,
  X
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { QRCodeSVG } from "qrcode.react";

import { api, idempotencyKey } from "../api";
import { money, shortAddress, signedMoney } from "../format";
import type { AccountState, Market, Session, TradeSettings, WalletBalances } from "../types";

type Props = {
  session: Session | null;
  state: AccountState | null;
  balances: WalletBalances | null;
  market: Market;
  settings: TradeSettings;
  onSettings: (settings: TradeSettings) => void;
  onSignOut: () => void;
  onBalances: () => Promise<void>;
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
  const [historyFilter, setHistoryFilter] = useState<"all" | "wins" | "losses" | "liquidations">("all");
  const leverageOptions = [25, 50, 100, 500].filter(
    (value) => value >= props.market.minLeverage && value <= props.market.maxLeverage
  );
  const fixedLeverage = props.market.minLeverage === props.market.maxLeverage;
  const address = props.session?.walletAddress ?? props.balances?.address;
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
          <span>Available to trade</span>
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
            disabled={available <= 0}
            onClick={() => setWalletAction("withdraw")}
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
          <strong>Arbitrum · {shortAddress(address)}</strong>
          {addressCopied ? <Check size={13} /> : <Copy size={13} />}
        </button>
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
          <strong>{money(props.settings.ticketUsd)}</strong>
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
        <div><span>Network</span><strong>Arbitrum One</strong></div>
        <div><span>Execution</span><strong>Best available route</strong></div>
        <div><span>Account</span><strong>Invite protected</strong></div>
        <div><span>Email</span><strong>Not linked</strong></div>
      </section>
      <button className="sign-out-button" type="button" onClick={props.onSignOut}>
        <LogOut size={16} />
        Sign out
      </button>

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
                <div className="segmented">
                  {[10, 20, 50, 100].map((value) => (
                    <button
                      key={value}
                      className={props.settings.ticketUsd === value ? "active" : ""}
                      onClick={() => props.onSettings({ ...props.settings, ticketUsd: value })}
                    >
                      ${value}
                    </button>
                  ))}
                </div>

                <label>Leverage</label>
                {fixedLeverage ? (
                  <div className="fixed-setting">
                    <strong>{props.market.maxLeverage}x</strong>
                    <span>Fixed for {props.market.symbol} DEGEN</span>
                  </div>
                ) : (
                  <div className="segmented">
                    {leverageOptions.map((value) => (
                      <button
                        key={value}
                        className={props.settings.leverage === value ? "active" : ""}
                        onClick={() => props.onSettings({ ...props.settings, leverage: value })}
                      >
                        {value}x
                      </button>
                    ))}
                  </div>
                )}
              </section>

              <section className="preset-control-group protection-group">
                <span className="preset-group-label">PROTECTION</span>
                <ProtectionSelector
                  label="Stop loss"
                  enabled={props.settings.stopLossEnabled}
                  helper="Loss budget · placed on venue"
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
                  helper="Profit target · placed on venue"
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
                <span className="wallet-sheet-kicker">ARBITRUM ONE</span>
                <h2>Deposit USDC</h2>
                <p>Send native USDC on Arbitrum to your TICK wallet.</p>
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
                <span className="wallet-sheet-kicker">ARBITRUM ONE</span>
                <h2>Withdraw USDC</h2>
                <p>USDC is sent directly from your TICK wallet.</p>
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
                            String(Math.max(0, props.balances?.spendableUsdc ?? 0))
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
                      placeholder="0x..."
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
  helper,
  value,
  onOff,
  onValue
}: {
  label: string;
  enabled: boolean;
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
