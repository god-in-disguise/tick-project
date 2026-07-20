import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";

import { clamp, formatMoney, formatPercent, formatPrice, formatSignedMoney } from "../market";
import type { Execution, Market } from "../types";
import { styles } from "../styles";

type Props = {
  markets: Market[];
  history: Execution[];
  onMarket: (pair: string) => void;
};

export function Dashboard({ markets, history, onMarket }: Props) {
  const ranked = [...markets].sort((a, b) => b.tradability - a.tradability);
  const hot = ranked[0];
  const realized = history.reduce((sum, trade) => sum + (trade.realizedWalletDelta ?? 0), 0);

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
      </View>
      {history.length ? history.slice(0, 10).map((trade) => (
        <View key={trade.id} style={styles.historyRow}>
          <View>
            <Text style={styles.historySymbol}>{trade.pair.split("-")[0]}</Text>
            <Text style={styles.micro}>{trade.side?.toUpperCase() ?? "TRADE"}</Text>
          </View>
          <Text style={[(trade.realizedWalletDelta ?? 0) >= 0 ? styles.positive : styles.negative, styles.historyPnl]}>
            {formatSignedMoney(trade.realizedWalletDelta ?? 0)}
          </Text>
        </View>
      )) : <View style={styles.emptyPanel}><Text style={styles.secondaryText}>No completed local trades</Text></View>}
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
