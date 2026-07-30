import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, RefObject } from "react";

import type { Side } from "../types";

export type SwipeCue = "LONG" | "SHORT" | "CLOSE" | "WAIT" | "LOCKED";
export type SwipeAction = {
  armed: boolean;
  blocked: boolean;
  direction: "up" | "down";
  label: "LONG" | "SHORT" | "CLOSE" | "ADD FUNDS" | "WAIT" | "POSITION LOCKED";
};

type Options = {
  marketId: string;
  positionSide: Side | null;
  busy: boolean;
  needsFunding: boolean;
  onOpen: (side: Side) => void;
  onClose: () => void;
  onShift: (offset: number) => void;
  onFund: () => void;
  onCue: (cue: SwipeCue) => void;
  onChartDoubleTap: () => void;
};

type Axis = "horizontal" | "vertical";
type Sample = { x: number; y: number; at: number };
type Pointer = {
  id: number;
  startX: number;
  startY: number;
  chartTap: boolean;
  axis: Axis | null;
  samples: Sample[];
};
type Motion = {
  x: number;
  y: number;
  progress: number;
  pageProgress: number;
  scale: number;
};

const AXIS_LOCK_PX = 12;
const AXIS_DOMINANCE = 1.12;
const DOUBLE_TAP_MS = 320;
const TAP_MOVEMENT_PX = 12;
const DOUBLE_TAP_DISTANCE_PX = 28;
const HORIZONTAL_COMMIT_RATIO = 0.27;
const HORIZONTAL_FLING_PX_PER_SECOND = 800;
const HORIZONTAL_MIN_FLING_DISTANCE_PX = 32;
const HORIZONTAL_PROJECTION_SECONDS = 0.16;
const HORIZONTAL_MIN_SETTLE_MS = 170;
const HORIZONTAL_MAX_SETTLE_MS = 300;
const VERTICAL_SETTLE_MS = 220;
const VERTICAL_DISARM_RATIO = 0.78;

