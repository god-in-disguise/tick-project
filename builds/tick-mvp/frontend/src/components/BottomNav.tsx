import { House, UserRound } from "lucide-react";
import { createPortal } from "react-dom";

import { TickWordmark } from "./TickWordmark";

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
          aria-label="Pulse"
          title="Pulse"
          className={tab === "dashboard" ? "active" : ""}
          aria-current={tab === "dashboard" ? "page" : undefined}
          onClick={() => onTab("dashboard")}
        >
          <House size={20} />
          <span className="side-nav-label">Pulse</span>
        </button>
        <button
          className={`tick-nav ${tab === "trade" ? "active" : ""}`}
          aria-current={tab === "trade" ? "page" : undefined}
          onClick={() => onTab("trade")}
        >
          <TickWordmark className="nav-wordmark" />
        </button>
        <button
          aria-label="Me"
          title="Me"
          className={tab === "profile" ? "active" : ""}
          aria-current={tab === "profile" ? "page" : undefined}
          onClick={() => onTab("profile")}
        >
          <UserRound size={20} />
          <span className="side-nav-label">Me</span>
        </button>
      </nav>
    </div>,
    document.body
  );
}
