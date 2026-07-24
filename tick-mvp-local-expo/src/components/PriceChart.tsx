import React, { useEffect, useRef, useState } from "react";
import { View } from "react-native";
import Svg, { Circle, Defs, Line, LinearGradient, Path, Rect, Stop, Text as SvgText } from "react-native-svg";

import { CHART_WINDOW_SECONDS } from "../config";
import { clamp, formatAxisPrice } from "../market";
import type { ChartPoint, Direction, Market } from "../types";
import { styles } from "../styles";

type Props = {
  market: Market;
  entry?: number;
  stopLoss?: number | null;
  liquidation?: number | null;
  direction?: Direction;
};

export function PriceChart({ market, entry, stopLoss, liquidation, direction }: Props) {
  const displayPrice = useRenderedPrice(market.price, market.pair);
  const domainRef = useRef<StableDomain | null>(null);
  const clockRef = useRef<number | null>(null);
  const domainPairRef = useRef(market.pair);
  if (domainPairRef.current !== market.pair) {
    domainPairRef.current = market.pair;
    domainRef.current = null;
    clockRef.current = null;
  }
  const chart = buildChart(market.chartPoints, market.points, market.price, displayPrice, entry, stopLoss, liquidation, domainRef, clockRef);
  const movementColor = market.move >= 0 ? "#38d39f" : "#ff6070";

  return (
    <View style={styles.chart}>
      <Svg width="100%" height="100%" viewBox="0 0 360 440" preserveAspectRatio="none">
        <Defs>
          <LinearGradient id="chart-background" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={market.theme.top} stopOpacity="0.35" />
            <Stop offset="1" stopColor={market.theme.bottom} stopOpacity="0.18" />
          </LinearGradient>
          <LinearGradient id="chart-area" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={market.theme.accent} stopOpacity="0.17" />
            <Stop offset="0.72" stopColor={market.theme.accent} stopOpacity="0.03" />
            <Stop offset="1" stopColor={market.theme.accent} stopOpacity="0" />
          </LinearGradient>
        </Defs>

        <Rect x="0" y="0" width="360" height="440" fill="url(#chart-background)" />
        {chart.ticks.map((tick, index) => (
          <React.Fragment key={`${index}-${tick.y.toFixed(2)}`}>
            <Line x1={chart.left} y1={tick.y} x2={chart.right} y2={tick.y} stroke="rgba(255,255,255,0.05)" strokeWidth="1" />
            <SvgText x="352" y={tick.y + 3} textAnchor="end" fill="rgba(225,235,232,0.48)" fontSize="8" fontWeight="700">
              {tick.label}
            </SvgText>
          </React.Fragment>
        ))}
        {[102, 198].map((x) => (
          <Line key={x} x1={x} y1="22" x2={x} y2="408" stroke="rgba(255,255,255,0.025)" strokeWidth="1" />
        ))}

        {chart.entryLine ? (
          <Line
            x1={chart.left}
            y1={chart.entryLine.y}
            x2={chart.right}
            y2={chart.entryLine.y}
            stroke={direction === "up" ? "rgba(56,211,159,0.42)" : "rgba(255,96,112,0.42)"}
            strokeDasharray="5 7"
            strokeWidth="1.15"
          />
        ) : null}
        {chart.liquidationLine ? (
          <Line
            x1={chart.left}
            y1={chart.liquidationLine.y}
            x2={chart.right}
            y2={chart.liquidationLine.y}
            stroke="rgba(255,96,112,0.26)"
            strokeDasharray="2 8"
            strokeWidth="0.8"
          />
        ) : null}
        {chart.stopLossLine ? (
          <Line
            x1={chart.left}
            y1={chart.stopLossLine.y}
            x2={chart.right}
            y2={chart.stopLossLine.y}
            stroke="rgba(255,193,102,0.5)"
            strokeDasharray="4 6"
            strokeWidth="1.05"
          />
        ) : null}
        {chart.entryEdge ? (
          <SvgText x={chart.left + 2} y={chart.entryEdge.y} fill="rgba(225,235,232,0.46)" fontSize="7" fontWeight="900">
            ENTRY {chart.entryEdge.direction}
          </SvgText>
        ) : null}
        {chart.liquidationEdge ? (
          <SvgText x={chart.left + 2} y={chart.liquidationEdge.y} fill="rgba(255,96,112,0.58)" fontSize="7" fontWeight="900">
            LIQ {chart.liquidationEdge.direction}
          </SvgText>
        ) : null}
        {chart.stopLossEdge ? (
          <SvgText x={chart.left + 2} y={chart.stopLossEdge.y} fill="rgba(255,193,102,0.72)" fontSize="7" fontWeight="900">
            SL {chart.stopLossEdge.direction}
          </SvgText>
        ) : null}

        <Path d={chart.areaPath} fill="url(#chart-area)" />
        <Path d={chart.path} fill="none" stroke={market.theme.glow} strokeOpacity="0.12" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        <Path d={chart.path} fill="none" stroke={market.theme.accent} strokeWidth="2.15" strokeLinecap="round" strokeLinejoin="round" />
        <Line x1={chart.left} y1={chart.last.y} x2={chart.right} y2={chart.last.y} stroke={movementColor} strokeOpacity="0.16" strokeDasharray="3 7" />
        <Line x1={chart.last.x} y1={chart.last.y} x2={chart.right + 1} y2={chart.last.y} stroke={movementColor} strokeOpacity="0.62" />
        <Rect x={chart.right + 1} y={chart.priceTagY} width="48" height="16" rx="8" fill={movementColor} />
        <SvgText x={chart.right + 25} y={chart.priceTagY + 10.8} textAnchor="middle" fill="#04110e" fontSize="6.8" fontWeight="900">
          {formatAxisPrice(displayPrice, chart.span)}
        </SvgText>
        <Circle cx={chart.last.x} cy={chart.last.y} r="6" fill={market.theme.accent} opacity="0.15" />
        <Circle cx={chart.last.x} cy={chart.last.y} r="3.2" fill={movementColor} />
      </Svg>
    </View>
  );
}

