import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  PanResponder,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View
} from "react-native";
import Svg, {
  Circle,
  Defs,
  Line,
  LinearGradient,
  Path,
  Rect,
  Stop,
  Text as SvgText
} from "react-native-svg";

type Direction = "up" | "down";
type Tab = "trade" | "activity" | "wallet" | "profile";
type Multiplier = 5 | 15 | 25 | 50 | 100;
type AssetClass = "CRYPTO" | "STOCK" | "INDEX" | "COMMODITY" | "FX";

type Market = {
  symbol: string;
  name: string;
  assetClass: AssetClass;
  feedLabel: string;
  maxMultiplier: Multiplier;
  price: number;
  move: number;
  points: number[];
  accent: string;
  glow: string;
  themeTop: string;
  themeMid: string;
  themeBottom: string;
  volatility: number;
  driftBias: number;
};

type Position = {
  id: string;
  symbol: string;
  direction: Direction;
  entry: number;
  entryPoint: number;
  mark: number;
  stake: number;
  multiplier: Multiplier;
  openedAt: number;
};

type Trade = {
  id: string;
  symbol: string;
  direction: Direction;
  pnl: number;
  pct: number;
  duration: string;
};

const CHART_UPDATE_MS = 180;
const CHART_HISTORY_SECONDS = 44;
const CHART_HISTORY_POINTS = Math.round((CHART_HISTORY_SECONDS * 1000) / CHART_UPDATE_MS);

const markets: Market[] = [
  makeMarket({
    symbol: "BTC",
    name: "Bitcoin",
    assetClass: "CRYPTO",
    feedLabel: "Crypto panic",
    maxMultiplier: 100,
    price: 63719.62,
    move: -3.18,
    points: [74, 72, 70, 68, 69, 66, 63, 65, 61, 58, 56, 59, 55, 52, 49, 51, 48, 45, 42, 44, 40, 38, 35, 32, 30, 28, 24, 22],
    accent: "#ff9f2e",
    glow: "#ffbd61",
    themeTop: "#101918",
    themeMid: "#151b17",
    themeBottom: "#24200f",
    volatility: 1.05,
    driftBias: -0.006
  }),
  makeMarket({
    symbol: "NVDA",
    name: "Nvidia",
    assetClass: "STOCK",
    feedLabel: "AI stock rush",
    maxMultiplier: 100,
    price: 182.4,
    move: 4.86,
    points: [28, 30, 29, 33, 38, 36, 41, 45, 49, 47, 53, 57, 54, 60, 64, 62, 68, 72, 69, 75, 78, 73, 80, 84, 81, 85, 82, 86],
    accent: "#5eead4",
    glow: "#8ff5e7",
    themeTop: "#0b171a",
    themeMid: "#0d2023",
    themeBottom: "#0b2f32",
    volatility: 0.92,
    driftBias: 0.012
  }),
  makeMarket({
    symbol: "ETH",
    name: "Ethereum",
    assetClass: "CRYPTO",
    feedLabel: "ETH breakout",
    maxMultiplier: 100,
    price: 1793.6,
    move: 1.41,
    points: [42, 43, 41, 44, 45, 46, 44, 47, 50, 49, 52, 53, 51, 54, 56, 55, 58, 61, 60, 62, 64, 63, 65, 67, 66, 69, 70, 72],
    accent: "#ff9f2e",
    glow: "#ffc66b",
    themeTop: "#121817",
    themeMid: "#171a12",
    themeBottom: "#27210d",
    volatility: 0.95,
    driftBias: 0.005
  }),
  makeMarket({
    symbol: "TSLA",
    name: "Tesla",
    assetClass: "STOCK",
    feedLabel: "Stock squeeze",
    maxMultiplier: 100,
    price: 442.8,
    move: -5.4,
    points: [77, 74, 70, 72, 68, 63, 66, 59, 54, 57, 50, 44, 47, 41, 36, 38, 32, 28, 31, 25, 22, 29, 36, 42, 39, 47, 51, 49],
    accent: "#fb7185",
    glow: "#fda4af",
    themeTop: "#190f14",
    themeMid: "#1d1218",
    themeBottom: "#2f1721",
    volatility: 1.18,
    driftBias: -0.01
  }),
  makeMarket({
    symbol: "US100",
    name: "Nasdaq",
    assetClass: "INDEX",
    feedLabel: "Macro move",
    maxMultiplier: 100,
    price: 26240,
    move: 2.08,
    points: [34, 35, 37, 36, 39, 43, 41, 45, 49, 52, 50, 54, 57, 55, 59, 63, 61, 65, 68, 67, 70, 72, 71, 75, 73, 77, 79, 78],
    accent: "#60a5fa",
    glow: "#93c5fd",
    themeTop: "#0d1521",
    themeMid: "#0e1b2d",
    themeBottom: "#122845",
    volatility: 0.72,
    driftBias: 0.008
  }),
  makeMarket({
    symbol: "XAU",
    name: "Gold",
    assetClass: "COMMODITY",
    feedLabel: "Safe-haven bid",
    maxMultiplier: 100,
    price: 4215.3,
    move: 1.26,
    points: [46, 45, 47, 49, 48, 51, 53, 52, 55, 56, 54, 57, 60, 58, 61, 63, 62, 65, 64, 67, 69, 68, 70, 72, 71, 74, 73, 75],
    accent: "#facc15",
    glow: "#fde68a",
    themeTop: "#17150d",
    themeMid: "#1d1a10",
    themeBottom: "#302609",
    volatility: 0.62,
    driftBias: 0.006
  }),
  makeMarket({
    symbol: "WTI",
    name: "Crude Oil",
    assetClass: "COMMODITY",
    feedLabel: "Oil shock",
    maxMultiplier: 100,
    price: 58.4,
    move: -3.72,
    points: [62, 59, 55, 58, 53, 50, 52, 48, 43, 45, 39, 35, 38, 34, 30, 32, 28, 25, 29, 33, 31, 36, 41, 39, 44, 46, 43, 48],
    accent: "#f97316",
    glow: "#fdba74",
    themeTop: "#19120c",
    themeMid: "#21170e",
    themeBottom: "#301b0b",
    volatility: 1.08,
    driftBias: -0.008
  }),
  makeMarket({
    symbol: "EURUSD",
    name: "Euro Dollar",
    assetClass: "FX",
    feedLabel: "FX trend",
    maxMultiplier: 100,
    price: 1.1684,
    move: 0.42,
    points: [40, 41, 42, 41, 43, 45, 44, 46, 47, 49, 48, 50, 52, 51, 53, 54, 56, 55, 57, 59, 58, 60, 62, 61, 63, 62, 64, 65],
    accent: "#a3e635",
    glow: "#d9f99d",
    themeTop: "#10170d",
    themeMid: "#16200f",
    themeBottom: "#20310d",
    volatility: 0.48,
    driftBias: 0.004
  })
];

