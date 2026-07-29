import { useEffect, useState } from "react";

import { api, ApiError, clearSession, storedSession } from "./api";
import { AuthGate } from "./components/AuthGate";
import { BottomNav, type Tab } from "./components/BottomNav";
import { Dashboard } from "./components/Dashboard";
import { InstallLanding } from "./components/InstallLanding";
import { Profile } from "./components/Profile";
import { TradeView } from "./components/TradeView";
import type { Session } from "./types";
import { useTick } from "./useTick";

export function App() {
  const [session, setSession] = useState<Session | null>(() => storedSession());
  const installed = useStandaloneMode();
  const appPreview = new URLSearchParams(window.location.search).get("app") === "1"
    || import.meta.env.VITE_FORCE_APP === "true";

  useEffect(() => {
    if (!session) return;
    let active = true;
    api.me().catch((cause) => {
      if (!active || !(cause instanceof ApiError) || ![401, 404].includes(cause.status)) return;
      clearSession();
      setSession(null);
    });
    return () => {
      active = false;
    };
  }, [session?.token]);

  if (!installed && !appPreview) {
    return <InstallLanding />;
  }

  if (!session) {
    return <AuthGate onAuthenticated={setSession} />;
  }

  return (
    <TickApp
      key={session.userId}
      session={session}
      onSignOut={() => {
        clearSession();
        setSession(null);
      }}
    />
  );
}

function TickApp({
  session,
  onSignOut
}: {
  session: Session;
  onSignOut: () => void;
}) {
  const tick = useTick(session);
  const [tab, setTab] = useState<Tab>("trade");
  const [depositRequested, setDepositRequested] = useState(false);

  if (!tick.activeMarket) {
    return (
      <div className="loading-screen">
        <span className="loading-mark" aria-hidden="true" />
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
  const requestFunding = () => {
    setDepositRequested(true);
    setTab("profile");
  };

  return (
    <div className="app-shell">
      <div className="app-content">
        {tab === "trade" ? (
          <TradeView
            userId={session.userId}
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
            onFund={requestFunding}
          />
        ) : null}
        {tab === "dashboard" ? <Dashboard markets={tick.markets} onMarket={selectMarket} /> : null}
        {tab === "profile" ? (
          <Profile
            session={tick.session}
            state={tick.state}
            balances={tick.balances}
            market={tick.activeMarket}
            settings={tick.settings}
            estimatedNetPnl={tick.estimatedNetPnl}
            depositRequested={depositRequested}
            onDepositRequestHandled={() => setDepositRequested(false)}
            onSettings={tick.setSettings}
            onTrade={() => setTab("trade")}
            onSignOut={onSignOut}
            onBalances={tick.refreshBalances}
          />
        ) : null}
      </div>
      <BottomNav tab={tab} onTab={setTab} />
    </div>
  );
}

function useStandaloneMode(): boolean {
  const detect = () => {
    const navigatorWithStandalone = navigator as Navigator & { standalone?: boolean };
    return window.matchMedia("(display-mode: standalone)").matches
      || navigatorWithStandalone.standalone === true;
  };
  const [standalone, setStandalone] = useState(detect);

  useEffect(() => {
    const media = window.matchMedia("(display-mode: standalone)");
    const update = () => setStandalone(detect());
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  return standalone;
}
