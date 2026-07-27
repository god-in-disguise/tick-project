import { useState } from "react";

import { BottomNav, type Tab } from "./components/BottomNav";
import { Dashboard } from "./components/Dashboard";
import { Profile } from "./components/Profile";
import { TradeView } from "./components/TradeView";
import { useTick } from "./useTick";

export function App() {
  const tick = useTick();
  const [tab, setTab] = useState<Tab>("trade");

  if (!tick.activeMarket) {
    return (
      <div className="loading-screen">
        <strong>TICK</strong>
        <span>{tick.error ?? "Connecting to live markets"}</span>
      </div>
    );
  }

  const selectMarket = async (market: string) => {
    if (tick.activePosition || tick.busy) return;
    await tick.selectMarket(market);
    setTab("trade");
  };

  return (
    <div className="app-shell">
      <div className="app-content">
        {tab === "trade" ? (
          <TradeView
            market={tick.activeMarket}
            position={tick.activePosition}
            quote={tick.activeQuote}
            quotes={tick.quotes}
            balances={tick.balances}
            settings={tick.settings}
            estimatedNetPnl={tick.estimatedNetPnl}
            busy={tick.busy}
            busyAction={tick.busyAction}
            error={tick.error}
            closedResult={tick.closedResult}
            onOpen={tick.open}
            onClose={tick.close}
            onShift={tick.shiftMarket}
          />
        ) : null}
        {tab === "dashboard" ? <Dashboard markets={tick.markets} onMarket={selectMarket} /> : null}
        {tab === "profile" ? (
          <Profile
            session={tick.session}
            state={tick.state}
            balances={tick.balances}
            settings={tick.settings}
            onSettings={tick.setSettings}
          />
        ) : null}
      </div>
      <BottomNav tab={tab} onTab={setTab} />
    </div>
  );
}
