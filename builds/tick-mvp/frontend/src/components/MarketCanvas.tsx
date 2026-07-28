import { useEffect, useLayoutEffect, useRef } from "react";

import { price } from "../format";
import type { Market, Side, Theme } from "../types";

type Props = {
  market: Market;
  theme: Theme;
  entry: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  liquidation: number | null;
  side: Side | null;
};

type Domain = { min: number; max: number; market: string; lastExtremeAt: number };

const WINDOW_SECONDS = 90;

export function MarketCanvas(props: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const propsRef = useRef(props);
  const visualPrice = useRef(props.market.price);
  const domainRef = useRef<Domain | null>(null);
  const frameRef = useRef(0);
  propsRef.current = props;

  useLayoutEffect(() => {
    visualPrice.current = props.market.price;
    domainRef.current = null;
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (canvas && context) {
      draw(context, canvas, props, props.market.price, domainRef);
    }
  }, [props.market.market]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      canvas.width = Math.max(1, Math.round(rect.width * dpr));
      canvas.height = Math.max(1, Math.round(rect.height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const render = () => {
      const current = propsRef.current;
      const target = current.market.price;
      visualPrice.current += (target - visualPrice.current) * 0.18;
      if (Math.abs(target - visualPrice.current) < Math.max(Math.abs(target) * 1e-10, 1e-8)) {
        visualPrice.current = target;
      }
      draw(context, canvas, current, visualPrice.current, domainRef);
      frameRef.current = requestAnimationFrame(render);
    };
    frameRef.current = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frameRef.current);
      observer.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className="market-canvas" aria-label={`${props.market.symbol} live price chart`} />;
}

function draw(
  context: CanvasRenderingContext2D,
  canvas: HTMLCanvasElement,
  props: Props,
  displayPrice: number,
  domainRef: React.MutableRefObject<Domain | null>
) {
  const dpr = Math.min(window.devicePixelRatio || 1, 3);
  const width = canvas.width / dpr;
  const height = canvas.height / dpr;
  if (width <= 1 || height <= 1) return;

  const top = 22;
  const bottom = height - (props.entry !== null ? 124 : 62);
  const left = 0;
  const right = width - 58;
  const now = Date.now() / 1000;
  const start = now - WINDOW_SECONDS;
  const points = props.market.observations.filter(
    (point) => point.receivedTs >= start && Number.isFinite(point.price) && point.price > 0
  );
  const source = points.length ? points : [{ seq: 0, receivedTs: now, price: props.market.price, unchanged: true }];
  const values = source.map((point) => point.price);
  const targetDomain = calculateDomain(values, props.market.price);
  const domain = stableDomain(domainRef, props.market.market, targetDomain);
  const span = Math.max(domain.max - domain.min, Number.EPSILON);
  const x = (time: number) => left + clamp((time - start) / WINDOW_SECONDS, 0, 1) * (right - left);
  const y = (value: number) => bottom - ((value - domain.min) / span) * (bottom - top);

  context.clearRect(0, 0, width, height);
  const background = context.createLinearGradient(0, 0, 0, height);
  background.addColorStop(0, hexWithAlpha(props.theme.top, 1));
  background.addColorStop(1, hexWithAlpha(props.theme.bottom, 1));
  context.fillStyle = background;
  context.fillRect(0, 0, width, height);

  context.lineWidth = 1;
  context.strokeStyle = "rgba(231,240,237,0.055)";
  context.fillStyle = "rgba(224,235,232,0.46)";
  context.font = "700 10px ui-monospace, SFMono-Regular, Menlo, monospace";
  context.textAlign = "right";
  context.textBaseline = "middle";
  for (const ratio of [0.12, 0.36, 0.60, 0.84]) {
    const gridY = top + (bottom - top) * ratio;
    context.beginPath();
    context.moveTo(left, gridY);
    context.lineTo(right, gridY);
    context.stroke();
    const value = domain.max - span * ratio;
    context.fillText(axisPrice(value, span), width - 7, gridY);
  }
  for (const ratio of [0.25, 0.5, 0.75]) {
    const gridX = left + (right - left) * ratio;
    context.beginPath();
    context.moveTo(gridX, top);
    context.lineTo(gridX, bottom);
    context.stroke();
  }

  overlay(context, props.entry, domain, y, right, props.side === "short" ? "#ff6070" : "#38d39f", "ENTRY");
  overlay(context, props.takeProfit, domain, y, right, "#38d39f", "TP", 0);
  overlay(context, props.stopLoss, domain, y, right, "#ffc166", "SL", 1);
  overlay(context, props.liquidation, domain, y, right, "#ff6070", "LIQ", 2);

  const coordinates = source.map((point) => ({ x: x(point.receivedTs), y: y(point.price) }));
  const lastReal = coordinates.at(-1) ?? { x: right, y: y(props.market.price) };
  // The path and marker always use the real venue price. Only the numeric
  // label is tweened; animation must not invent a rebound at the live edge.
  const edge = { x: right, y: y(props.market.price) };

  context.beginPath();
  traceMonotone(context, coordinates.length === 1 ? [{ x: left, y: coordinates[0].y }, ...coordinates] : coordinates);
  context.lineTo(edge.x, edge.y);
  context.lineTo(edge.x, bottom);
  context.lineTo(coordinates.length === 1 ? left : coordinates[0].x, bottom);
  context.closePath();
  const area = context.createLinearGradient(0, top, 0, bottom);
  area.addColorStop(0, hexWithAlpha(props.theme.accent, 0.05));
  area.addColorStop(0.75, hexWithAlpha(props.theme.accent, 0.018));
  area.addColorStop(1, hexWithAlpha(props.theme.accent, 0));
  context.fillStyle = area;
  context.fill();

  drawLine(context, coordinates, edge, props.theme.glow, 7, 0.085);
  drawLine(context, coordinates, edge, props.theme.accent, 2.25, 1);

  const movementColor = props.market.movePct >= 0 ? "#38d39f" : "#ff6070";
  context.strokeStyle = hexWithAlpha(movementColor, 0.34);
  context.setLineDash([3, 7]);
  context.beginPath();
  context.moveTo(lastReal.x, edge.y);
  context.lineTo(right, edge.y);
  context.stroke();
  context.setLineDash([]);

  const pulse = 4.8 + Math.sin(performance.now() / 170) * 0.8;
  context.fillStyle = hexWithAlpha(props.theme.accent, 0.16);
  context.beginPath();
  context.arc(edge.x, edge.y, pulse + 3, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = movementColor;
  context.beginPath();
  context.arc(edge.x, edge.y, 3.2, 0, Math.PI * 2);
  context.fill();

  const label = price(displayPrice, true);
  context.font = "900 10px -apple-system, BlinkMacSystemFont, sans-serif";
  const tagWidth = Math.max(49, context.measureText(label).width + 18);
  const tagX = right + 4;
  const tagY = clamp(edge.y - 10, top, bottom - 20);
  roundedRect(context, tagX, tagY, tagWidth, 20, 10);
  context.fillStyle = movementColor;
  context.fill();
  context.fillStyle = "#06100e";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(label, tagX + tagWidth / 2, tagY + 10.5);
}

function drawLine(
  context: CanvasRenderingContext2D,
  coordinates: { x: number; y: number }[],
  edge: { x: number; y: number },
  color: string,
  width: number,
  alpha: number
) {
  context.save();
  context.strokeStyle = hexWithAlpha(color, alpha);
  context.lineWidth = width;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.beginPath();
  traceMonotone(context, coordinates.length === 1 ? [{ x: 0, y: coordinates[0].y }, ...coordinates] : coordinates);
  context.lineTo(edge.x, edge.y);
  context.stroke();
  context.restore();
}

function calculateDomain(values: number[], current: number) {
  let min = Math.min(...values, current);
  let max = Math.max(...values, current);
  const steps = values.slice(1).map((value, index) => Math.abs(value - values[index]));
  const averageStep = steps.reduce((sum, value) => sum + value, 0) / Math.max(1, steps.length);
  const minimumSpan = Math.max(current * 0.00002, averageStep * 7, 0.00001);
  if (max - min < minimumSpan) {
    const center = (min + max) / 2;
    min = center - minimumSpan / 2;
    max = center + minimumSpan / 2;
  }
  const padding = (max - min) * 0.17;
  return { min: min - padding, max: max + padding };
}

function stableDomain(
  ref: React.MutableRefObject<Domain | null>,
  market: string,
  target: { min: number; max: number }
) {
  const now = performance.now();
  const current = ref.current;
  if (!current || current.market !== market) {
    ref.current = { ...target, market, lastExtremeAt: now };
    return target;
  }
  const expanded = target.min < current.min || target.max > current.max;
  const contraction = now - current.lastExtremeAt > 2_500 ? 0.018 : 0;
  const next = {
    market,
    min: target.min < current.min ? target.min : current.min + (target.min - current.min) * contraction,
    max: target.max > current.max ? target.max : current.max + (target.max - current.max) * contraction,
    lastExtremeAt: expanded ? now : current.lastExtremeAt
  };
  ref.current = next;
  return next;
}

function overlay(
  context: CanvasRenderingContext2D,
  value: number | null,
  domain: { min: number; max: number },
  y: (value: number) => number,
  right: number,
  color: string,
  label: string,
  edgeSlot = 0
) {
  if (!value || !Number.isFinite(value)) return;
  if (value < domain.min || value > domain.max) {
    context.fillStyle = hexWithAlpha(color, 0.76);
    context.font = "800 9px -apple-system, BlinkMacSystemFont, sans-serif";
    context.textAlign = "left";
    context.textBaseline = value > domain.max ? "top" : "bottom";
    const edgeY = value > domain.max
      ? 25 + edgeSlot * 14
      : context.canvas.height / (window.devicePixelRatio || 1) - 21 - edgeSlot * 14;
    context.fillText(`${label} ${value > domain.max ? "↑" : "↓"}`, 8, edgeY);
    return;
  }
  context.save();
  context.strokeStyle = hexWithAlpha(color, label === "LIQ" ? 0.28 : 0.45);
  context.lineWidth = label === "LIQ" ? 0.8 : 1;
  context.setLineDash(label === "LIQ" ? [2, 8] : [5, 7]);
  context.beginPath();
  context.moveTo(0, y(value));
  context.lineTo(right, y(value));
  context.stroke();
  context.restore();
}

function axisPrice(value: number, span: number): string {
  const decimals = value >= 1000 ? (span < 10 ? 1 : 0) : value >= 1 ? (span < 1 ? 3 : 2) : 5;
  return value.toFixed(decimals);
}

function roundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number
) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
}

function traceMonotone(context: CanvasRenderingContext2D, raw: { x: number; y: number }[]) {
  const points = raw.filter((point, index) => index === 0 || point.x > raw[index - 1].x + 0.01);
  if (!points.length) return;
  context.moveTo(points[0].x, points[0].y);
  if (points.length === 1) return;
  if (points.length === 2) {
    context.lineTo(points[1].x, points[1].y);
    return;
  }

  const delta = points.slice(1).map((point, index) => {
    const dx = point.x - points[index].x;
    return dx > 0 ? (point.y - points[index].y) / dx : 0;
  });
  const slopes = [delta[0]];
  for (let index = 1; index < points.length - 1; index += 1) {
    if (delta[index - 1] * delta[index] <= 0) {
      slopes[index] = 0;
    } else {
      slopes[index] = (delta[index - 1] + delta[index]) / 2;
    }
  }
  slopes[points.length - 1] = delta.at(-1) ?? 0;

  for (let index = 0; index < delta.length; index += 1) {
    if (Math.abs(delta[index]) < 1e-9) {
      slopes[index] = 0;
      slopes[index + 1] = 0;
      continue;
    }
    const a = slopes[index] / delta[index];
    const b = slopes[index + 1] / delta[index];
    const magnitude = Math.hypot(a, b);
    if (magnitude > 3) {
      const scale = 3 / magnitude;
      slopes[index] = scale * a * delta[index];
      slopes[index + 1] = scale * b * delta[index];
    }
  }

  for (let index = 0; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    const dx = next.x - current.x;
    context.bezierCurveTo(
      current.x + dx / 3,
      current.y + slopes[index] * dx / 3,
      next.x - dx / 3,
      next.y - slopes[index + 1] * dx / 3,
      next.x,
      next.y
    );
  }
}

function hexWithAlpha(hex: string, alpha: number): string {
  if (!hex.startsWith("#")) return hex;
  const clean = hex.slice(1);
  const value = clean.length === 3 ? clean.split("").map((character) => character + character).join("") : clean;
  const red = Number.parseInt(value.slice(0, 2), 16);
  const green = Number.parseInt(value.slice(2, 4), 16);
  const blue = Number.parseInt(value.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
