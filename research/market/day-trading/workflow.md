# Short-Horizon Trading Workflow

Last reviewed: 2026-07-30

## Product Boundary

TICK is not trying to reproduce every professional trading workflow. It is
compressing the common short-horizon loop into a mobile surface:

```text
DISCOVER -> ORIENT -> AUTHORIZE -> MONITOR -> EXIT -> REVIEW
```

The user chooses direction. TICK selects and explains market conditions,
normalizes route terms, executes the authorized preset, and reports the truth.

## 1. Discover

Question:

> Which supported market deserves attention now?

Useful inputs:

```text
market availability
price and feed freshness
recent path movement and range
activity relative to that market's baseline
estimated round-trip route cost
spread, price impact, and route health
scheduled event or session transition
```

Output:

```text
Pulse ranking with an explicit reason
```

Not output:

```text
BUY
SELL
guaranteed edge
```

Discovery is where cross-asset breadth matters most. The user should not have
to know whether crypto, gold, EUR/USD, or an index is active before opening
TICK.

## 2. Orient

Question:

> What kind of movement am I looking at?

The current TICK structure is a sensible hypothesis:

```text
LIVE      60-90 seconds for immediate tape and execution
CONTEXT   15 minutes of visible structure
RANGE     current position within the retained one-hour range
```

Multi-timeframe tools are common because a wider view provides context while a
shorter view supports timing. This does not prove those exact windows are
optimal for TICK; it supports having one reversible context action instead of
a permanent timeframe toolbar.

Source:

- [TradingView: Leveraging Multi-Timeframe Analysis](https://www.tradingview.com/support/solutions/43000591555-leveraging-multi-timeframe-analysis/)

The context surface should answer only:

```text
near recent high, low, or middle?
range expanding or compressing?
recent pace faster or slower than normal?
scheduled market event nearby?
```

## 3. Authorize

Question:

> What exact financial action will this gesture authorize?

Terms visible before the gesture:

```text
ticket / collateral
leverage
effective exposure
estimated open cost
estimated round-trip cost
loss budget or venue stop, if enabled
estimated liquidation distance
quote freshness
```

The vertical gesture can remain the confirmation if these terms are stable and
the backend enforces a short-lived authorization envelope. A material price,
cost, leverage, market-state, or route change requires a refresh rather than
silent execution on different terms.

Opening and closing are intentionally asymmetric:

```text
open:
requires valid market, quote, balance, route, and policy state

close:
risk-reducing action; submit from known normalized position state and
reconcile venue rejection or external closure afterward
```

## 4. Monitor

Question:

> What would this position return if closed now, and what can end it first?

Primary information:

```text
estimated net if closed now
actual opening cost already incurred
estimated current close cost
cost recovered / net break-even
time in position
stop distance
liquidation distance
venue state
```

The live chart can include:

```text
entry
net break-even
venue stop
take profit
liquidation
authoritative execution markers
```

It should not become a second Pulse. Once money is exposed, risk and financial
truth outrank new market stories.

## 5. Exit

Question:

> Is exposure actually gone?

Required state distinction:

```text
close requested
close initiation accepted
awaiting venue execution
position closed
result reconciling
result final
```

For oracle-based venues, transaction initiation is not the same as execution.
The chart and UI can acknowledge progress immediately, but they must not claim
the position is closed until an authoritative venue observation establishes it.

Venue-native TP and SL are useful because they can operate while the PWA is
backgrounded or disconnected. Their guarantees and trigger references differ
by venue and asset class. For example, a stop can lose the race to liquidation
or execute differently when a market gaps.

Sources:

- [Gains Network: Opening and Closing Trades](https://docs.gains.trade/gtrade-leveraged-trading/opening-closing-trades)
- [Bybit: TP/SL for Perpetual and Futures Contracts](https://www.bybit.com/en/help-center/article/Introduction-to-Take-Profit-Stop-Loss-Perpetual-Futures-Contracts)

## 6. Review

Question:

> Why did the wallet change by this amount?

History should show:

```text
market and direction
entry and exit
price movement PnL
open fee
close fee
spread and price impact
borrowing or funding
gas charge
realized net result
finalization source
execution times
```

Useful review metrics:

```text
net result
cost as percent of ticket
time in trade
maximum favorable movement
maximum adverse movement
whether the position ended manually, by stop, TP, or liquidation
```

Win count alone is not useful enough. A high win rate can coexist with negative
net PnL.

## Stage-Specific Information Budget

| Stage | Primary number | Context | Primary action |
| --- | --- | --- | --- |
| Discover | activity relative to normal | cost and availability | select market |
| Orient | current price and recent range | pace and range location | choose direction or wait |
| Authorize | ticket and all-in cost | exposure and risk distance | one deliberate gesture |
| Monitor | estimated net if closed now | cost recovery and risk | close |
| Exit | exposure state | venue execution progress | wait or recover |
| Review | realized net wallet result | cost and execution breakdown | dismiss or inspect |

## Asset-Class Differences Inside the Same Workflow

The stages remain stable, while risk metadata changes:

```text
crypto:
24/7, funding/borrowing, liquidation, no scheduled close

FX:
session liquidity, weekend gaps, rollover, macro-event restrictions

indices and commodities:
session breaks, event risk, gaps, possible expiry in futures routes

equities:
core/extended hours, halts, earnings, dividends, corporate actions

rates:
contract maturity, yield/price direction, scheduled central-bank and
economic releases
```

This is why TICK needs one normalized workflow and explicit market
capabilities, not one generic `is_open` flag.
