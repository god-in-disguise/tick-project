# TICK Product Implications

Last reviewed: 2026-07-30

## Preserve the Current Philosophy

TICK's consumer loop remains:

```text
one market
one visible preset
one deliberate gesture
one live position
one truthful result
```

Cross-asset breadth belongs behind that simplicity. The user should not have to
choose a venue, learn different order forms, or interpret route-specific names.

## Pulse: Find the Market, Do Not Pick the Trade

Pulse should answer:

> What is moving unusually, economically executable, and available now?

Each candidate needs a compact explanation:

```text
FAST · 1.8x NORMAL
MOVE 0.17% · COST 0.05%
NEAR 1H LOW
```

The three lines mean:

```text
FAST:
relative movement regime for this market

MOVE / COST:
observed movement compared with estimated route hurdle

NEAR 1H LOW:
location inside the real retained range
```

They do not mean long, short, rebound, breakout continuation, or positive
expected value.

Pulse should support:

```text
ALL
CRYPTO
FX
INDICES
COMMODITIES
EQUITIES
RATES
```

The default remains `ALL`, because finding activity across markets is the
product advantage. Filters are user intent, not separate app modes.

## TICK Flat State: Explain the Moment

Information budget:

```text
asset and asset class
current price
current leverage preset
one market story
live chart
context action
amount, exposure, cost, and risk distance
```

Good market stories:

```text
NEAR 90s LOW
NEAR 1H HIGH
RANGE EXPANDING
PACE 1.7x NORMAL
COST JUST COVERED
EVENT IN 12m
```

Bad market stories:

```text
BUY NOW
STRONG LONG
EASY WIN
POSITIVE EDGE
```

Only one story should be primary at a time. It should have a real source
timestamp and clear expiry.

## Chart: Truthful but Alive

The current direction remains correct:

```text
LIVE:
60-90 second timestamp-based tape

CONTEXT:
preloaded wider view with one-hour retained range
```

The chart may animate between real ticks at display frame rate, but only real
market observations enter history, extrema, PnL, markers, or scanner metrics.

Useful chart texture:

```text
real line
derived 1-2 second high/low wicks
truthfully labeled price activity
current range position
entry and net break-even after open
authoritative stop, TP, liquidation, and close markers
```

Do not add external-venue price data to make the execution chart look busier.
Context from another source must be separately labeled and must never drive
position truth.

## TICK Live State: Explain the Money

After the venue confirms the opening, replace market-discovery emphasis with:

```text
EST. NET IF CLOSED NOW

cost recovery
time in trade
entry
net break-even
stop / TP
liquidation distance
close
```

`Cost recovery` is useful because it explains why favorable price movement can
still leave net PnL negative. It must not become a progress challenge that
encourages holding.

One possible secondary item is:

```text
AMOUNT AT RISK
$10.00
```

Do not add another changing indicator merely to fill space. Position state is
already information-dense.

## Leverage Across Asset Classes

Leverage should be a risk and route term, not the identity of the market.

The scanner ranks the market before leverage. The preset then determines:

```text
effective exposure
cost as percent of collateral
liquidation distance
stress loss during measured close latency
```

The same leverage value does not imply the same risk across BTC, EUR/USD, a
stock, and gold. Suggested leverage should eventually derive from:

```text
user loss budget
market's recent stress movement
route cost
p95 close latency
gap risk
venue and policy bounds
```

For the demo, 500x can remain explicitly experimental where supported. It must
not be used to make a dead market qualify as active.

## Cross-Asset Language

Use normalized retail language:

| Internal concept | Consumer label |
| --- | --- |
| realized absolute return ratio | pace |
| cost coverage ratio | movement vs cost |
| range percentile | near 1H high/low |
| market session | open / closed / opens in |
| event restriction | event risk / terms elevated |
| venue health | route ready / delayed |
| instrument expiry | contract rolls / closes at |

Do not hide material structural differences. If a stock or index cannot be
closed outside its route's market hours, the position screen must say so before
opening.

## Me: Review, Configure, Fund

Me should remain operational:

```text
available balance
deposit / withdraw
active preset
history
settings
```

History should optimize understanding rather than status:

```text
net result
cost
duration
end reason
execution path
```

No real-money leaderboard or trade streak is needed.

## Notifications

Potentially useful:

```text
a user-defined market becomes ACTIVE and AVAILABLE
a live position reaches a user-defined risk state
venue stop, TP, liquidation, or close executes
deposit or withdrawal completes
```

Avoid:

```text
you lost, win it back
market pumping, trade now
maintain your streak
another user made money
```

Default notification success is not taps or resulting trade count. It is
relevance, comprehension, and low false-positive rate.

## Product Success Metric

The north-star candidate is:

```text
qualified market understanding
```

Operational proxy:

> Percentage of sessions in which the user can correctly identify why the
> market is ranked, state the ticket/cost/risk terms, and either make one
> intentional trade or deliberately wait.

Supporting metrics:

```text
time to understood candidate
quote-to-gesture comprehension
estimated-to-realized cost error
open and close execution correctness
eventual reconciliation
result comprehension
return for another qualifying market
```

Trades per session is a guardrail metric, not the objective.
