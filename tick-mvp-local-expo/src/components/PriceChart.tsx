import React from "react";
import { View } from "react-native";
import Svg, { Circle, Defs, Line, LinearGradient, Path, Rect, Stop, Text as SvgText } from "react-native-svg";

import { clamp, formatAxisPrice } from "../market";
import type { Direction, Market } from "../types";
import { styles } from "../styles";

type Props = {
  market: Market;
  entry?: number;
  liquidation?: number | null;
  direction?: Direction;
};

export function PriceChart({ market, entry, liquidation, direction }: Props) {
  const chart = buildChart(market.points, market.price, entry, liquidation);
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

        {chart.entryY !== null ? (
          <Line
            x1={chart.left}
            y1={chart.entryY}
            x2={chart.right}
            y2={chart.entryY}
            stroke={direction === "up" ? "rgba(56,211,159,0.42)" : "rgba(255,96,112,0.42)"}
            strokeDasharray="5 7"
            strokeWidth="1.15"
          />
        ) : null}
        {chart.liquidationY !== null ? (
          <Line
            x1={chart.left}
            y1={chart.liquidationY}
            x2={chart.right}
            y2={chart.liquidationY}
            stroke="rgba(255,96,112,0.26)"
            strokeDasharray="2 8"
            strokeWidth="0.8"
          />
        ) : null}

        <Path d={chart.areaPath} fill="url(#chart-area)" />
        <Path d={chart.path} fill="none" stroke={market.theme.glow} strokeOpacity="0.12" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
        <Path d={chart.path} fill="none" stroke={market.theme.accent} strokeWidth="2.15" strokeLinecap="round" strokeLinejoin="round" />
        <Line x1={chart.left} y1={chart.last.y} x2={chart.right} y2={chart.last.y} stroke={movementColor} strokeOpacity="0.16" strokeDasharray="3 7" />
        <Line x1={chart.last.x} y1={chart.last.y} x2={chart.right + 1} y2={chart.last.y} stroke={movementColor} strokeOpacity="0.62" />
        <Rect x={chart.right + 1} y={chart.priceTagY} width="48" height="16" rx="8" fill={movementColor} />
        <SvgText x={chart.right + 25} y={chart.priceTagY + 10.8} textAnchor="middle" fill="#04110e" fontSize="6.8" fontWeight="900">
          {formatAxisPrice(market.price, chart.span)}
        </SvgText>
        <Circle cx={chart.last.x} cy={chart.last.y} r="6" fill={market.theme.accent} opacity="0.15" />
        <Circle cx={chart.last.x} cy={chart.last.y} r="3.2" fill={movementColor} />
      </Svg>
    </View>
  );
}

function buildChart(points: number[], currentPrice: number, entry?: number, liquidation?: number | null) {
  const top = 24;
  const bottom = 406;
  const left = 6;
  const right = 310;
  const clean = [...points, currentPrice].filter((point) => Number.isFinite(point) && point > 0).slice(-240);
  const source = clean.length > 1 ? clean : [currentPrice, currentPrice];
  const visible = source.length > 20 ? smooth(source) : source;
  const range = [entry, liquidation].filter((value): value is number => Number.isFinite(value)).length
    ? [...visible, currentPrice, ...(entry ? [entry] : []), ...(liquidation ? [liquidation] : [])]
    : [...visible, currentPrice];
  let min = Math.min(...range);
  let max = Math.max(...range);
  const averageStep = visible.slice(1).reduce((sum, point, index) => sum + Math.abs(point - visible[index]), 0) / Math.max(1, visible.length - 1);
  const minimumSpan = Math.max(currentPrice * 0.000025, averageStep * 6, 0.00001);
  if (max - min < minimumSpan) {
    const center = (max + min) / 2;
    min = center - minimumSpan / 2;
    max = center + minimumSpan / 2;
  }
  const padding = (max - min) * 0.12;
  min -= padding;
  max += padding;
  const span = Math.max(max - min, minimumSpan);
  const toY = (value: number) => clamp(bottom - ((value - min) / span) * (bottom - top), top, bottom);
  const coordinates = visible.map((point, index) => ({
    x: left + (index / Math.max(1, visible.length - 1)) * (right - left),
    y: toY(point)
  }));
  const path = smoothPath(coordinates);
  const first = coordinates[0] ?? { x: left, y: bottom };
  const last = coordinates[coordinates.length - 1] ?? { x: right, y: toY(currentPrice) };
  const areaPath = `${path} L ${last.x} ${bottom} L ${first.x} ${bottom} Z`;
  const ticks = [0.82, 0.58, 0.34, 0.10].map((ratio) => {
    const value = min + span * ratio;
    return { y: toY(value), label: formatAxisPrice(value, span) };
  });
  return {
    path,
    areaPath,
    last,
    left,
    right,
    ticks,
    span,
    entryY: entry ? toY(entry) : null,
    liquidationY: liquidation ? toY(liquidation) : null,
    priceTagY: clamp(last.y - 9, top, bottom - 18)
  };
}

function smooth(points: number[]) {
  return points.map((point, index) => {
    const previous = points[index - 1] ?? point;
    const next = points[index + 1] ?? point;
    return previous * 0.025 + point * 0.95 + next * 0.025;
  });
}

function smoothPath(points: { x: number; y: number }[]) {
  if (!points.length) return "";
  let path = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
  for (let index = 1; index < points.length - 1; index += 1) {
    const current = points[index];
    const next = points[index + 1];
    path += ` Q ${current.x.toFixed(2)} ${current.y.toFixed(2)}, ${((current.x + next.x) / 2).toFixed(2)} ${((current.y + next.y) / 2).toFixed(2)}`;
  }
  const last = points[points.length - 1];
  return `${path} L ${last.x.toFixed(2)} ${last.y.toFixed(2)}`;
}
