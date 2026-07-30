# TICK Engine

Last reviewed: 2026-07-30

## Product Decision

`TICK Engine` is the server-side discovery and interpretation layer that turns
market observations, route economics, and user execution constraints into a
small set of truthful product states. It does not predict direction or advise
the user which side to take.

TICK should not be only a volatility scanner. It should identify the
short-horizon shape of real movement:

```text
DIRECTIONAL
Momentum, trend continuation, and breakout conditions.

OSCILLATING
Range-bound, reversing, and short-horizon mean-reverting conditions.
```

This is a product simplification, not a claim that all day-trading methods fit
into two strategies. News trading, order-flow trading, market making, relative
value, and other methods exist. Directional and oscillating behavior are the
two primary chart regimes TICK can explain clearly in its current mobile loop.

What is sometimes casually called short-term "swing trading" is more accurately
called range trading or mean-reversion scalping here. Swing trading usually
describes positions held for days or weeks.

## Established Scanner Behavior

Existing scanners already direct trader attention toward:

```text
top percentage gainers and losers
most active instruments
unusual or relative volume
trade rate
price range
new highs and lows
volatility
momentum
```

IBKR exposes scanners such as top gainers and losers, most active, hot by price
and volume, top trade rate, top price range, and new highs or lows. TradingView
screeners expose volatility, momentum, performance, volume, and technical
filters across crypto and traditional markets.

These products establish that traders search for these market conditions. They
do not establish that a high-ranked candidate will be profitable.

Sources:

- [IBKR Market Scanners](https://www.interactivebrokers.com/en/?f=%2Fen%2Fsoftware%2Fpdfhighlights%2FPDF-marketscanners.php)
- [TradingView Crypto Coins Screener](https://www.tradingview.com/support/solutions/43000718742-crypto-coins-screener-discover-hidden-gems/)
- [TradingView Stock Screener](https://www.tradingview.com/support/solutions/43000718866-tradingview-stock-screener-trade-smarter-not-harder/)

## Directional Regime

Example:

```text
100 -> 101 -> 102 -> 103
```

The market has a substantial signed displacement and most observed movement is
in one direction.

Relevant measurements:

```text
signed net movement
directional efficiency
return sign persistence
acceleration or deceleration
participation
fresh range break
time since impulse began
```

Potential TICK stories:

```text
SURGING
DUMPING
PACE ACCELERATING
RANGE BREAK
IMPULSE COOLING
```

Example presentation:

```text
SURGING

+0.42% / 60s
88% directional
PARTICIPATION 2.2x
Impulse started 14s ago
```

The state describes recent behavior. It does not tell the user to go long,
short, or expect continuation.

Research documents intraday momentum in some markets and conditions. It also
shows that predictability changes with volume, volatility, liquidity, news, and
regime. Equity evidence at half-hour horizons is not proof of continuation over
TICK's next 10 to 60 seconds.

Sources:

- [Fidelity: Momentum](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/momentum)
- [Gao et al.: Market Intraday Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866)
- [Wen et al.: Intraday Return Predictability in Cryptocurrency Markets](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4080253)

## Oscillating Regime

Example:

```text
100 -> 103 -> 99 -> 102 -> 100
```

The market has substantial path movement but little net displacement. A trader
may interpret this as a temporary range or mean-reverting process.

Relevant measurements:

```text
range amplitude
directional efficiency
reversal count
mean-crossing frequency
range-boundary stability
average swing duration
current range position
range relative to route cost
```

Potential TICK stories:

```text
SWINGING
RANGE HOLDING
NEAR RANGE HIGH
NEAR RANGE LOW
RANGE COMPRESSING
```

Example presentation:

```text
SWINGING

4 reversals / 90s
Range 2.3x cost
Near lower range
Average swing 18s
```

A temporary range can break at any time. Near a recent boundary does not mean
that price must reverse. Range trading requires precise timing, and a
directional breakout can invalidate the observed regime.

Sources:

- [Fidelity: Range Trading](https://www.fidelity.com/learning-center/trading-investing/trading/range-trading)
- [IBKR: Mean Reversion](https://www.interactivebrokers.com/campus/glossary-terms/mean-reversion-statistical/)

## Common Measurements

For a sequence of real prices:

```text
path_movement =
  sum(abs(price[t] - price[t - 1]))

signed_net_movement =
  price[last] - price[first]

directional_efficiency =
  abs(signed_net_movement) / path_movement
```

Interpretation:

```text
near 1.0
movement was almost completely one-directional

near 0.0
price moved substantially but returned near its starting point
```

Directional efficiency needs a minimum movement threshold. A nearly flat
series must not be labeled directional merely because its tiny changes happened
to share one sign.

The first regime classifier can use:

```text
ACTIVE + high directional efficiency + positive net movement
-> SURGING

ACTIVE + high directional efficiency + negative net movement
-> DUMPING

ACTIVE + low directional efficiency + repeated reversals
-> SWINGING

ACTIVE + recent escape from a stable range
-> BREAKING

recent short-window direction opposes the earlier impulse
-> REVERSING

low ACTIVE
-> QUIET
```

Thresholds must be normalized against the same market, source, time-of-week,
and regime. They must be versioned and validated rather than selected only for
visual effect.

## Temporal Fit

Movement can be large enough to cover cost but too short-lived for TICK's
execution path.

```text
temporal_fit =
  observed or expected opportunity duration
  / p95 execution lifecycle latency
```

Examples:

```text
average swing duration: 1.5s
open execution latency: 2.0s

not operationally usable
```

```text
average swing duration: 18s
open execution latency: 2s
close execution latency: 2s

potentially usable, subject to costs and future validation
```

`TRADEABLE` therefore requires:

```text
movement amplitude plausibly covers route cost
opportunity duration survives measured execution latency
price and route remain fresh
liquidity and route health remain acceptable
```

Temporal fit must use actual route latency distributions rather than one
optimistic sample.

## TICK Engine Model

The engine's normalized discovery state is:

```text
ACTIVE
Is meaningful movement happening?

SHAPE
Surging, dumping, swinging, breaking, reversing, or quiet?

PARTICIPATION
Is real market involvement elevated?

CONTEXT
Where is price within its short and wider ranges?

TRADEABLE
Does the observed pattern survive costs and execution latency?

AVAILABLE
Can this user and route execute now?
```

Pulse can expose the shape without choosing the trade:

```text
SURGING
+0.38% / 60s
89% directional
PARTICIPATION 2.1x
```

```text
SWINGING
4 reversals / 90s
Range 2.3x cost
Near 1H low
```

The regime can change while the user watches:

```text
SWINGING
-> RANGE BREAK
-> SURGING
```

That transition is a first-class market event and may be more informative than
the static label.

## Shadow Validation

For every regime observation, record:

```text
signal timestamp
scanner version
market and source
active percentile
signed net movement
directional efficiency
participation
range and reversal measurements
route cost
p50 and p95 route latency
```

Evaluate future movement from both:

```text
signal time
estimated and actual executable fill time
```

Measure:

```text
signed return after 10s, 30s, 60s, and 5m
continuation or reversal
maximum favorable excursion
maximum adverse excursion
time until regime changed
whether movement survived round-trip cost
```

Measuring only from signal time would overstate usefulness because the user
cannot receive that historical price. TICK should not make a predictive
follow-through claim until the exact signal, latency, and cost-adjusted
evaluation supports it.
