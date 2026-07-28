import {
  ArrowDownToLine,
  ArrowUpFromLine,
  ChevronRight,
  Copy,
  History,
  LogOut,
  Settings2,
  WalletCards,
  X
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { api, idempotencyKey } from "../api";
import { money, shortAddress, signedMoney } from "../format";
import type { AccountState, Session, TradeSettings, WalletBalances } from "../types";

type Props = {
  session: Session | null;
  state: AccountState | null;
  balances: WalletBalances | null;
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
  const [walletMessage, setWalletMessage] = useState<string | null>(null);
  const [editingPreset, setEditingPreset] = useState(false);
  const [historyFilter, setHistoryFilter] = useState<"all" | "wins" | "losses" | "liquidations">("all");
  const leverageOptions = [25, 50, 100, 500];
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
    const amount = Number(withdrawAmount);
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

  return (
    <main className="page profile-page">
      <header className="page-header">
        <div>
          <span>ACCOUNT</span>
          <h1>Me</h1>
          <small>{displayName}</small>
        </div>
        <WalletCards size={22} />
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
        <span>Available to trade</span>
        <strong>{money(available)}</strong>
        <div className="wallet-actions">
          <button
            className={available <= 0 ? "primary" : ""}
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
          onClick={() => address && navigator.clipboard.writeText(address)}
          title="Copy deposit address"
        >
          <span>Wallet &amp; network</span>
          <strong>Arbitrum · {shortAddress(address)}</strong>
          <Copy size={13} />
        </button>
      </section>

      <div className="section-heading">
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

      <div className="section-heading">
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

      <div className="section-heading">
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

      {editingPreset ? (
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
            <h2>Trade settings</h2>
            <p>These terms apply automatically to every opening gesture.</p>
            <div className="settings-group">
              <label>Amount</label>
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

              <SettingToggle
                label="Stop loss"
                enabled={props.settings.stopLossEnabled}
                onToggle={() =>
                  props.onSettings({
                    ...props.settings,
                    stopLossEnabled: !props.settings.stopLossEnabled
                  })
                }
              />
              {props.settings.stopLossEnabled ? (
                <>
                  <small className="venue-protection-note">Loss budget · placed directly on venue</small>
                  <div className="segmented">
                    {[5, 10, 20, 50].map((value) => (
                      <button
                        key={value}
                        className={props.settings.maxLossUsd === value ? "active" : ""}
                        onClick={() => props.onSettings({ ...props.settings, maxLossUsd: value })}
                      >
                        ${value}
                      </button>
                    ))}
                  </div>
                </>
              ) : null}

              <SettingToggle
                label="Take profit"
                enabled={props.settings.takeProfitEnabled}
                onToggle={() =>
                  props.onSettings({
                    ...props.settings,
                    takeProfitEnabled: !props.settings.takeProfitEnabled
                  })
                }
              />
              {props.settings.takeProfitEnabled ? (
                <>
                  <small className="venue-protection-note">Profit target · placed directly on venue</small>
                  <div className="segmented">
                    {[5, 10, 20, 50].map((value) => (
                      <button
                        key={value}
                        className={props.settings.takeProfitUsd === value ? "active" : ""}
                        onClick={() => props.onSettings({ ...props.settings, takeProfitUsd: value })}
                      >
                        ${value}
                      </button>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}

      {walletAction ? (
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
                <button
                  className="wallet-address-full"
                  type="button"
                  onClick={() => address && navigator.clipboard.writeText(address)}
                >
                  <span>{address ?? "Address unavailable"}</span>
                  <Copy size={16} />
                </button>
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
                        type="number"
                        inputMode="decimal"
                        min="0.01"
                        step="0.01"
                        placeholder="0.00"
                        value={withdrawAmount}
                        onChange={(event) => setWithdrawAmount(event.target.value)}
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
        </div>
      ) : null}
    </main>
  );
}

function SettingToggle({
  label,
  enabled,
  onToggle
}: {
  label: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="setting-toggle-row">
      <label>{label}</label>
      <button
        className="setting-toggle"
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={`${label} ${enabled ? "on" : "off"}`}
        onClick={onToggle}
      >
        <span />
      </button>
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