export function useTradeSwipe(options: Options): {
  rootRef: RefObject<HTMLElement | null>;
  previewOffset: -1 | 1 | null;
  action: SwipeAction | null;
  handlers: {
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerUp: (event: ReactPointerEvent<HTMLElement>) => void;
    onPointerCancel: () => void;
  };
} {
  const rootRef = useRef<HTMLElement>(null);
  const pointer = useRef<Pointer | null>(null);
  const actionRef = useRef<SwipeAction | null>(null);
  const previewOffsetRef = useRef<-1 | 1 | null>(null);
  const lastChartTap = useRef<{ at: number; x: number; y: number } | null>(null);
  const motion = useRef<Motion>({
    x: 0,
    y: 0,
    progress: 0,
    pageProgress: 0,
    scale: 1
  });
  const motionFrame = useRef<number | null>(null);
  const settleTimer = useRef<number | null>(null);
  const settling = useRef(false);
  const verticalArmed = useRef(false);
  const [previewOffset, setPreviewOffsetState] = useState<-1 | 1 | null>(null);
  const [action, setActionState] = useState<SwipeAction | null>(null);

  const setPreviewOffset = (offset: -1 | 1 | null) => {
    if (previewOffsetRef.current === offset) return;
    previewOffsetRef.current = offset;
    setPreviewOffsetState(offset);
  };

  const setAction = (next: SwipeAction | null) => {
    const current = actionRef.current;
    if (
      current?.armed === next?.armed
      && current?.blocked === next?.blocked
      && current?.direction === next?.direction
      && current?.label === next?.label
    ) {
      return;
    }
    if (current && next && current.armed !== next.armed) {
      haptic(next.armed ? 8 : 3);
    }
    actionRef.current = next;
    setActionState(next);
  };

  const applyMotion = () => {
    motionFrame.current = null;
    const root = rootRef.current;
    if (!root) return;
    root.style.setProperty("--swipe-x", `${motion.current.x}px`);
    root.style.setProperty("--swipe-y", `${motion.current.y}px`);
    root.style.setProperty("--swipe-progress", String(motion.current.progress));
    root.style.setProperty("--swipe-page-progress", String(motion.current.pageProgress));
    root.style.setProperty("--swipe-scale", String(motion.current.scale));
  };

  const updateMotion = (next: Motion, immediate = false) => {
    motion.current = next;
    if (immediate) {
      if (motionFrame.current !== null) cancelAnimationFrame(motionFrame.current);
      applyMotion();
      return;
    }
    if (motionFrame.current === null) {
      motionFrame.current = requestAnimationFrame(applyMotion);
    }
  };

  const clearSettleTimer = () => {
    if (settleTimer.current !== null) {
      window.clearTimeout(settleTimer.current);
      settleTimer.current = null;
    }
  };

  const finishReset = () => {
    const root = rootRef.current;
    root?.classList.remove("is-swipe-settling");
    root?.removeAttribute("data-swipe-axis");
    settling.current = false;
    setPreviewOffset(null);
    setAction(null);
  };

  const reset = (durationMs = VERTICAL_SETTLE_MS) => {
    const root = rootRef.current;
    clearSettleTimer();
    settling.current = true;
    verticalArmed.current = false;
    root?.classList.add("is-swipe-settling");
    root?.style.setProperty("--swipe-settle-ms", `${durationMs}ms`);
    updateMotion({ x: 0, y: 0, progress: 0, pageProgress: 0, scale: 1 }, true);
    settleTimer.current = window.setTimeout(finishReset, durationMs);
  };

  const resetImmediately = () => {
    clearSettleTimer();
    if (motionFrame.current !== null) {
      cancelAnimationFrame(motionFrame.current);
      motionFrame.current = null;
    }
    pointer.current = null;
    verticalArmed.current = false;
    motion.current = { x: 0, y: 0, progress: 0, pageProgress: 0, scale: 1 };
    applyMotion();
    finishReset();
  };

  useEffect(() => {
    resetImmediately();
    lastChartTap.current = null;
    // The market ID is the state boundary for a completed horizontal page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options.marketId]);

  useEffect(() => () => {
    clearSettleTimer();
    if (motionFrame.current !== null) cancelAnimationFrame(motionFrame.current);
  }, []);

  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (settling.current || isGestureExcludedTarget(event.target)) return;
    verticalArmed.current = false;
    pointer.current = {
      id: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      chartTap: isChartTapTarget(event.target),
      axis: null,
      samples: [{ x: event.clientX, y: event.clientY, at: performance.now() }]
    };
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture may be unavailable for synthetic accessibility input.
    }
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const current = pointer.current;
    if (!current || current.id !== event.pointerId || settling.current) return;
    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;
    const horizontal = Math.abs(dx);
    const vertical = Math.abs(dy);
    rememberSample(current, event.clientX, event.clientY);

    if (!current.axis) {
      if (Math.max(horizontal, vertical) < AXIS_LOCK_PX) return;
      if (horizontal > vertical * AXIS_DOMINANCE) {
        current.axis = "horizontal";
      } else if (vertical > horizontal * AXIS_DOMINANCE) {
        current.axis = "vertical";
      } else {
        return;
      }
      rootRef.current?.setAttribute("data-swipe-axis", current.axis);
      lastChartTap.current = null;
    }

    if (current.axis === "horizontal") {
      const blocked = Boolean(options.positionSide || options.busy);
      const offset: -1 | 1 = dx < 0 ? 1 : -1;
      setPreviewOffset(blocked ? null : offset);
      setAction(null);
      const visibleX = blocked ? rubberBand(dx, 42) : dx;
      const width = rootRef.current?.clientWidth ?? window.innerWidth;
      const pageProgress = blocked
        ? 0
        : clamp(horizontal / (width * HORIZONTAL_COMMIT_RATIO), 0, 1);
      updateMotion({ x: visibleX, y: 0, progress: 0, pageProgress, scale: 1 });
      return;
    }

    setPreviewOffset(null);
    const threshold = verticalThreshold(rootRef.current);
    const progress = clamp(vertical / threshold, 0, 1);
    if (!verticalArmed.current && progress >= 1) {
      verticalArmed.current = true;
    } else if (verticalArmed.current && progress < VERTICAL_DISARM_RATIO) {
      verticalArmed.current = false;
    }
    const direction = dy < 0 ? "up" : "down";
    const side: Side = direction === "up" ? "long" : "short";
    const nextAction = verticalAction(options, side, direction, verticalArmed.current);
    setAction(nextAction);
    const visibleY = Math.sign(dy) * resistedVerticalTravel(vertical, rootRef.current);
    updateMotion({
      x: 0,
      y: visibleY,
      progress,
      pageProgress: 0,
      scale: 1 - progress * 0.006
    });
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLElement>) => {
    const current = pointer.current;
    pointer.current = null;
    if (!current || current.id !== event.pointerId || settling.current) return;
    rememberSample(current, event.clientX, event.clientY);
    const dx = event.clientX - current.startX;
    const dy = event.clientY - current.startY;
    const horizontal = Math.abs(dx);
    const vertical = Math.abs(dy);

    if (!current.axis && current.chartTap && horizontal <= TAP_MOVEMENT_PX && vertical <= TAP_MOVEMENT_PX) {
      handleChartTap(event.clientX, event.clientY);
      return;
    }

    if (current.axis === "horizontal") {
      if (options.positionSide || options.busy) {
        options.onCue("LOCKED");
        reset(horizontalResetDuration(horizontal, widthFor(rootRef.current)));
        return;
      }
      const velocity = pointerVelocity(current);
      const direction = dx < 0 ? 1 : -1;
      const width = widthFor(rootRef.current);
      const sameDirectionFling = Math.sign(velocity.x) === Math.sign(dx)
        && Math.abs(velocity.x) >= HORIZONTAL_FLING_PX_PER_SECOND
        && horizontal >= HORIZONTAL_MIN_FLING_DISTANCE_PX;
      const projectedX = dx + velocity.x * HORIZONTAL_PROJECTION_SECONDS;
      const projectedCommit = Math.sign(projectedX) === Math.sign(dx)
        && horizontal >= HORIZONTAL_MIN_FLING_DISTANCE_PX
        && Math.abs(projectedX) >= width * HORIZONTAL_COMMIT_RATIO;
      if (
        horizontal >= width * HORIZONTAL_COMMIT_RATIO
        || sameDirectionFling
        || projectedCommit
      ) {
        settleHorizontal(direction as -1 | 1, width, dx, velocity.x);
      } else {
        reset(horizontalResetDuration(horizontal, width));
      }
      return;
    }

    if (current.axis === "vertical") {
      const completedAction = actionRef.current;
      reset(VERTICAL_SETTLE_MS);
      if (!completedAction?.armed || completedAction.blocked) {
        if (completedAction?.label === "WAIT") options.onCue("WAIT");
        if (completedAction?.label === "POSITION LOCKED") options.onCue("LOCKED");
        return;
      }
      executeAction(completedAction);
      return;
    }

    reset();
  };

  const onPointerCancel = () => {
    pointer.current = null;
    reset();
  };

  const handleChartTap = (x: number, y: number) => {
    const now = performance.now();
    const previous = lastChartTap.current;
    const closeToPrevious = previous
      ? Math.hypot(x - previous.x, y - previous.y) <= DOUBLE_TAP_DISTANCE_PX
      : false;
    if (previous && now - previous.at <= DOUBLE_TAP_MS && closeToPrevious) {
      lastChartTap.current = null;
      haptic(3);
      options.onChartDoubleTap();
    } else {
      lastChartTap.current = { at: now, x, y };
    }
  };

  const settleHorizontal = (
    offset: -1 | 1,
    width: number,
    currentX: number,
    velocityX: number
  ) => {
    const root = rootRef.current;
    clearSettleTimer();
    settling.current = true;
    setPreviewOffset(offset);
    const targetX = -offset * width;
    const durationMs = horizontalCommitDuration(currentX, targetX, width, velocityX);
    root?.classList.add("is-swipe-settling");
    root?.style.setProperty("--swipe-settle-ms", `${durationMs}ms`);
    updateMotion({
      x: targetX,
      y: 0,
      progress: 0,
      pageProgress: 1,
      scale: 1
    }, true);
    haptic(4);
    settleTimer.current = window.setTimeout(() => {
      options.onShift(offset);
      requestAnimationFrame(() => {
        motion.current = {
          x: 0,
          y: 0,
          progress: 0,
          pageProgress: 0,
          scale: 1
        };
        applyMotion();
        finishReset();
      });
    }, durationMs);
  };

  const executeAction = (completedAction: SwipeAction) => {
    switch (completedAction.label) {
      case "LONG":
        options.onCue("LONG");
        options.onOpen("long");
        break;
      case "SHORT":
        options.onCue("SHORT");
        options.onOpen("short");
        break;
      case "CLOSE":
        options.onCue("CLOSE");
        options.onClose();
        break;
      case "ADD FUNDS":
        options.onCue("WAIT");
        options.onFund();
        break;
      default:
        break;
    }
  };

  return {
    rootRef,
    previewOffset,
    action,
    handlers: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel }
  };
}