function makeMarket(market: Market): Market {
  return {
    ...market,
    points: expandPoints(market.points)
  };
}

const initialTrades: Trade[] = [
  { id: "1", symbol: "NVDA", direction: "up", pnl: 31.6, pct: 126.4, duration: "02:36" },
  { id: "2", symbol: "WTI", direction: "down", pnl: 12.8, pct: 51.2, duration: "01:42" },
  { id: "3", symbol: "BTC", direction: "down", pnl: -6.4, pct: -25.6, duration: "04:18" }
];

export default function App() {
  const [tab, setTab] = useState<Tab>("trade");
  const [marketIndex, setMarketIndex] = useState(0);
  const [liveMarkets, setLiveMarkets] = useState(markets);
  const [stake, setStake] = useState(25);
  const [multiplier, setMultiplier] = useState<Multiplier>(100);
  const [balance, setBalance] = useState(420.6);
  const [position, setPosition] = useState<Position | null>(null);
  const [closedTrade, setClosedTrade] = useState<Trade | null>(null);
  const [trades, setTrades] = useState(initialTrades);

  const market = liveMarkets[marketIndex];
  const activeMultiplier = (multiplier > market.maxMultiplier ? market.maxMultiplier : multiplier) as Multiplier;
  const exposure = stake * activeMultiplier;
  const openFee = exposure * 0.0004;

  useEffect(() => {
    const timer = setInterval(() => {
      setLiveMarkets((current) =>
        current.map((item, index) => {
          const last = item.points[item.points.length - 1] ?? 50;
          const previous = item.points[item.points.length - 2] ?? last;
          const beforePrevious = item.points[item.points.length - 3] ?? previous;
          const velocity = last - previous;
          const acceleration = previous - beforePrevious;
          const now = Date.now();
          const regimeWave = Math.sin(now / 5200 + index * 1.1);
          const regime = regimeWave > 0 ? 1 : -1;
          const assetRhythm =
            item.assetClass === "FX" ? 0.72 : item.assetClass === "INDEX" ? 0.82 : item.assetClass === "STOCK" ? 1.08 : item.assetClass === "COMMODITY" ? 0.98 : 1.14;
          const volatility = item.volatility * assetRhythm;
          const trend = item.driftBias + (item.move >= 0 ? 0.004 : -0.004);
          const regimeDrift = regime * 0.026 * volatility;
          const fastPulse = Math.sin(now / 210 + index * 1.8) * 0.026 * volatility;
          const midPulse = Math.sin(now / 620 + index * 1.15) * 0.035 * volatility;
          const slowPulse = Math.sin(now / 1550 + index * 0.9) * 0.024 * volatility;
          const momentum = clamp(velocity * 0.036 + acceleration * 0.014, -0.052, 0.052) * volatility;
          const edgeReversal = last > 80 ? -0.1 * volatility : last < 20 ? 0.1 * volatility : 0;
          const squeeze = regimeWave > 0.68 ? Math.sign(velocity || regime) * 0.038 * volatility : 0;
          const pullback = Math.random() > 0.9 ? -Math.sign(velocity || regime) * (0.04 + Math.random() * 0.075) * volatility : 0;
          const breakout = Math.random() > 0.968 ? Math.sign(regime + velocity || 1) * (0.13 + Math.random() * 0.18) * volatility : 0;
          const liquidationWick = Math.random() > 0.986 ? -Math.sign(velocity || regime) * (0.11 + Math.random() * 0.16) * volatility : 0;
          const noise = (Math.random() - 0.5) * 0.03 * volatility;
          const tick = trend + regimeDrift + fastPulse + midPulse + slowPulse + momentum + edgeReversal + squeeze + pullback + breakout + liquidationWick + noise;
          const price = item.price * (1 + tick / 100);
          const point = clamp(last + tick * (8.8 + volatility * 3.2), 8, 88);

          return {
            ...item,
            price,
            move: clamp(item.move + tick * 0.18, -12.5, 12.5),
            points: [...item.points.slice(1), point]
          };
        })
      );
    }, CHART_UPDATE_MS);

    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!position) return;
    const matchingMarket = liveMarkets.find((item) => item.symbol === position.symbol);
    if (!matchingMarket) return;
    setPosition((current) => (current ? { ...current, mark: matchingMarket.price } : current));
  }, [liveMarkets, position?.symbol]);

  const livePnl = useMemo(() => {
    if (!position) return null;
    const side = position.direction === "up" ? 1 : -1;
    const move = ((position.mark - position.entry) / position.entry) * side;
    const pnl = position.stake * position.multiplier * move;
    return {
      usd: pnl,
      pct: (pnl / position.stake) * 100
    };
  }, [position]);

  function open(direction: Direction) {
    if (position || balance < stake + openFee) return;
    setClosedTrade(null);
    setBalance((value) => round(value - stake - openFee));
    setPosition({
      id: `p-${Date.now()}`,
      symbol: market.symbol,
      direction,
      entry: market.price,
      entryPoint: market.points[market.points.length - 1] ?? 50,
      mark: market.price,
      stake,
      multiplier: activeMultiplier,
      openedAt: Date.now()
    });
  }

  function cashOut() {
    if (!position || !livePnl) return;
    const fee = Math.max(0, livePnl.usd) * 0.2;
    const returned = Math.max(0, position.stake + livePnl.usd - fee);
    const result = round(livePnl.usd - fee);
    const trade = {
      id: `t-${Date.now()}`,
      symbol: position.symbol,
      direction: position.direction,
      pnl: result,
      pct: round((result / position.stake) * 100),
      duration: formatDuration(Date.now() - position.openedAt)
    };

    setBalance((value) => round(value + returned));
    setTrades((current) => [trade, ...current]);
    setClosedTrade(trade);
    setTimeout(() => {
      setClosedTrade((current) => (current?.id === trade.id ? null : current));
    }, 1150);
    setPosition(null);
  }

  function nextMarket() {
    setMarketIndex((value) => (value + 1) % liveMarkets.length);
  }

  function prevMarket() {
    setMarketIndex((value) => (value - 1 + liveMarkets.length) % liveMarkets.length);
  }

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" />
      <View style={styles.app}>
        {tab === "trade" && (
          <Trade
            market={market}
            balance={balance}
            stake={stake}
            multiplier={activeMultiplier}
            position={position}
            closedTrade={closedTrade}
            livePnl={livePnl}
            onOpen={open}
            onCashOut={cashOut}
            onNext={nextMarket}
            onPrev={prevMarket}
          />
        )}
        {tab === "activity" && <Activity trades={trades} />}
        {tab === "wallet" && <Wallet balance={balance} position={position} livePnl={livePnl} />}
        {tab === "profile" && <Profile stake={stake} multiplier={multiplier} onStake={setStake} onMultiplier={setMultiplier} />}
        <BottomNav tab={tab} onTab={setTab} />
      </View>
    </SafeAreaView>
  );
}