function useRenderedPrice(targetPrice: number, resetKey: string) {
  const [displayPrice, setDisplayPrice] = useState(targetPrice);
  const currentRef = useRef(targetPrice);
  const keyRef = useRef(resetKey);
  const frameRef = useRef<number | null>(null);
  const reset = keyRef.current !== resetKey;
  if (reset) {
    keyRef.current = resetKey;
    currentRef.current = targetPrice;
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
  }

  useEffect(() => {
    if (!Number.isFinite(targetPrice) || targetPrice <= 0) return;
    const from = currentRef.current || targetPrice;
    const started = Date.now();
    const durationMs = 170;

    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);

    const step = () => {
      const elapsed = Date.now() - started;
      const progress = clamp(elapsed / durationMs, 0, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const next = from + (targetPrice - from) * eased;
      currentRef.current = next;
      setDisplayPrice(next);
      if (progress < 1) frameRef.current = requestAnimationFrame(step);
    };

    frameRef.current = requestAnimationFrame(step);
    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [targetPrice, resetKey]);

  return reset ? targetPrice : displayPrice;
}

function buildChart(
  chartPoints: ChartPoint[],
  fallbackPoints: number[],
  currentPrice: number,
  displayPrice: number,
  entry?: number,
  stopLoss?: number | null,
  liquidation?: number | null,
  domainRef?: React.MutableRefObject<StableDomain | null>,
  clockRef?: React.MutableRefObject<number | null>
) {
  const top = 24;
  const bottom = 406;
  const left = 6;
  const right = 310;
  const renderNow = Date.now() / 1000;
  const latestSourceTime = chartPoints.reduce((latest, point) => Math.max(latest, point.time), 0);
  const sourceClock = latestSourceTime || renderNow;
  const previousClock = clockRef?.current;
  const now = previousClock === null || previousClock === undefined
    ? sourceClock
    : latestSourceTime > previousClock + 0.001
      ? latestSourceTime
      : previousClock;
  if (clockRef) clockRef.current = now;
  const source = normalizeChartPoints(chartPoints, fallbackPoints, currentPrice, now);
  const xMin = now - CHART_WINDOW_SECONDS;
  const xMax = now;
  const visible = source.filter((point) => point.time >= xMin && point.time <= xMax);
  const display = visible.length >= 2 ? visible : source.slice(-2);
  const lastSource = display[display.length - 1] ?? { time: now, price: currentPrice };
  const lastDisplay = Math.abs(lastSource.price - displayPrice) > 0.0000001
    ? { time: now, price: displayPrice }
    : { time: now, price: lastSource.price, unchanged: true };
  const displayPoints = [...display.filter((point) => point.time < now - 0.05), lastDisplay];
  const domainPoints = [...display, { time: now, price: currentPrice }];
  const range = domainPoints.map((point) => point.price);
  let min = Math.min(...range);
  let max = Math.max(...range);
  const averageStep = domainPoints
    .slice(1)
    .reduce((sum, point, index) => sum + Math.abs(point.price - domainPoints[index].price), 0) / Math.max(1, domainPoints.length - 1);
  const minimumSpan = Math.max(currentPrice * 0.000018, averageStep * 7, 0.00001);
  if (max - min < minimumSpan) {
    const center = (max + min) / 2;
    min = center - minimumSpan / 2;
    max = center + minimumSpan / 2;
  }
  const padding = (max - min) * 0.16;
  min -= padding;
  max += padding;
  if (domainRef) {
    const domain = stabilizeDomain({ min, max }, domainRef);
    min = domain.min;
    max = domain.max;
  }
  const span = Math.max(max - min, minimumSpan);
  const rawY = (value: number) => bottom - ((value - min) / span) * (bottom - top);
  const toY = (value: number) => clamp(rawY(value), top, bottom);
  const toX = (time: number) => left + clamp((time - xMin) / Math.max(0.001, xMax - xMin), 0, 1) * (right - left);
  const coordinates = displayPoints.map((point) => ({
    x: toX(point.time),
    y: toY(point.price)
  }));
  const path = linePath(coordinates);
  const first = coordinates[0] ?? { x: left, y: bottom };
  const last = coordinates[coordinates.length - 1] ?? { x: right, y: toY(currentPrice) };
  const areaPath = `${path} L ${last.x} ${bottom} L ${first.x} ${bottom} Z`;
  const ticks = [0.82, 0.58, 0.34, 0.10].map((ratio) => {
    const value = min + span * ratio;
    return { y: toY(value), label: formatAxisPrice(value, span) };
  });
  const entryOverlay = overlay(entry, rawY(entry ?? NaN), top, bottom);
  const stopLossOverlay = overlay(stopLoss ?? undefined, rawY(stopLoss ?? NaN), top, bottom);
  const liquidationOverlay = overlay(liquidation ?? undefined, rawY(liquidation ?? NaN), top, bottom);
  return {
    path,
    areaPath,
    last,
    left,
    right,
    ticks,
    span,
    entryLine: entryOverlay.line,
    entryEdge: entryOverlay.edge,
    stopLossLine: stopLossOverlay.line,
    stopLossEdge: stopLossOverlay.edge,
    liquidationLine: liquidationOverlay.line,
    liquidationEdge: liquidationOverlay.edge,
    priceTagY: clamp(last.y - 9, top, bottom - 18)
  };
}

type StableDomain = {
  min: number;
  max: number;
  updatedAt: number;
};

function stabilizeDomain(next: { min: number; max: number }, ref: React.MutableRefObject<StableDomain | null>) {
  const now = Date.now();
  const current = ref.current;
  if (!current || !Number.isFinite(next.min) || !Number.isFinite(next.max) || next.max <= next.min) {
    ref.current = { ...next, updatedAt: now };
    return next;
  }

  const elapsed = Math.max(16, now - current.updatedAt);
  const contraction = clamp(elapsed / 3200, 0, 1);
  const min = next.min < current.min ? next.min : current.min + (next.min - current.min) * contraction;
  const max = next.max > current.max ? next.max : current.max + (next.max - current.max) * contraction;
  ref.current = { min, max, updatedAt: now };
  return { min, max };
}

function linePath(points: { x: number; y: number }[]) {
  if (!points.length) return "";
  let path = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let index = 1; index < points.length; index += 1) {
    path += ` L ${points[index].x.toFixed(2)} ${points[index].y.toFixed(2)}`;
  }
  return path;
}

function overlay(value: number | undefined, y: number, top: number, bottom: number) {
  if (!value || !Number.isFinite(value) || !Number.isFinite(y)) return { line: null, edge: null };
  if (y < top) return { line: null, edge: { y: top + 11, direction: "UP" } };
  if (y > bottom) return { line: null, edge: { y: bottom - 5, direction: "DOWN" } };
  return { line: { y }, edge: null };
}

function normalizeChartPoints(chartPoints: ChartPoint[], fallbackPoints: number[], currentPrice: number, now: number): ChartPoint[] {
  const clean = chartPoints
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.price) && point.price > 0)
    .sort((a, b) => a.time - b.time || (a.seq ?? 0) - (b.seq ?? 0));
  if (clean.length >= 2) return clean;
  const fallback = fallbackPoints.filter((point) => Number.isFinite(point) && point > 0);
  const source = fallback.length >= 2 ? fallback : [currentPrice, currentPrice];
  const count = Math.max(1, source.length - 1);
  return source.map((price, index) => ({
    time: now - CHART_WINDOW_SECONDS + (index / count) * CHART_WINDOW_SECONDS,
    price
  }));
}
