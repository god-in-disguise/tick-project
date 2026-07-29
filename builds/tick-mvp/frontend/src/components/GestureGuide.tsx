import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  type LucideIcon
} from "lucide-react";
import { useState } from "react";

type Props = {
  userId: string;
};

export function GestureGuide({ userId }: Props) {
  const storageKey = `tick.gesture-guide.v1.${userId}`;
  const [visible, setVisible] = useState(
    () => localStorage.getItem(storageKey) !== "dismissed"
  );

  if (!visible) return null;

  const dismiss = () => {
    localStorage.setItem(storageKey, "dismissed");
    setVisible(false);
  };

  return (
    <div className="gesture-guide" aria-label="Trade gesture guide">
      <section className="gesture-guide-panel">
        <header>
          <span className="gesture-guide-kicker">THE TICK LOOP</span>
          <strong>How TICK works</strong>
          <p>One deliberate gesture acts on the market in front of you.</p>
        </header>
        <div className="gesture-guide-actions">
          <Gesture direction="up" Icon={ArrowUp} gesture="Swipe up" action="Go long" />
          <Gesture direction="down" Icon={ArrowDown} gesture="Swipe down" action="Go short" />
          <Gesture direction="left" Icon={ArrowLeft} gesture="Swipe left" action="Next market" />
          <Gesture direction="right" Icon={ArrowRight} gesture="Swipe right" action="Previous market" />
        </div>
        <button
          type="button"
          onClick={dismiss}
          onPointerDown={(event) => event.stopPropagation()}
          onPointerUp={(event) => event.stopPropagation()}
        >
          Start exploring
        </button>
      </section>
    </div>
  );
}

function Gesture({
  direction,
  Icon,
  gesture,
  action
}: {
  direction: "up" | "down" | "left" | "right";
  Icon: LucideIcon;
  gesture: string;
  action: string;
}) {
  return (
    <div className="gesture-guide-action">
      <span className={`gesture-motion gesture-motion-${direction}`} aria-hidden="true">
        <i />
        <Icon />
      </span>
      <span>
        <small>{gesture}</small>
        <b>{action}</b>
      </span>
    </div>
  );
}