function verticalAction(
  options: Pick<Options, "positionSide" | "busy" | "needsFunding">,
  side: Side,
  direction: SwipeAction["direction"],
  armed: boolean
): SwipeAction {
  if (options.busy) {
    return { armed, blocked: true, direction, label: "WAIT" };
  }
  if (options.positionSide) {
    if (options.positionSide !== side) {
      return { armed, blocked: true, direction, label: "POSITION LOCKED" };
    }
    return { armed, blocked: false, direction, label: "CLOSE" };
  }
  if (options.needsFunding) {
    return { armed, blocked: false, direction, label: "ADD FUNDS" };
  }
  return {
    armed,
    blocked: false,
    direction,
    label: side === "long" ? "LONG" : "SHORT"
  };
}

function rememberSample(pointer: Pointer, x: number, y: number) {
  const now = performance.now();
  pointer.samples.push({ x, y, at: now });
  const cutoff = now - 120;
  while (pointer.samples.length > 2 && pointer.samples[0].at < cutoff) {
    pointer.samples.shift();
  }
}

function pointerVelocity(pointer: Pointer): { x: number; y: number } {
  const first = pointer.samples[0];
  const last = pointer.samples[pointer.samples.length - 1];
  const seconds = Math.max((last.at - first.at) / 1_000, 0.001);
  return {
    x: (last.x - first.x) / seconds,
    y: (last.y - first.y) / seconds
  };
}

