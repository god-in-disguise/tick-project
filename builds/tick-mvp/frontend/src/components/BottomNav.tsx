import { Radar, UserRound } from "lucide-react";

export type Tab = "dashboard" | "trade" | "profile";

type Props = {
  tab: Tab;
  onTab: (tab: Tab) => void;
};

export function BottomNav({ tab, onTab }: Props) {
  return (
    <nav className="bottom-nav" aria-label="Primary">
      <button className={tab === "dashboard" ? "active" : ""} onClick={() => onTab("dashboard")}>
        <Radar size={18} />
        <span>Pulse</span>
      </button>
      <button className={`tick-nav ${tab === "trade" ? "active" : ""}`} onClick={() => onTab("trade")}>
        <span className="tick-candle" aria-hidden="true" />
        <span>TICK</span>
      </button>
      <button className={tab === "profile" ? "active" : ""} onClick={() => onTab("profile")}>
        <UserRound size={18} />
        <span>Me</span>
      </button>
    </nav>
  );
}
