# Crypto Day-Trader Workflows and TICK

Last reviewed: 2026-07-30

This is the implementation-facing memo for the current crypto chart and mobile
loop. The deeper empirical, behavioral, and cross-asset research now lives in
[`day-trading/`](day-trading/README.md).

## Executive Decision

TICK should not become a compact professional terminal. The useful workflow to
preserve is:

```text
find an active and executable market
-> inspect a slightly wider context
-> act on the live tape
-> watch net result and risk
-> close and review the real wallet result
```

The next high-value addition is therefore a deliberate chart context switch,
not a collection of permanent indicators:

```text
LIVE     60-90 second execution tape
CONTEXT  15 minute price view backed by one hour of retained tape
```

The wider view should load before the transition, use the same gTrade price
source, and return to the exact live state without a blank frame or historical
redraw.

The context surface should include one plain vertical one-hour range rail at
the chart edge:

```text
1H HIGH
   |
   o  current
   |
1H LOW
```

The dot is the current price percentile inside the real retained one-hour
range. `NEAR 1H LOW` and `NEAR 1H HIGH` describe range location only; they are
not directional advice. The 15-minute chart remains the default context because
it preserves useful structure for a seconds-long entry, while the one-hour
retention supplies broader high, low, and range position.

## What Active Traders Actually Need

### 1. Market selection

Short-horizon traders first need enough movement, enough liquidity, acceptable
costs, and reliable execution. Kraken's current day-trading material explicitly
calls out volatility, liquidity, fees, slippage, leverage, and platform
reliability as core constraints. It also describes momentum, range, breakout,
news, VWAP, and order-flow approaches as different setups rather than one
universal strategy.

This supports TICK's current product boundary:

```text
Pulse selects markets.
TICK does not select direction.
```

Sources:

- [Kraken: crypto day-trading strategies](https://www.kraken.com/learn/day-trading-strategies)
- [Kraken: what is crypto day trading?](https://www.kraken.com/learn/what-is-crypto-day-trading?noappbanner=1&noapplink=1)
- [Kraken: crypto market volatility](https://www.kraken.com/learn/crypto-market-volatility)

### 2. Wider context before precise execution

Multiple-timeframe analysis is a common way to separate context from entry
timing. Interactive Brokers describes combining higher and lower timeframes for
opportunity identification, execution precision, and risk management. Fidelity
also emphasizes matching chart timeframe to the intended trading horizon and
recognizing that short movement can sit inside a different longer trend.

For TICK this does not justify a timeframe toolbar. It justifies one reversible
context action:

```text
LIVE <-> 5m or 15m
```

Sources:

- [Interactive Brokers: leveraging timeframes](https://www.interactivebrokers.com/campus/webinars/leveraging-timeframes-to-define-your-trading-style/)
- [Fidelity: basic concepts of trend](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/basic-concepts-trend)
- [Fidelity: using technical analysis](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/using-technical-analysis)

### 3. A small number of reactive signals

Price, volume, volatility, momentum, support, and resistance are common inputs,
but technical analysis is reactive and probabilistic rather than predictive.
That supports TICK's plain-language event labels:

```text
NEAR 90s HIGH
NEAR 90s LOW
TAPE ACCELERATING
TAPE COOLING
RANGE BREAK
```

These labels describe observed market state. They must not become `BUY`,
`SELL`, or "positive edge" claims.

Sources:

- [Fidelity: what is technical analysis?](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/what-is-technical-analysis)
- [Fidelity: support and resistance](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/support-and-resistance?print=true-0)

### 4. Position monitoring is different from market analysis

Once a position is open, the useful questions change:

```text
What is my estimated net result now?
How much of the round-trip cost has price movement recovered?
How long have I been exposed?
How far are the venue stop and liquidation levels?
Has the venue actually closed the position?
```

The current live-position surface is close to the right information budget:

```text
estimated net if closed now
cost recovery
time in trade
stop/liquidation distance
close action
```

Do not add RSI, MACD, several moving averages, order-book depth, funding, and
open interest to this state. They would compete with the user's immediate
financial truth.

gTrade itself distinguishes order initiation from oracle execution, shows
liquidation and TP/SL levels, and defines displayed net PnL as what returns to
the wallet at closure.

Sources:

- [Gains: opening and closing trades](https://docs.gains.trade/gtrade-leveraged-trading/opening-closing-trades)
- [Gains: fees and dynamic liquidation](https://docs.gains.trade/gtrade-leveraged-trading/fees-and-spread)

## What `TAPE HEAT` Means Today

The current component is a relative movement-tempo meter. It does not measure
direction, expected return, volume, or whether a trade should be opened.

Current calculation:

```text
1. Divide the real 90-second gTrade tape into 2-second buckets.
2. For each bucket, sum absolute real price movement.
3. Add a very small weight for the number of real changed-price updates.
4. Average the last 10 seconds.
5. Compare that average with the preceding 30 seconds.
```

Interpretation:

```text
0.7x  = the last 10 seconds moved about 30% less than the prior baseline
1.0x  = similar movement tempo
1.5x  = about 50% more movement tempo
2.0x  = about twice the movement tempo
```

The five bars are the five real 2-second activity buckets inside the latest
10-second window. A taller bar means more observed absolute movement in that
bucket. The bars do not show long versus short.

Current labels:

```text
QUIET   below 0.6x
WARM    0.6x to below 1.0x
ACTIVE  1.0x to below 1.55x
HOT     1.55x and above
```

### Product-language recommendation

`TAPE HEAT` is visually useful but still requires explanation. A clearer future
label is:

```text
SWING TEMPO
1.4x recent pace
```

The default surface can retain the five live bars and one ratio. The exact
`10s versus prior 30s` explanation belongs in a tap detail or first-use guide.

Before changing the window, measure it. A `20s versus prior 60s` comparison
will be steadier but less responsive. The current `10s versus prior 30s`
comparison better matches a seconds-long TICK position but can change labels
more often. This is an A/B decision, not a theoretical one.

## Data TICK Can Truthfully Show

### From the gTrade price source

Gains publishes a real-time price stream with updates as often as every 25 ms
and a chart endpoint with OHLC values. The documented price stream contains
pair IDs and prices, not traded size.

TICK can derive from this same source:

```text
real tick line
1-2 second OHLC micro-bars
short-window range
position inside recent range
absolute movement tempo
price-update cadence
real range breaks
```

It should label the histogram `ACTIVITY`, `TAPE`, or `SWING TEMPO`, not
`VOLUME`.

Source:

- [Gains: price feed](https://docs.gains.trade/developer/integrators/price-feed)

### Volume, funding, and open interest

Real volume can be useful when the source provides actual trades. Coinbase, for
example, documents candles with traded base volume and WebSocket updates that
may aggregate multiple trades. Hyperliquid exposes mark price, funding, and
open interest in its perpetual context API.

Those data are not automatically valid for TICK's current gTrade position:

- an external venue's price must never drive gTrade PnL, stops, liquidation, or
  chart execution markers;
- cross-venue volume or OI would be context only and needs explicit source
  labeling;
- funding is low-value for a position intended to last seconds;
- adding another stream is justified only after it measurably improves market
  selection.

Sources:

- [Coinbase: Advanced Trade WebSocket channels](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-channels)
- [Hyperliquid: perpetual asset contexts](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [Hyperliquid: funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding)

## TICK Product Calls

### Build next

1. Add the preloaded `LIVE <-> CONTEXT` chart switch with a one-hour range rail.
2. Keep one changing market-story label, with event age when useful.
3. Keep the real five-bucket tempo texture, but test clearer `SWING TEMPO`
   language.
4. Keep position mode limited to net PnL, cost recovery, time, risk distance,
   and close state.
5. Record whether Pulse rankings predicted continued executable movement after
   selection, not merely movement before selection.

### Keep out of the default screen

```text
RSI
MACD
several moving averages
full volume profile
funding table
open-interest table
liquidation heatmap
order book
directional buy/sell signals
```

These can become Pro/detail features only when a real user need and a reliable
data source are established.

### Validate with users

For each demo session, capture:

```text
Did the user open CONTEXT before trading?
How quickly did they understand SWING TEMPO?
Did the market-story label affect market selection?
Did they understand that HIGH/LOW describes range location, not advice?
Did cost recovery help explain negative initial net PnL?
Did they close from the visible action without confusion?
Did the final wallet result match what they expected?
```

The foundation remains:

> Show enough changing context to explain the market, but keep the trade itself
> centered on truthful net outcome and venue-confirmed state.
