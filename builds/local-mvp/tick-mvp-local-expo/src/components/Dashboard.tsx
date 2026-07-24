import React, { useMemo, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { clamp, formatMoney, formatPercent, formatPrice, formatSignedMoney } from "../market";
import type { Execution, Market } from "../types";
import { styles } from "../styles";

type Props = {
  markets: Market[];
  history: Execution[];
  onMarket: (pair: string) => void;
};

type HistoryFilter = "all" | "wins" | "losses" | "stops" | "liqs";

const historyFilters: Array<{ key: HistoryFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "wins", label: "Wins" },
  { key: "losses", label: "Losses" },
  { key: "stops", label: "Stops" },
  { key: "liqs", label: "Liqs" }
];

export function Dashboard({ markets, history, onMarket }: Props) {
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>("all");
  const ranked = [...markets].sort((a, b) => b.tradability - a.tradability);
  const hot = ranked[0];
  const realized = history.reduce((sum, trade) => sum + (trade.realizedWalletDelta ?? 0), 0);
  const outcomes = useMemo(() => history.map((trade) => ({ trade, outcome: tradeOutcome(trade) })), [history]);
  const stops = outcomes.filter(({ outcome }) => outcome.kind === "stop").length;
  const liquidations = outcomes.filter(({ outcome }) => outcome.kind === "liq").length;
  const filteredHistory = outcomes.filter(({ outcome }) => {
    if (historyFilter === "all") return true;
    if (historyFilter === "wins") return outcome.kind === "win";
    if (historyFilter === "losses") return outcome.kind === "loss";
    if (historyFilter === "stops") return outcome.kind === "stop";
    return outcome.kind === "liq";
  });

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
      <Text style={styles.pageTitle}>TICK</Text>
      {hot ? (
        <Pressable style={styles.hotCard} onPress={() => onMarket(hot.pair)}>
          <View>
            <Text style={styles.micro}>Hot now</Text>
            <Text style={styles.hotSymbol}>{hot.symbol}</Text>
            <Text style={styles.secondaryText}>{hot.feedLabel} · cost {formatPercent(hot.feeHurdlePct)}</Text>
          </View>
          <View style={styles.hotRight}>
            <Text style={[styles.hotMove, hot.move >= 0 ? styles.positive : styles.negative]}>{formatPercent(hot.move)}</Text>
            <Text style={styles.secondaryText}>{formatPrice(hot.price)}</Text>
          </View>
        </Pressable>
      ) : (
        <View style={styles.emptyPanel}><Text style={styles.secondaryText}>Scanner loading</Text></View>
      )}

      <View style={styles.statsRow}>
        <Metric label="Markets" value={String(markets.length)} />
        <Metric label="Realized" value={formatSignedMoney(realized)} positive={realized >= 0} />
        <Metric label="Stops / Liqs" value={`${stops}/${liquidations}`} />
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Volatility scanner</Text>
        <Text style={styles.micro}>live</Text>
      </View>
      {ranked.map((market, index) => (
        <Pressable key={market.pair} style={styles.scannerRow} onPress={() => onMarket(market.pair)}>
          <Text style={styles.scannerRank}>#{index + 1}</Text>
          <View style={styles.scannerIdentity}>
            <Text style={styles.scannerSymbol}>{market.symbol}</Text>
            <Text style={styles.micro}>{market.assetClass} · {formatPrice(market.price)}</Text>
          </View>
          <View style={styles.scannerActivity}>
            <View style={styles.scannerTrack}>
              <View style={[styles.scannerFill, { width: `${clamp(market.tradability, 3, 100)}%`, backgroundColor: market.theme.accent }]} />
            </View>
            <Text style={styles.scannerMeta}>move {formatPercent(market.activeTapePct)} · cost {formatPercent(market.feeHurdlePct)}</Text>
          </View>
        </Pressable>
      ))}

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Recent</Text>
        <Text style={styles.micro}>{history.length} trades</Text>
      </View>
      <View style={styles.filterRow}>
        {historyFilters.map((filter) => (
          <Pressable
            key={filter.key}
            style={[styles.filterChip, historyFilter === filter.key ? styles.filterChipActive : undefined]}
            onPress={() => setHistoryFilter(filter.key)}
          >
            <Text style={[styles.filterText, historyFilter === filter.key ? styles.filterTextActive : undefined]}>
              {filter.label}
            </Text>
          </Pressable>
        ))}
      </View>
      {filteredHistory.length ? filteredHistory.slice(0, 14).map(({ trade, outcome }) => (
        <View key={trade.id} style={styles.historyRow}>
          <View style={styles.historyMain}>
            <View style={styles.historyTitleRow}>
              <Text style={styles.historySymbol}>{trade.pair.split("-")[0]}</Text>
              <Text style={[styles.historyStatus, historyStatusStyle(outcome.kind)]}>{outcome.label}</Text>
            </View>
            <Text style={styles.micro}>
              {trade.side?.toUpperCase() ?? "TRADE"} · {formatTicket(trade)} · {formatTradeAge(trade.updatedAt)}
            </Text>
          </View>
          <View style={styles.historyRight}>
            <Text style={[outcome.pnl >= 0 ? styles.positive : styles.negative, styles.historyPnl]}>
              {formatSignedMoney(outcome.pnl)}
            </Text>
            <Text style={styles.micro}>{formatDuration(trade.result?.durationSeconds)}</Text>
          </View>
        </View>
      )) : <View style={styles.emptyPanel}><Text style={styles.secondaryText}>No trades for this filter</Text></View>}
    </ScrollView>
  );
}

function Metric({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <View style={styles.metricCard}>
      <Text style={styles.micro}>{label}</Text>
      <Text style={[styles.metricValue, positive === undefined ? undefined : positive ? styles.positive : styles.negative]}>{value}</Text>
    </View>
  );
}

function tradeOutcome(trade: Execution): { kind: "win" | "loss" | "stop" | "liq" | "failed"; label: string; pnl: number } {
  const status = trade.result?.status;
  const pnl = trade.realizedWalletDelta ?? 0;
  if (status === "liquidated") return { kind: "liq", label: "LIQ", pnl };
  if (status === "stop_loss_hit") return { kind: "stop", label: "STOP", pnl };
  if (trade.status === "failed" || trade.status === "unknown") return { kind: "failed", label: "FAIL", pnl };
  return pnl >= 0 ? { kind: "win", label: "WIN", pnl } : { kind: "loss", label: "LOSS", pnl };
}

function historyStatusStyle(kind: ReturnType<typeof tradeOutcome>["kind"]) {
  if (kind === "win") return styles.historyStatusWin;
  if (kind === "stop") return styles.historyStatusStop;
  if (kind === "liq" || kind === "failed") return styles.historyStatusBad;
  return styles.historyStatusLoss;
}

function formatTicket(trade: Execution): string {
  const ticket = trade.ticketUsd ?? trade.position?.ticketUsd ?? trade.position?.collateral;
  const leverage = trade.leverage ?? trade.position?.leverage;
  if (!ticket && !leverage) return "ticket --";
  if (!leverage) return formatMoney(ticket ?? 0);
  return `${formatMoney(ticket ?? 0)} · ${Math.round(leverage)}x`;
}

function formatTradeAge(updatedAt: number): string {
  if (!updatedAt) return "now";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - updatedAt));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function formatDuration(seconds?: number): string {
  if (!seconds || seconds <= 0) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}