function verticalThreshold(root: HTMLElement | null): number {
  const height = root?.clientHeight ?? window.innerHeight;
  return clamp(height * 0.12, 90, 120);
}

function resistedVerticalTravel(distance: number, root: HTMLElement | null): number {
  const cap = clamp((root?.clientHeight ?? window.innerHeight) * 0.09, 60, 90);
  return cap * (1 - Math.exp(-distance / (cap * 0.72)));
}

function rubberBand(distance: number, cap: number): number {
  return Math.sign(distance) * cap * (1 - Math.exp(-Math.abs(distance) / cap));
}

function widthFor(root: HTMLElement | null): number {
  return root?.clientWidth ?? window.innerWidth;
}

function horizontalResetDuration(distance: number, width: number): number {
  const ratio = clamp(distance / Math.max(width, 1), 0, 1);
  return Math.round(170 + ratio * 90);
}

function horizontalCommitDuration(
  currentX: number,
  targetX: number,
  width: number,
  velocityX: number
): number {
  const remainingRatio = clamp(Math.abs(targetX - currentX) / Math.max(width, 1), 0, 1);
  const movingTowardTarget = Math.sign(velocityX) === Math.sign(targetX - currentX);
  const velocityReduction = movingTowardTarget
    ? clamp(Math.abs(velocityX) / 2_000, 0, 1) * 65
    : 0;
  return Math.round(clamp(
    175 + remainingRatio * 115 - velocityReduction,
    HORIZONTAL_MIN_SETTLE_MS,
    HORIZONTAL_MAX_SETTLE_MS
  ));
}

function haptic(duration: number) {
  navigator.vibrate?.(duration);
}

function isGestureExcludedTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(
    "button, a, input, select, textarea, [role='button'], "
      + ".execution-dock, .pnl-panel, .result-pop, .funding-prompt, "
      + ".gesture-guide, .error-toast"
  ));
}

function isChartTapTarget(target: EventTarget | null): boolean {
  return target instanceof Element && Boolean(target.closest(".chart-stage"));
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
