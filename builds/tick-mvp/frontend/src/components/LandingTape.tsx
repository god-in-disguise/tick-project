import { useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { Market, MarketObservation } from "../types";

const WINDOW_SECONDS = 90;

export function LandingTape() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sequenceRef = useRef(0);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [observations, setObservations] = useState<MarketObservation[]>([]);

  useEffect(() => {
    let active = true;
    api.markets()
      .then((next) => {
        if (!active || next.length === 0) return;
        const distinct = next.filter(
          (market, index) => next.findIndex((candidate) => candidate.symbol === market.symbol) === index
        ).slice(0, 3);
        setMarkets(distinct);
        setSelected((current) => current ?? distinct[0]?.market ?? null);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    let active = true;

    const bootstrap = async () => {
      try {
        const chart = await api.chart(selected);
        if (!active) return;
        sequenceRef.current = chart.sequence;
        setObservations(chart.observations);
      } catch {
        // The landing remains usable when the public tape is temporarily unavailable.
      }
    };

    const update = async () => {
      try {
        const tape = await api.tape(selected, sequenceRef.current);
        if (!active) return;
        if (tape.resyncRequired) {
          await bootstrap();
          return;
        }
        sequenceRef.current = tape.sequence;
        if (tape.observations.length === 0) return;
        setObservations((current) => trimObservations([...current, ...tape.observations]));
      } catch {
        // The next interval retries without replacing the last truthful frame.
      }
    };

    setObservations([]);
    sequenceRef.current = 0;
    void bootstrap();
    const interval = window.setInterval(() => void update(), 700);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [selected]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const draw = () => drawTape(canvas, observations);
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    draw();
    return () => observer.disconnect();
  }, [observations]);

  const activeMarket = markets.find((market) => market.market === selected) ?? markets[0] ?? null;

  return (
    <section className="landing-live-stage" aria-label="Live market preview">
      <div className="landing-live-meta">
        <span><i /> LIVE TAPE</span>
        {activeMarket ? (
          <strong>
            {activeMarket.symbol}
            <b>{formatPrice(activeMarket.price)}</b>
          </strong>
        ) : (
          <strong>CONNECTING</strong>
        )}
      </div>
      <canvas ref={canvasRef} aria-hidden="true" />
      <div className="landing-market-tabs" aria-label="Preview market">
        {markets.map((market) => (
          <button
            key={market.market}
            className={market.market === selected ? "active" : ""}
            type="button"
            onClick={() => setSelected(market.market)}
          >
            <strong>{market.symbol}</strong>
            <span className={market.movePct >= 0 ? "positive" : "negative"}>
              {market.movePct >= 0 ? "+" : ""}{market.movePct.toFixed(2)}%
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function trimObservations(observations: MarketObservation[]): MarketObservation[] {
  if (observations.length === 0) return observations;
  const end = observations[observations.length - 1].receivedTs;
  const start = end - WINDOW_SECONDS;
  return observations.filter((observation) => observation.receivedTs >= start).slice(-360);
}

function drawTape(canvas: HTMLCanvasElement, source: MarketObservation[]): void {
  const rect = canvas.getBoundingClientRect();
  const scale = Math.min(window.devicePixelRatio || 1, 3);
  const width = Math.max(1, Math.round(rect.width * scale));
  const height = Math.max(1, Math.round(rect.height * scale));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const context = canvas.getContext("2d");
  if (!context) return;
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);

  context.strokeStyle = "rgba(243, 243, 239, 0.07)";
  context.lineWidth = 0.5;
  for (let index = 1; index < 4; index += 1) {
    const x = (rect.width / 4) * index;
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, rect.height);
    context.stroke();
  }
  for (let index = 1; index < 3; index += 1) {
    const y = (rect.height / 3) * index;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(rect.width, y);
    context.stroke();
  }

  const points = trimObservations(source).filter((point) => Number.isFinite(point.price));
  if (points.length < 2) return;
  const end = points[points.length - 1].receivedTs;
  const start = end - WINDOW_SECONDS;
  const prices = points.map((point) => point.price);
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  const rawSpan = Math.max(high - low, Math.abs(high) * 0.00008, 0.00001);
  const domainLow = low - rawSpan * 0.18;
  const domainHigh = high + rawSpan * 0.18;
  const domainSpan = domainHigh - domainLow;

  const coordinates = points.map((point) => ({
    x: ((point.receivedTs - start) / Math.max(1, end - start)) * rect.width,
    y: rect.height - ((point.price - domainLow) / domainSpan) * rect.height
  }));

  context.beginPath();
  coordinates.forEach((point, index) => {
    if (index === 0) context.moveTo(point.x, point.y);
    else context.lineTo(point.x, point.y);
  });
  const last = coordinates[coordinates.length - 1];
  context.lineTo(last.x, rect.height);
  context.lineTo(coordinates[0].x, rect.height);
  context.closePath();
  context.fillStyle = "rgba(204, 204, 216, 0.045)";
  context.fill();

  context.beginPath();
  coordinates.forEach((point, index) => {
    if (index === 0) context.moveTo(point.x, point.y);
    else context.lineTo(point.x, point.y);
  });
  context.strokeStyle = "#c9c8d4";
  context.lineWidth = 2;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.shadowColor = "rgba(201, 200, 212, 0.22)";
  context.shadowBlur = 8;
  context.stroke();
  context.shadowBlur = 0;

  context.beginPath();
  context.arc(last.x, last.y, 4, 0, Math.PI * 2);
  context.fillStyle = "#ff922b";
  context.fill();
}

function formatPrice(value: number): string {
  if (value >= 1000) return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (value >= 10) return value.toFixed(2);
  return value.toFixed(4);
}
