import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Hand,
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
          <strong>HOW IT WORKS</strong>
          <p>Swipe to trade. Move through live markets.</p>
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
          GOT IT
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
        <Hand className="gesture-hand" />
        <Icon className="gesture-arrow" />
      </span>
      <span>
        <small>{gesture}</small>
        <b>{action}</b>
      </span>
    </div>
  );
}
