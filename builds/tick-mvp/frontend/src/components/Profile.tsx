import { Copy, History, Settings2, WalletCards } from "lucide-react";

import { money, shortAddress, signedMoney } from "../format";
import type { AccountState, Session, TradeSettings, WalletBalances } from "../types";

type Props = {
  session: Session | null;
  state: AccountState | null;
  balances: WalletBalances | null;
  maxLeverage: number;
  settings: TradeSettings;
  onSettings: (settings: TradeSettings) => void;
};

export function Profile(props: Props) {
  const leverageOptions = [25, 50, 100, 500].filter((value) => value <= props.maxLeverage);
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
  const displayName = props.session?.user?.displayName || props.session?.user?.email || "TICK trader";

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
          <strong className={netPnl >= 0 ? "positive" : "negative"}>{signedMoney(netPnl)}</strong>
        </div>
        <div>
          <span>Trades</span>
          <strong>{settled.length}</strong>
        </div>
        <div>
          <span>Wins</span>
          <strong>{wins}</strong>
        </div>
      </section>

      <section className="wallet-summary">
        <span>Trading balance</span>
        <strong>{money(props.balances?.usdc)}</strong>
        <button
          className="address-button"
          onClick={() => address && navigator.clipboard.writeText(address)}
          title="Copy deposit address"
        >
          {shortAddress(address)}
          <Copy size={13} />
        </button>
      </section>

      <div className="section-heading">
        <div>
          <Settings2 size={15} />
          <strong>TICK config</strong>
        </div>
        <span>Applied to every gesture</span>
      </div>
      <section className="settings-group">
        <label>Collateral</label>
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

        <label>Venue stop loss</label>
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
      </section>

      <div className="section-heading">
        <div>
          <History size={15} />
          <strong>History</strong>
        </div>
        <span>Net wallet result</span>
      </div>
      <section className="trade-history">
        {history.length ? history.slice(0, 12).map(({ position, reconciliation }) => {
          const pnl = reconciliation?.walletDeltaUsd;
          return (
            <div className="history-row" key={position.id}>
              <span className={`history-side ${position.side}`}>
                {position.side === "long" ? "UP" : "DOWN"}
              </span>
              <span className="history-market">
                <strong>{position.market}</strong>
                <small>{position.leverage}x · {formatDate(position.updatedAt)}</small>
              </span>
              <span className="history-result">
                <strong className={pnl === null || pnl === undefined ? "" : pnl >= 0 ? "positive" : "negative"}>
                  {pnl === null || pnl === undefined ? "Settling" : signedMoney(pnl)}
                </strong>
                <small>{position.status}</small>
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
        <div><span>Execution</span><strong>gTrade</strong></div>
        <div><span>Wallet</span><strong>Platform custody</strong></div>
      </section>
    </main>
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