function Trade({
  market,
  balance,
  stake,
  multiplier,
  position,
  closedTrade,
  livePnl,
  onOpen,
  onCashOut,
  onNext,
  onPrev
}: {
  market: Market;
  balance: number;
  stake: number;
  multiplier: Multiplier;
  position: Position | null;
  closedTrade: Trade | null;
  livePnl: { usd: number; pct: number } | null;
  onOpen: (direction: Direction) => void;
  onCashOut: () => void;
  onNext: () => void;
  onPrev: () => void;
}) {
  const up = market.move >= 0;
  const [swipeCue, setSwipeCue] = useState<"long" | "short" | "next" | "prev" | null>(null);
  const cueOpacity = useRef(new Animated.Value(0)).current;
  const cueOffset = useRef(new Animated.Value(0)).current;
  const resultPop = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!closedTrade) return;

    resultPop.stopAnimation();
    resultPop.setValue(0);
    Animated.sequence([
      Animated.timing(resultPop, { toValue: 1, duration: 130, useNativeDriver: true }),
      Animated.delay(720),
      Animated.timing(resultPop, { toValue: 0, duration: 210, useNativeDriver: true })
    ]).start();
  }, [closedTrade, resultPop]);

  function flashCue(cue: "long" | "short" | "next" | "prev") {
    setSwipeCue(cue);
    cueOpacity.stopAnimation();
    cueOffset.stopAnimation();
    cueOpacity.setValue(0);
    cueOffset.setValue(cue === "long" ? 22 : cue === "short" ? -22 : 0);
    Animated.parallel([
      Animated.sequence([
        Animated.timing(cueOpacity, { toValue: 1, duration: 110, useNativeDriver: true }),
        Animated.timing(cueOpacity, { toValue: 0, duration: 380, delay: 180, useNativeDriver: true })
      ]),
      Animated.timing(cueOffset, { toValue: 0, duration: 260, useNativeDriver: true })
    ]).start(() => setSwipeCue(null));
  }
  const gestureResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dx) > 14 || Math.abs(gesture.dy) > 14,
        onPanResponderRelease: (_, gesture) => {
          const absX = Math.abs(gesture.dx);
          const absY = Math.abs(gesture.dy);
          const threshold = 54;

          if (absX > absY && absX > threshold && !position) {
            if (gesture.dx < 0) {
              flashCue("next");
              onNext();
            } else {
              flashCue("prev");
              onPrev();
            }
            return;
          }

          if (absY > absX && absY > threshold && !position) {
            if (gesture.dy < 0) {
              flashCue("long");
              onOpen("up");
            } else {
              flashCue("short");
              onOpen("down");
            }
          }
        }
      }),
    [cueOffset, cueOpacity, onNext, onOpen, onPrev, position]
  );

  return (
    <View style={[styles.tradeScreen, { backgroundColor: market.themeTop }]}>
      <View style={styles.topLine}>
        <View style={styles.brandMarket}>
          <Text style={styles.brand}>TICK</Text>
          <View style={styles.marketStack}>
            <View style={styles.marketInline}>
              <Text style={styles.inlineSymbol}>{market.symbol}</Text>
              <Text style={[styles.inlineLeverage, { color: market.glow }]}>{multiplier}x</Text>
              <Text style={styles.inlineName}>{market.name}</Text>
            </View>
            <View style={styles.headerPriceRow}>
              <Text style={styles.headerPrice}>{formatPrice(market.price)}</Text>
              <Text style={[styles.headerMove, up ? styles.greenText : styles.redText]}>
                {formatPercent(market.move)}
              </Text>
            </View>
          </View>
        </View>
        <View style={styles.balancePill}>
          <Text style={styles.balanceLabel}>Balance</Text>
          <Text style={styles.balanceValue}>{formatMoney(balance)}</Text>
        </View>
      </View>

      <View style={styles.chartWrap} {...gestureResponder.panHandlers}>
        <Chart
          market={market}
          points={market.points}
          price={market.price}
          up={up}
          entryPoint={position?.symbol === market.symbol ? position.entryPoint : undefined}
          direction={position?.symbol === market.symbol ? position.direction : undefined}
          livePnlPct={position?.symbol === market.symbol ? livePnl?.pct : undefined}
        />
        <View pointerEvents="none" style={styles.feedBadge}>
          <Text style={[styles.feedAsset, { color: market.glow }]}>{market.assetClass}</Text>
          <Text style={styles.feedText}>{market.feedLabel}</Text>
        </View>
        {position && livePnl ? (
          <View pointerEvents="none" style={styles.liveBadge}>
            <Text style={styles.liveSmall}>
              {position.symbol} {position.direction.toUpperCase()} {position.multiplier}x
            </Text>
            <Text style={[styles.livePnl, livePnl.usd >= 0 ? styles.greenText : styles.redText]}>
              {formatSignedMoney(livePnl.usd)}
            </Text>
            <Text style={[styles.livePct, livePnl.usd >= 0 ? styles.greenText : styles.redText]}>
              {formatPercent(livePnl.pct)}
            </Text>
          </View>
        ) : (
          null
        )}
        {!position && closedTrade ? (
          <Animated.View
            pointerEvents="none"
            style={[
              styles.closedCard,
              {
                opacity: resultPop,
                transform: [
                  {
                    translateY: resultPop.interpolate({
                      inputRange: [0, 1],
                      outputRange: [-8, 0]
                    })
                  },
                  {
                    scale: resultPop.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0.96, 1]
                    })
                  }
                ]
              }
            ]}
          >
            <Text style={styles.closedLabel}>Cashed out</Text>
            <Text style={[styles.closedValue, closedTrade.pnl >= 0 ? styles.greenText : styles.redText]}>
              {formatSignedMoney(closedTrade.pnl)}
            </Text>
            <Text style={styles.closedMeta}>
              {closedTrade.symbol} {closedTrade.direction.toUpperCase()} {formatPercent(closedTrade.pct)} in {closedTrade.duration}
            </Text>
          </Animated.View>
        ) : null}
        {swipeCue ? (
          <Animated.View
            pointerEvents="none"
            style={[
              styles.swipeCue,
              {
                opacity: cueOpacity,
                transform: [{ translateY: cueOffset }]
              }
            ]}
          >
            <Text style={[styles.swipeCueText, swipeCue === "short" ? styles.redText : styles.greenText]}>
              {swipeCue === "long" ? "LONG" : swipeCue === "short" ? "SHORT" : swipeCue === "next" ? "NEXT" : "PREV"}
            </Text>
          </Animated.View>
        ) : null}
        {position && livePnl ? (
          <View style={styles.floatingCashPanel}>
            <View style={styles.positionTerms}>
              <MiniTerm label="Entry" value={formatPrice(position.entry)} />
              <MiniTerm label="Now" value={formatPrice(position.mark)} />
              <MiniTerm label="Risk" value={`$${position.stake}`} />
            </View>
            <Pressable style={styles.cashButton} onPress={onCashOut}>
              <Text style={styles.cashText}>Cash out</Text>
            </Pressable>
          </View>
        ) : null}
      </View>
    </View>
  );
}

