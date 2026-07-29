import { ScanSearch, UserRound } from "lucide-react";
import { createPortal } from "react-dom";

export type Tab = "dashboard" | "trade" | "profile";

type Props = {
  tab: Tab;
  onTab: (tab: Tab) => void;
};

export function BottomNav({ tab, onTab }: Props) {
  return createPortal(
    <div className="bottom-nav-dock">
      <nav className="bottom-nav" aria-label="Primary" data-active-tab={tab}>
        <span className="bottom-nav-lens" aria-hidden="true" />
        <button
          className={tab === "dashboard" ? "active" : ""}
          aria-current={tab === "dashboard" ? "page" : undefined}
          onClick={() => onTab("dashboard")}
        >
          <ScanSearch size={20} />
          <span>Pulse</span>
        </button>
        <button
          className={`tick-nav ${tab === "trade" ? "active" : ""}`}
          aria-current={tab === "trade" ? "page" : undefined}
          onClick={() => onTab("trade")}
        >
          <span className="tick-candle" aria-hidden="true" />
          <span>TICK</span>
        </button>
        <button
          className={tab === "profile" ? "active" : ""}
          aria-current={tab === "profile" ? "page" : undefined}
          onClick={() => onTab("profile")}
        >
          <UserRound size={20} />
          <span>Me</span>
        </button>
      </nav>
    </div>,
    document.body
  );
}
