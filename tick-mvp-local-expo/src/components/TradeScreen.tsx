import React, { useEffect, useMemo, useRef, useState } from "react";
import { Animated, PanResponder, Pressable, Text, View } from "react-native";

import {
  directionForSide,
  formatMoney,
  formatPercent,
  formatPrice,
  formatSignedMoney,
  liquidationDistance,
  sideForDirection
} from "../market";
import type { Direction, Execution, FeedStatus, Market, Position, Quotes } from "../types";
import { styles } from "../styles";
import { PriceChart } from "./PriceChart";

type ClosedResult = {
  id: string;
  pair: string;
  pnl: number | null;
  grossPnl: number | null;
  costDrag: number | null;
  durationSeconds: number;
  label: string;
} | null;

type Props = {
  market: Market;
  balance: number;
  leverage: number;
  position: Position | null;
  execution: Execution | null;
  submitting: "long" | "short" | "close" | null;
  quotes: Quotes;
  closedResult: ClosedResult;
  error: string | null;
  tapeStale: boolean;
  tapeStatus: FeedStatus;
  onOpen: (direction: Direction) => void;
  onClose: () => void;
  onNext: () => void;
  onPrevious: () => void;
};

type Cue = "LONG" | "SHORT" | "CLOSE" | "NEXT" | "PREV" | "WAIT" | "LOCKED";