function Chart({
  market,
  points,
  price,
  up,
  entryPoint,
  direction
}: {
  market: Market;
  points: number[];
  price: number;
  up: boolean;
  entryPoint?: number;
  direction?: Direction;
  livePnlPct?: number;
}) {
  const chart = buildLineChart(points, price, entryPoint);
  const lineColor = market.accent;
  const glowColor = market.glow;
  const edgeColor = up ? c.green : c.red;
  const hasEntry = chart.entry && direction;

  return (
    <View style={styles.chart}>
      <Svg width="100%" height="100%" viewBox="0 0 360 360" preserveAspectRatio="none">
        <Defs>
          <LinearGradient id="chartBg" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={market.themeTop} stopOpacity="0.72" />
            <Stop offset="0.58" stopColor={market.themeMid} stopOpacity="0.5" />
            <Stop offset="1" stopColor={market.themeBottom} stopOpacity="0.55" />
          </LinearGradient>
          <LinearGradient id="lineArea" x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={glowColor} stopOpacity="0.28" />
            <Stop offset="0.62" stopColor={lineColor} stopOpacity="0.14" />
            <Stop offset="1" stopColor={lineColor} stopOpacity="0" />
          </LinearGradient>
        </Defs>
        <Rect x="0" y="0" width="360" height="360" fill="url(#chartBg)" />
        {chart.ticks.map((tick) => (
          <React.Fragment key={`${tick.value}-${tick.y}`}>
            <Line x1="18" y1={tick.y} x2="300" y2={tick.y} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
            <SvgText x="314" y={tick.y + 4} fill="rgba(218,230,226,0.66)" fontSize="10" fontWeight="800">
              {tick.label}
            </SvgText>
          </React.Fragment>
        ))}
        {[66, 124, 182, 240].map((x) => (
          <Line key={x} x1={x} y1="16" x2={x} y2="334" stroke="rgba(255,255,255,0.028)" strokeWidth="1" />
        ))}
        {chart.bars.map((bar) => (
          <Rect
            key={`${bar.x}-${bar.height}`}
            x={bar.x}
            y={bar.y}
            width={bar.width}
            height={bar.height}
            rx="1.8"
            fill={bar.up ? c.green : c.red}
            opacity={bar.opacity}
          />
        ))}
        {hasEntry && chart.entry ? (
          <>
            <Line
              x1="18"
              y1={chart.entry.y}
              x2="300"
              y2={chart.entry.y}
              stroke="rgba(236,222,183,0.4)"
              strokeDasharray="5 6"
              strokeLinecap="round"
              strokeWidth="1.2"
            />
          </>
        ) : null}
        <Path d={chart.areaPath} fill="url(#lineArea)" />
        <Path d={chart.linePath} fill="none" stroke={lineColor} strokeOpacity="0.08" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round" />
        <Path d={chart.linePath} fill="none" stroke={lineColor} strokeOpacity="0.22" strokeWidth="5.6" strokeLinecap="round" strokeLinejoin="round" />
        <Path d={chart.linePath} fill="none" stroke={lineColor} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
        <Path d={chart.tailPath} fill="none" stroke={glowColor} strokeOpacity="0.36" strokeWidth="3.8" strokeLinecap="round" strokeLinejoin="round" />
        <Path d={chart.sparkPath} fill="none" stroke="rgba(255,255,255,0.78)" strokeOpacity="0.42" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
        <Line
          x1="18"
          y1={chart.last.y}
          x2="300"
          y2={chart.last.y}
          stroke={edgeColor}
          strokeOpacity="0.2"
          strokeDasharray="4 7"
          strokeWidth="1"
        />
        <Rect x="304" y={chart.priceTag.y} width="52" height="19" rx="9.5" fill={edgeColor} opacity="0.92" />
        <SvgText x="330" y={chart.priceTag.y + 13} textAnchor="middle" fill="#06100d" fontSize="9.5" fontWeight="900">
          {chart.priceTag.label}
        </SvgText>
        <Circle cx={chart.last.x} cy={chart.last.y} r="7.5" fill={lineColor} opacity="0.14" />
        <Circle cx={chart.last.x} cy={chart.last.y} r="4.8" fill={edgeColor} opacity="0.22" />
        <Circle cx={chart.last.x} cy={chart.last.y} r="2.9" fill={edgeColor} />
      </Svg>
    </View>
  );
}

