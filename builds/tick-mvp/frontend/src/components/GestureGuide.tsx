import { ArrowDown, ArrowUp } from "lucide-react";
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
      <div className="gesture-guide-panel">
        <span className="gesture-guide-kicker">ONE GESTURE</span>
        <strong>Choose a direction</strong>
        <div className="gesture-guide-actions">
          <div>
            <ArrowUp aria-hidden="true" />
            <span>Swipe up</span>
            <b>LONG</b>
          </div>
          <i aria-hidden="true" />
          <div>
            <ArrowDown aria-hidden="true" />
            <span>Swipe down</span>
            <b>SHORT</b>
          </div>
        </div>
        <button
          type="button"
          onClick={dismiss}
          onPointerDown={(event) => event.stopPropagation()}
          onPointerUp={(event) => event.stopPropagation()}
        >
          Got it
        </button>
      </div>
    </div>
  );
}