export function TradeScreen(props: Props) {
  const { market, position, execution, quotes } = props;
  const [cue, setCue] = useState<Cue | null>(null);
  const cueOpacity = useRef(new Animated.Value(0)).current;
  const resultOpacity = useRef(new Animated.Value(0)).current;
  const busy = props.submitting !== null || execution?.status === "created" || execution?.status === "opening" || execution?.status === "closing" || execution?.status === "unknown";
  const closing = props.submitting === "close" || execution?.action === "close" && busy;
  const marketQuotes: Quotes = {
    long: quotes.long?.pair === market.pair && quotes.long.leverage === props.leverage ? quotes.long : null,
    short: quotes.short?.pair === market.pair && quotes.short.leverage === props.leverage ? quotes.short : null
  };
  const openingQuote = marketQuotes.long ?? marketQuotes.short;
  const cost = openingQuote?.estimatedAllInCostUsd ?? 0;
  const tape = market.activeTapePct ?? 0;
  const marketState = market.feedLabel === "Watching" ? "Live tape" : market.feedLabel;
  const gestureContext = useRef({
    position,
    busy,
    quotes: marketQuotes,
    onOpen: props.onOpen,
    onClose: props.onClose,
    onNext: props.onNext,
    onPrevious: props.onPrevious
  });
  gestureContext.current = {
    position,
    busy,
    quotes: marketQuotes,
    onOpen: props.onOpen,
    onClose: props.onClose,
    onNext: props.onNext,
    onPrevious: props.onPrevious
  };

  useEffect(() => {
    if (!props.closedResult) {
      resultOpacity.stopAnimation();
      resultOpacity.setValue(0);
      return;
    }
    resultOpacity.stopAnimation();
    resultOpacity.setValue(0);
    Animated.timing(resultOpacity, { toValue: 1, duration: 130, useNativeDriver: true }).start();
  }, [props.closedResult, resultOpacity]);

  function flash(next: Cue) {
    setCue(next);
    cueOpacity.stopAnimation();
    cueOpacity.setValue(0);
    Animated.sequence([
      Animated.timing(cueOpacity, { toValue: 1, duration: 90, useNativeDriver: true }),
      Animated.timing(cueOpacity, { toValue: 0, delay: 190, duration: 300, useNativeDriver: true })
    ]).start(() => setCue(null));
  }

  const gestures = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponderCapture: (_, gesture) => Math.abs(gesture.dx) > 6 || Math.abs(gesture.dy) > 6,
        onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dx) > 6 || Math.abs(gesture.dy) > 6,
        onPanResponderTerminationRequest: () => false,
        onPanResponderRelease: (_, gesture) => {
          const current = gestureContext.current;
          const horizontal = Math.abs(gesture.dx);
          const vertical = Math.abs(gesture.dy);

          if (horizontal > 36 && horizontal > vertical * 1.15) {
            if (current.position || current.busy) {
              flash("LOCKED");
              return;
            }
            if (gesture.dx < 0) {
              flash("NEXT");
              current.onNext();
            } else {
              flash("PREV");
              current.onPrevious();
            }
            return;
          }

          if (vertical <= 42 || vertical <= horizontal * 1.12) return;
          if (current.busy) {
            flash("WAIT");
            return;
          }

          const direction: Direction = gesture.dy < 0 ? "up" : "down";
          if (current.position) {
            if (directionForSide(current.position.side) !== direction) {
              flash("LOCKED");
              return;
            }
            flash("CLOSE");
            current.onClose();
            return;
          }

          const quote = direction === "up" ? current.quotes.long : current.quotes.short;
          if (quote && !quote.openingAllowed) {
            flash("WAIT");
            return;
          }
          flash(direction === "up" ? "LONG" : "SHORT");
          current.onOpen(direction);
        }
      }),
    []
  );

  return (
    <View style={[styles.tradeScreen, { backgroundColor: market.theme.top }]} {...gestures.panHandlers}>
      <View style={styles.tradeHeader}>
        <View style={styles.brandRow}>
          <Text style={styles.brand}>TICK</Text>
          <View style={styles.marketTitle}>
            <View style={styles.marketTitleLine}>
              <Text style={styles.symbol}>{market.symbol}</Text>
              <Text style={[styles.leverage, { color: market.theme.glow }]}>{props.leverage}x</Text>
              <Text style={styles.assetName}>{market.name}</Text>
            </View>
            <View style={styles.priceLine}>
              <Text style={styles.headerPrice}>{formatPrice(market.price)}</Text>
              <Text style={[styles.headerMove, market.move >= 0 ? styles.positive : styles.negative]}>
                {formatPercent(market.move)}
              </Text>
            </View>
          </View>
        </View>
        <View style={styles.balancePill}>
          <Text style={styles.balanceLabel}>Balance</Text>
          <Text style={styles.balanceValue}>{formatMoney(props.balance)}</Text>
        </View>
      </View>

      <View style={styles.chartWrap}>
        <PriceChart
          market={market}
          entry={position?.entry}
          liquidation={position?.estimatedLiquidationPrice}
          direction={position ? directionForSide(position.side) : undefined}
        />

        <View pointerEvents="none" style={styles.marketBadge}>
          <View style={styles.badgeTopLine}>
            <Text style={[styles.assetClass, { color: market.theme.glow }]}>{market.assetClass}</Text>
            {openingQuote?.marketOpen ? <Text style={styles.testBadge}>LIVE</Text> : null}
            {props.tapeStatus !== "live" ? <Text style={styles.staleBadge}>{tapeBadge(props.tapeStatus)}</Text> : null}
          </View>
          <Text style={styles.marketState}>{marketState}</Text>
          <Text style={styles.marketMetrics}>MOVE {formatPercent(tape)} · COST {formatPercent(costToMove(openingQuote))}</Text>
        </View>

        {position ? (
          <View pointerEvents="none" style={styles.pnlBadge}>
            <Text style={styles.pnlMeta}>{closing ? "CLOSING" : position.optimistic ? "PENDING" : position.indexing ? "LIVE" : position.side.toUpperCase()} · {position.leverage}x</Text>
            {closing ? (
              <Text style={styles.pendingValue}>Exiting</Text>
            ) : (
              <Text style={[styles.pnlValue, position.estimatedNetPnl >= 0 ? styles.positive : styles.negative]}>
                {formatSignedMoney(position.estimatedNetPnl)}
              </Text>
            )}
            <Text style={styles.pnlEstimate}>
              {closing
                ? "market close sent"
                : position.optimistic
                  ? "venue confirmation"
                  : props.tapeStatus !== "live"
                    ? "venue mark fallback"
                    : position.indexing
                      ? "callback confirmed"
                      : "estimated net"}
            </Text>
          </View>
        ) : execution?.status === "opening" || props.submitting === "long" || props.submitting === "short" ? (
          <View pointerEvents="none" style={styles.pnlBadge}>
            <Text style={styles.pnlMeta}>{(execution?.side ?? props.submitting)?.toUpperCase()} · {execution?.leverage ?? props.leverage}x</Text>
            <Text style={styles.pendingValue}>Opening</Text>
          </View>
        ) : null}

        {cue ? (
          <Animated.View pointerEvents="none" style={[styles.gestureCue, { opacity: cueOpacity }]}>
            <Text style={[styles.gestureCueText, cue === "SHORT" ? styles.negative : cue === "LONG" ? styles.positive : undefined]}>
              {cue}
            </Text>
          </Animated.View>
        ) : null}

        {props.closedResult ? (
          <Animated.View pointerEvents="none" style={[styles.closedCard, { opacity: resultOpacity }]}>
            <Text style={styles.closedLabel}>{props.closedResult.label}</Text>
            <Text
              style={[
                styles.closedPnl,
                props.closedResult.pnl === null
                  ? styles.closedSettling
                  : props.closedResult.pnl >= 0
                    ? styles.positive
                    : styles.negative
              ]}
            >
              {props.closedResult.pnl === null ? "Settling" : formatSignedMoney(props.closedResult.pnl)}
            </Text>
            <View style={styles.closedBreakdown}>
              <ResultMetric
                label="Gross"
                value={props.closedResult.grossPnl === null ? "--" : formatSignedMoney(props.closedResult.grossPnl)}
                tone={props.closedResult.grossPnl}
              />
              <ResultMetric
                label="Costs"
                value={formatCostDrag(props.closedResult.costDrag)}
                tone={props.closedResult.costDrag === null ? null : -Math.abs(props.closedResult.costDrag)}
              />
              <ResultMetric
                label="Net"
                value={props.closedResult.pnl === null ? "--" : formatSignedMoney(props.closedResult.pnl)}
                tone={props.closedResult.pnl}
              />
            </View>
            <Text style={styles.closedMeta}>{props.closedResult.pair} · {formatDuration(props.closedResult.durationSeconds)}</Text>
          </Animated.View>
        ) : null}

        {props.error ? (
          <View style={styles.errorToast}>
            <Text numberOfLines={2} style={styles.errorText}>{props.error}</Text>
          </View>
        ) : null}

        <View style={styles.executionDock}>
          <View style={styles.termRow}>
            {position ? (
              <>
                <Term label="Entry" value={formatPrice(position.entry)} />
                <Term label="Now" value={formatPrice(position.mark)} />
                <Term
                  label="Liq"
                  value={position.estimatedLiquidationPrice ? formatPrice(position.estimatedLiquidationPrice) : liquidationDistance(position.entry, position.estimatedLiquidationPrice)}
                />
                <Term label="Away" value={liquidationDistance(position.entry, position.estimatedLiquidationPrice)} />
              </>
            ) : (
              <>
                <Term label="Ticket" value={formatMoney(openingQuote?.ticketUsd ?? 20)} />
                <Term label="Exposure" value={compactMoney(openingQuote?.notionalUsd ?? 20 * props.leverage)} />
                <Term label="Cost" value={openingQuote ? formatMoney(openingQuote.estimatedAllInCostUsd) : "--"} />
                <Term label="Risk" value={formatMoney(openingQuote?.collateralAtRiskUsd ?? 20)} />
              </>
            )}
          </View>
          {position ? (
            <Pressable disabled={busy} onPress={props.onClose} style={[styles.closeButton, busy && styles.closeButtonDisabled]}>
              <Text style={styles.closeButtonText}>
                {position.optimistic ? "Confirming" : closing ? "Closing" : "Close"}
              </Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    </View>
  );
}

function Term({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.term}>
      <Text style={styles.termLabel}>{label}</Text>
      <Text numberOfLines={1} style={styles.termValue}>{value}</Text>
    </View>
  );
}

function ResultMetric({ label, value, tone }: { label: string; value: string; tone: number | null }) {
  return (
    <View style={styles.resultMetric}>
      <Text style={styles.resultMetricLabel}>{label}</Text>
      <Text
        numberOfLines={1}
        style={[
          styles.resultMetricValue,
          tone === null ? undefined : tone >= 0 ? styles.positive : styles.negative
        ]}
      >
        {value}
      </Text>
    </View>
  );
}

function tapeBadge(status: FeedStatus): string {
  if (status === "delayed") return "DELAYED";
  if (status === "disconnected") return "NO TAPE";
  if (status === "resyncing") return "SYNC";
  return "STALE";
}

function costToMove(quote: Quotes["long"]): number {
  return quote?.feeHurdlePct ?? 0;
}

function compactMoney(value: number): string {
  if (value >= 1000) return `$${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k`;
  return formatMoney(value);
}

function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(Math.max(0, seconds % 60)).padStart(2, "0")}`;
}

function formatCostDrag(value: number | null): string {
  if (value === null) return "--";
  if (Math.abs(value) < 0.005) return "$0.00";
  return value >= 0 ? `-${formatMoney(value)}` : `+${formatMoney(Math.abs(value))}`;
}