function Activity({ trades }: { trades: Trade[] }) {
  const pnl = trades.reduce((sum, trade) => sum + trade.pnl, 0);

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
      <Text style={styles.pageTitle}>Activity</Text>
      <View style={styles.bigStat}>
        <Text style={styles.micro}>All-time result</Text>
        <Text style={[styles.bigStatValue, pnl >= 0 ? styles.greenText : styles.redText]}>
          {formatSignedMoney(pnl)}
        </Text>
      </View>
      {trades.map((trade) => (
        <View key={trade.id} style={styles.listItem}>
          <View>
            <Text style={styles.listTitle}>
              {trade.symbol} {trade.direction.toUpperCase()}
            </Text>
            <Text style={styles.micro}>{trade.duration}</Text>
          </View>
          <View style={styles.listRight}>
            <Text style={[styles.listValue, trade.pnl >= 0 ? styles.greenText : styles.redText]}>
              {formatSignedMoney(trade.pnl)}
            </Text>
            <Text style={styles.micro}>
              {formatPercent(trade.pct)}
            </Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

function Wallet({
  balance,
  position,
  livePnl
}: {
  balance: number;
  position: Position | null;
  livePnl: { usd: number; pct: number } | null;
}) {
  const equity = balance + (position?.stake ?? 0) + (livePnl?.usd ?? 0);

  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
      <Text style={styles.pageTitle}>Wallet</Text>
      <View style={styles.walletBox}>
        <Text style={styles.micro}>TICK balance</Text>
        <Text style={styles.walletAmount}>{formatMoney(equity)}</Text>
        <Text style={styles.softText}>Available {formatMoney(balance)}</Text>
      </View>
      <View style={styles.walletActions}>
        <Pressable style={styles.primaryAction}>
          <Text style={styles.primaryActionText}>Deposit</Text>
        </Pressable>
        <Pressable style={styles.secondaryAction}>
          <Text style={styles.secondaryActionText}>Withdraw</Text>
        </Pressable>
      </View>
      <View style={styles.simpleBox}>
        <Info label="Wallet" value="Privy embedded" />
        <Info label="Trading" value="Enabled" />
        <Info label="Risk" value="Stake limited" />
      </View>
    </ScrollView>
  );
}

function Profile({
  stake,
  multiplier,
  onStake,
  onMultiplier
}: {
  stake: number;
  multiplier: Multiplier;
  onStake: (stake: number) => void;
  onMultiplier: (multiplier: Multiplier) => void;
}) {
  return (
    <ScrollView style={styles.page} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
      <Text style={styles.pageTitle}>Me</Text>
      <View style={styles.profileBox}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>T</Text>
        </View>
        <View>
          <Text style={styles.profileName}>tick.tick</Text>
          <Text style={styles.micro}>Trading enabled</Text>
        </View>
      </View>
      <View style={styles.simpleBox}>
        <Text style={styles.boxTitle}>Preset</Text>
        <Text style={styles.presetCaption}>This is what the Trade screen uses.</Text>
        <Text style={styles.presetLabel}>Risk</Text>
        <View style={styles.presetRow}>
          {[10, 25, 50].map((value) => (
            <Pressable key={value} style={[styles.chip, stake === value && styles.chipActive]} onPress={() => onStake(value)}>
              <Text style={[styles.chipText, stake === value && styles.chipActiveText]}>${value}</Text>
            </Pressable>
          ))}
        </View>
        <Text style={styles.presetLabel}>Speed</Text>
        <View style={styles.presetRow}>
          {[5, 25, 50, 100].map((value) => (
            <Pressable
              key={value}
              style={[styles.chip, multiplier === value && styles.chipActive]}
              onPress={() => onMultiplier(value as Multiplier)}
            >
              <Text style={[styles.chipText, multiplier === value && styles.chipActiveText]}>{value}x</Text>
            </Pressable>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}

function BottomNav({ tab, onTab }: { tab: Tab; onTab: (tab: Tab) => void }) {
  const items: { id: Tab; label: string }[] = [
    { id: "trade", label: "Trade" },
    { id: "activity", label: "History" },
    { id: "wallet", label: "Wallet" },
    { id: "profile", label: "Me" }
  ];

  return (
    <View style={styles.nav}>
      {items.map((item) => (
        <Pressable key={item.id} style={[styles.navItem, tab === item.id && styles.navActive]} onPress={() => onTab(item.id)}>
          <Text style={[styles.navText, tab === item.id && styles.navTextActive]}>{item.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function MiniTerm({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.miniTerm}>
      <Text style={styles.miniLabel}>{label}</Text>
      <Text style={styles.miniValue}>{value}</Text>
    </View>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.infoRow}>
      <Text style={styles.infoLabel}>{label}</Text>
      <Text style={styles.infoValue}>{value}</Text>
    </View>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function expandPoints(points: number[], target = CHART_HISTORY_POINTS) {
  if (points.length >= target) return points.slice(-target);

  return Array.from({ length: target }, (_, index) => {
    const sourceIndex = (index / Math.max(1, target - 1)) * (points.length - 1);
    const lower = Math.floor(sourceIndex);
    const upper = Math.min(points.length - 1, lower + 1);
    const progress = sourceIndex - lower;
    const interpolated = points[lower] * (1 - progress) + points[upper] * progress;
    const pulse = Math.sin(index * 0.72) * 0.7 + Math.sin(index * 0.19) * 0.85;

    return clamp(interpolated + pulse, 10, 86);
  });
}

function buildLineChart(points: number[], price: number, entryValue?: number) {
  const top = 16;
  const bottom = 334;
  const left = 18;
  const right = 300;
  const smoothed = points.map((point, index) => {
    const previous = points[index - 1] ?? point;
    const next = points[index + 1] ?? point;
    return previous * 0.22 + point * 0.56 + next * 0.22;
  });
  const rawMin = Math.min(...smoothed, ...(entryValue === undefined ? [] : [entryValue]));
  const rawMax = Math.max(...smoothed, ...(entryValue === undefined ? [] : [entryValue]));
  const rawSpan = Math.max(1, rawMax - rawMin);
  const midpoint = (rawMax + rawMin) / 2;
  const compressedSpan = rawSpan * 1.32;
  const min = midpoint - compressedSpan / 2;
  const max = midpoint + compressedSpan / 2;
  const span = Math.max(1, max - min);
  const toY = (value: number) => bottom - ((value - min) / span) * (bottom - top);
  const coords = smoothed.map((point, index) => ({
    x: left + (index / Math.max(1, smoothed.length - 1)) * (right - left),
    y: toY(point)
  }));
  const linePath = buildSmoothPath(coords);
  const tailPath = buildSmoothPath(coords.slice(Math.max(0, coords.length - 58)));
  const sparkPath = buildSmoothPath(coords.slice(Math.max(0, coords.length - 18)));
  const last = coords[coords.length - 1] ?? { x: right, y: bottom };
  const first = coords[0] ?? { x: left, y: bottom };
  const areaPath = `${linePath} L ${last.x.toFixed(2)} ${bottom.toFixed(2)} L ${first.x.toFixed(2)} ${bottom.toFixed(2)} Z`;
  const lastPoint = smoothed[smoothed.length - 1] ?? midpoint;
  const bars: { x: number; y: number; width: number; height: number; up: boolean; opacity: number }[] = [];
  const barStart = Math.max(1, smoothed.length - 60);

  for (let index = barStart; index < smoothed.length; index += 3) {
    const delta = smoothed[index] - (smoothed[index - 1] ?? smoothed[index]);
    const magnitude = clamp(Math.abs(delta) / 2.1, 0.1, 1);
    const x = left + (index / Math.max(1, smoothed.length - 1)) * (right - left);
    const height = 4 + magnitude * 22;

    bars.push({
      x: x - 1.35,
      y: bottom - 5 - height,
      width: 2.7,
      height,
      up: delta >= 0,
      opacity: 0.07 + magnitude * 0.17
    });
  }

  const ticks = [0.82, 0.62, 0.42, 0.22].map((ratio) => {
    const value = min + span * ratio;
    const estimatedPrice = price * (1 + (value - lastPoint) * 0.00125);
    return {
      value,
      y: toY(value),
      label: formatAxisPrice(estimatedPrice)
    };
  });
  const entry = entryValue === undefined ? undefined : { x: right, y: toY(entryValue) };
  const priceTag = {
    y: clamp(last.y - 9.5, top + 1, bottom - 19),
    label: formatAxisPrice(price)
  };

  return { linePath, tailPath, sparkPath, areaPath, ticks, bars, last, entry, priceTag };
}

function buildSmoothPath(coords: { x: number; y: number }[]) {
  if (coords.length === 0) return "";
  if (coords.length === 1) return `M ${coords[0].x.toFixed(2)} ${coords[0].y.toFixed(2)}`;

  let path = `M ${coords[0].x.toFixed(2)} ${coords[0].y.toFixed(2)}`;

  for (let index = 0; index < coords.length - 1; index += 1) {
    const p0 = coords[index - 1] ?? coords[index];
    const p1 = coords[index];
    const p2 = coords[index + 1];
    const p3 = coords[index + 2] ?? p2;
    const tension = 0.64;
    const cp1x = p1.x + ((p2.x - p0.x) / 6) * tension;
    const cp1y = p1.y + ((p2.y - p0.y) / 6) * tension;
    const cp2x = p2.x - ((p3.x - p1.x) / 6) * tension;
    const cp2y = p2.y - ((p3.y - p1.y) / 6) * tension;

    path += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }

  return path;
}

function round(value: number) {
  return Math.round(value * 100) / 100;
}

function formatDuration(ms: number) {
  const seconds = Math.max(1, Math.floor(ms / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function formatPrice(price: number) {
  if (!Number.isFinite(price)) return "$0.00";
  if (price < 1) return `$${price.toFixed(4)}`;
  if (price < 10) return `$${price.toFixed(4)}`;
  if (price < 100) return `$${price.toFixed(2)}`;
  return `$${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatMoney(value: number) {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `$${safeValue.toFixed(2)}`;
}

function formatSignedMoney(value: number) {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `${safeValue >= 0 ? "+" : "-"}$${Math.abs(safeValue).toFixed(2)}`;
}

function formatPercent(value: number) {
  const safeValue = Number.isFinite(value) ? value : 0;
  return `${safeValue >= 0 ? "+" : ""}${safeValue.toFixed(1)}%`;
}

function formatAxisPrice(price: number) {
  if (!Number.isFinite(price)) return "0";
  if (price < 1) return price.toFixed(4);
  if (price < 10) return price.toFixed(4);
  if (price < 100) return price.toFixed(2);
  if (price < 1000) return price.toFixed(1);
  return Math.round(price).toLocaleString(undefined, { useGrouping: false });
}

const c = {
  bg: "#0e1719",
  panel: "#121f22",
  panel2: "#18292d",
  line: "#2d4146",
  text: "#f4fbfa",
  soft: "#a7bab6",
  muted: "#78908a",
  green: "#38c884",
  red: "#ed5b67"
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#0a1214",
    alignItems: "center"
  },
  app: {
    flex: 1,
    width: "100%",
    maxWidth: 430,
    backgroundColor: c.bg
  },
  tradeScreen: {
    flex: 1,
    paddingHorizontal: 12,
    paddingTop: 5,
    paddingBottom: 4
  },
  topLine: {
    height: 46,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  brandMarket: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    flexShrink: 1
  },
  brand: {
    color: c.text,
    fontSize: 22,
    fontWeight: "900"
  },
  marketStack: {
    justifyContent: "center",
    flexShrink: 1
  },
  marketInline: {
    flexDirection: "row",
    alignItems: "baseline",
    gap: 6,
    flexShrink: 1
  },
  inlineSymbol: {
    color: c.text,
    fontSize: 17,
    fontWeight: "900"
  },
  inlineLeverage: {
    color: "#ffbd61",
    fontSize: 12,
    fontWeight: "900"
  },
  inlineName: {
    color: c.soft,
    fontSize: 12,
    fontWeight: "800"
  },
  headerPriceRow: {
    flexDirection: "row",
    alignItems: "baseline",
    gap: 7,
    marginTop: 1
  },
  headerPrice: {
    color: "rgba(244,251,250,0.92)",
    fontSize: 13,
    fontWeight: "900",
    lineHeight: 15
  },
  headerMove: {
    fontSize: 12,
    fontWeight: "900",
    lineHeight: 14
  },
  micro: {
    color: c.muted,
    fontSize: 12,
    fontWeight: "700"
  },
  balancePill: {
    minWidth: 108,
    minHeight: 35,
    borderRadius: 18,
    backgroundColor: "rgba(56,200,132,0.13)",
    borderWidth: 1,
    borderColor: "rgba(56,200,132,0.34)",
    paddingHorizontal: 12,
    justifyContent: "center"
  },
  balanceLabel: {
    color: "rgba(174,231,203,0.72)",
    fontSize: 9,
    fontWeight: "800",
    lineHeight: 11
  },
  balanceValue: {
    color: c.green,
    fontSize: 16,
    fontWeight: "900",
    lineHeight: 18
  },
  marketLine: {
    minHeight: 55,
    flexDirection: "row",
    alignItems: "flex-end",
    justifyContent: "space-between",
    gap: 14
  },
  symbol: {
    color: c.text,
    fontSize: 36,
    fontWeight: "900",
    lineHeight: 38
  },
  name: {
    color: c.soft,
    fontSize: 14,
    fontWeight: "800"
  },
  priceBlock: {
    alignItems: "flex-end",
    paddingBottom: 4
  },
  price: {
    color: c.text,
    fontSize: 19,
    fontWeight: "900"
  },
  move: {
    fontSize: 13,
    fontWeight: "900",
    marginTop: 0
  },
  greenText: {
    color: c.green
  },
  redText: {
    color: c.red
  },
  chartWrap: {
    flex: 1,
    minHeight: 0,
    marginHorizontal: -12,
    marginTop: 0,
    marginBottom: 4,
    overflow: "hidden",
    borderRadius: 0
  },
  chart: {
    flex: 1,
    borderRadius: 0,
    overflow: "hidden",
    backgroundColor: "rgba(13,17,16,0.56)"
  },
  feedBadge: {
    position: "absolute",
    left: 16,
    top: 16,
    borderRadius: 14,
    backgroundColor: "rgba(6,12,13,0.42)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    paddingHorizontal: 10,
    paddingVertical: 7
  },
  feedAsset: {
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 0
  },
  feedText: {
    color: "rgba(231,240,237,0.78)",
    fontSize: 11,
    fontWeight: "900",
    marginTop: 1
  },
  liveBadge: {
    position: "absolute",
    left: 0,
    right: 0,
    top: 62,
    alignItems: "center",
    justifyContent: "center"
  },
  liveSmall: {
    color: c.soft,
    fontSize: 11,
    fontWeight: "800",
    marginBottom: 3,
    textShadowColor: "rgba(0,0,0,0.5)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 6
  },
  livePnl: {
    fontSize: 40,
    fontWeight: "900",
    lineHeight: 43,
    textShadowColor: "rgba(0,0,0,0.42)",
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 12
  },
  livePct: {
    fontSize: 14,
    fontWeight: "900",
    textShadowColor: "rgba(0,0,0,0.48)",
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 8
  },
  closedCard: {
    position: "absolute",
    left: 36,
    right: 36,
    top: 72,
    borderRadius: 18,
    backgroundColor: "rgba(13,21,24,0.82)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.09)",
    paddingHorizontal: 15,
    paddingTop: 12,
    paddingBottom: 14
  },
  closedLabel: {
    color: c.soft,
    fontSize: 12,
    fontWeight: "900"
  },
  closedValue: {
    fontSize: 36,
    fontWeight: "900",
    lineHeight: 39,
    marginTop: 2
  },
  closedMeta: {
    color: c.soft,
    fontSize: 12,
    fontWeight: "800",
    marginTop: 5
  },
  floatingCashPanel: {
    position: "absolute",
    left: 14,
    right: 14,
    bottom: 42,
    minHeight: 76,
    borderRadius: 18,
    backgroundColor: "rgba(12,19,21,0.72)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.08)",
    padding: 9,
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  chip: {
    flex: 1,
    height: 38,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: c.panel2,
    borderWidth: 1,
    borderColor: c.line
  },
  chipActive: {
    backgroundColor: c.text,
    borderColor: c.text
  },
  chipText: {
    color: c.soft,
    fontSize: 13,
    fontWeight: "900"
  },
  chipActiveText: {
    color: c.bg
  },
  miniTerm: {
    minWidth: 48
  },
  miniLabel: {
    color: c.muted,
    fontSize: 11,
    fontWeight: "700",
    marginBottom: 3
  },
  miniValue: {
    color: c.text,
    fontSize: 12,
    fontWeight: "900"
  },
  swipeCue: {
    position: "absolute",
    left: 0,
    right: 0,
    top: "42%",
    alignItems: "center",
    justifyContent: "center"
  },
  swipeCueText: {
    fontSize: 44,
    fontWeight: "900",
    letterSpacing: 0,
    textShadowColor: "rgba(0,0,0,0.34)",
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 10
  },
  positionTerms: {
    flex: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 8
  },
  cashButton: {
    width: 108,
    height: 58,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: c.text
  },
  cashText: {
    color: c.bg,
    fontSize: 18,
    fontWeight: "900"
  },
  page: {
    flex: 1
  },
  pageContent: {
    paddingHorizontal: 18,
    paddingTop: 22,
    paddingBottom: 22
  },
  pageTitle: {
    color: c.text,
    fontSize: 34,
    fontWeight: "900",
    marginBottom: 16
  },
  bigStat: {
    minHeight: 118,
    borderRadius: 10,
    backgroundColor: c.panel,
    borderWidth: 1,
    borderColor: c.line,
    padding: 16,
    justifyContent: "center",
    marginBottom: 12
  },
  bigStatValue: {
    fontSize: 42,
    fontWeight: "900",
    marginTop: 4
  },
  listItem: {
    minHeight: 72,
    borderRadius: 10,
    backgroundColor: c.panel,
    borderWidth: 1,
    borderColor: c.line,
    paddingHorizontal: 14,
    marginBottom: 9,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },
  listTitle: {
    color: c.text,
    fontSize: 15,
    fontWeight: "900",
    marginBottom: 4
  },
  listRight: {
    alignItems: "flex-end"
  },
  listValue: {
    fontSize: 18,
    fontWeight: "900"
  },
  walletBox: {
    minHeight: 150,
    borderRadius: 10,
    backgroundColor: c.panel,
    borderWidth: 1,
    borderColor: c.line,
    padding: 18,
    justifyContent: "center"
  },
  walletAmount: {
    color: c.text,
    fontSize: 48,
    fontWeight: "900",
    marginTop: 4
  },
  softText: {
    color: c.soft,
    fontSize: 14,
    fontWeight: "800",
    marginTop: 6
  },
  walletActions: {
    flexDirection: "row",
    gap: 10,
    marginTop: 12
  },
  primaryAction: {
    flex: 1,
    height: 56,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: c.green
  },
  primaryActionText: {
    color: c.bg,
    fontSize: 16,
    fontWeight: "900"
  },
  secondaryAction: {
    flex: 1,
    height: 56,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: c.panel2,
    borderWidth: 1,
    borderColor: c.line
  },
  secondaryActionText: {
    color: c.text,
    fontSize: 16,
    fontWeight: "900"
  },
  simpleBox: {
    borderRadius: 10,
    backgroundColor: c.panel,
    borderWidth: 1,
    borderColor: c.line,
    padding: 16,
    marginTop: 12
  },
  infoRow: {
    minHeight: 36,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderTopWidth: 1,
    borderTopColor: "rgba(255,255,255,0.055)"
  },
  infoLabel: {
    color: c.muted,
    fontSize: 13,
    fontWeight: "700"
  },
  infoValue: {
    color: c.text,
    fontSize: 13,
    fontWeight: "900"
  },
  profileBox: {
    minHeight: 84,
    borderRadius: 10,
    backgroundColor: c.panel,
    borderWidth: 1,
    borderColor: c.line,
    padding: 14,
    flexDirection: "row",
    alignItems: "center",
    gap: 12
  },
  avatar: {
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: c.text,
    alignItems: "center",
    justifyContent: "center"
  },
  avatarText: {
    color: c.bg,
    fontSize: 22,
    fontWeight: "900"
  },
  profileName: {
    color: c.text,
    fontSize: 19,
    fontWeight: "900"
  },
  boxTitle: {
    color: c.text,
    fontSize: 17,
    fontWeight: "900",
    marginBottom: 12
  },
  presetCaption: {
    color: c.muted,
    fontSize: 12,
    fontWeight: "700",
    marginTop: -6,
    marginBottom: 14
  },
  presetLabel: {
    color: c.soft,
    fontSize: 13,
    fontWeight: "900",
    marginBottom: 8
  },
  presetRow: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 14
  },
  nav: {
    height: 50,
    borderRadius: 25,
    backgroundColor: "rgba(22,32,36,0.82)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    flexDirection: "row",
    padding: 5,
    marginHorizontal: 32,
    marginBottom: 10,
    flexShrink: 0
  },
  navItem: {
    flex: 1,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center"
  },
  navActive: {
    backgroundColor: c.text
  },
  navText: {
    color: "rgba(148,168,161,0.58)",
    fontSize: 11,
    fontWeight: "900"
  },
  navTextActive: {
    color: c.bg
  }
});
