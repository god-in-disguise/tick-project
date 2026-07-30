# Current MVP Readiness and the TICK Formula

Last reviewed: 2026-07-30

## Executive Answer

TICK is already a credible live product prototype. It is not yet an
evidence-backed trader discovery tool.

The current build has crossed the difficult threshold from interface concept
to real financial plumbing:

```text
shared live prices
durable market history
real quote terms
real delegated execution
venue event detection
net-result reconciliation
per-user wallets and gas accounting
```

What remains unproven is the part most capable of making TICK genuinely useful:

> Does Pulse reliably find movement that is unusual, available, and large
> enough relative to execution costs to deserve a trader's attention?

The current answer is a promising prototype, not yet a validated yes.

## Readiness by Outcome

These percentages are judgment calls based on current code and observed live
canaries. They are not project-completion metrics.

| Outcome | Readiness | Reason |
| --- | ---: | --- |
| Team and investor demonstration | 85% | The differentiated loop, live chart, real money path, wallet, and results exist. Remaining work is reliability and presentation polish. |
| Controlled funded crypto alpha | 65% | The one-user lifecycle is real and the multi-user domain exists, but recovery, reconciliation, and operational canaries need more repetitions. |
| Discovery tool an experienced trader can trust | 45% | Pulse is understandable and attractive, but its ranking has not been historically calibrated or tested against subsequent movement. |
| Cross-asset discovery product | 25% | The design model exists and gTrade exposes several asset classes, but normalized sessions, gaps, events, route capabilities, and baselines are not implemented. |
| Product proven to improve trader outcomes | 10% | There is no user study or controlled outcome evidence yet, and external research says persistent net profitability is rare. |

The most accurate overall description is:

> TICK is roughly halfway to a genuinely useful trader tool, but much closer to
> a compelling private demonstration.

## What Is Already Real

### One shared market source

The gTrade public client starts one process-level price stream and uses that
shared stream for market summaries and charts. It does not create a separate
upstream feed for each user.

Evidence:

- [`GTradePublicClient`](../../../builds/tick-mvp/backend/tick_mvp/venues/gtrade/public.py#L48)
- [shared price-stream initialization](../../../builds/tick-mvp/backend/tick_mvp/venues/gtrade/public.py#L63)

### Durable truthful chart history

Real observations are reduced into one-second OHLC bars, written in batches to
Postgres, and retained for 24 hours. The record also preserves sample count and
source sequence.

Evidence:

- [`PostgresMarketHistory`](../../../builds/tick-mvp/backend/tick_mvp/infrastructure/market_history.py#L68)
- [bar persistence](../../../builds/tick-mvp/backend/tick_mvp/infrastructure/market_history.py#L204)
- [24-hour pruning](../../../builds/tick-mvp/backend/tick_mvp/infrastructure/market_history.py#L262)

This is enough for LIVE and one-hour context. It is not enough to estimate a
stable same-time-of-week baseline.

### Production-shaped execution primitives

The schema separates:

```text
Quote
TradeIntent
ExecutionAttempt
Position
VenueEvent
Reconciliation
LedgerEvent
```

It also stores idempotency request hashes, nonces, deterministic transaction
hashes, financial reconciliation, and deduplicated venue logs.

Evidence:

- [quote and intent persistence](../../../builds/tick-mvp/backend/tick_mvp/infrastructure/models.py#L89)
- [execution attempts and positions](../../../builds/tick-mvp/backend/tick_mvp/infrastructure/models.py#L133)
- [venue events and reconciliation](../../../builds/tick-mvp/backend/tick_mvp/infrastructure/models.py#L218)
- [ledger events](../../../builds/tick-mvp/backend/tick_mvp/infrastructure/models.py#L249)

This is a strong seed for a real build. It should be hardened, not replaced.

### Cross-asset runtime is still narrow

The current gTrade metadata adapter recognizes FX, commodities, and indices,
then treats every remaining symbol as crypto. Equities and rates do not yet
have their own runtime capability or lifecycle model.

Evidence:

- [current asset-class classifier](../../../builds/tick-mvp/backend/tick_mvp/venues/gtrade/public.py#L374)

This is acceptable for the crypto MVP. It means cross-asset breadth should
first run as shadow discovery work, not be represented as a finished execution
capability.

## The Current Discovery Formula

There are currently two related but different scanner calculations.

### Backend ranking

For each watchlist market, the backend calculates:

```text
active_tape_pct = 60-second high-low range / current price
fee_hurdle_pct  = opening fee * 2
surplus_pct     = active_tape_pct - fee_hurdle_pct

score =
  active_tape_pct * 1000
  + surplus_pct * 500
```

It then sorts markets by that score.

Evidence:

- [market-summary calculation](../../../builds/tick-mvp/backend/tick_mvp/venues/gtrade/public.py#L137)
- [range helper](../../../builds/tick-mvp/backend/tick_mvp/venues/gtrade/public.py#L413)

Strengths:

- shared across users;
- simple;
- uses real movement;
- includes a first approximation of cost.

Limitations:

- compares raw ranges across markets with different normal volatility;
- uses only opening fee times two, not the full current route cost;
- does not include spread, dynamic price impact, borrowing, slippage, latency,
  or route quality;
- has arbitrary weights;
- has not been evaluated against future movement;
- can over-rank a naturally noisy market and under-rank an unusual move in a
  normally quiet market.

### Client `TAPE HEAT`

Each phone independently constructs two-second bars and compares activity in
the last 10 seconds with activity during the preceding 30 seconds:

```text
bar activity =
  absolute path movement
  + a small changed-update term

tempo ratio =
  average activity over last 10s
  / average activity over prior 30s
```

Thresholds are:

```text
HOT     >= 1.55x
ACTIVE  >= 1.00x
WARM    >= 0.60x
QUIET   <  0.60x
```

Evidence:

- [microbar construction](../../../builds/tick-mvp/frontend/src/marketActivity.ts#L25)
- [tempo calculation and stories](../../../builds/tick-mvp/frontend/src/marketActivity.ts#L78)
- [thresholds](../../../builds/tick-mvp/frontend/src/marketActivity.ts#L127)
- [`TAPE HEAT` rendering](../../../builds/tick-mvp/frontend/src/components/TapeHeat.tsx#L12)

Strengths:

- visually responsive;
- explains acceleration without predicting direction;
- uses only real source observations.

Limitations:

- two users may get different values from different local observation windows;
- ten seconds versus the previous thirty is too short to mean "normal";
- a quiet baseline can make a small move appear extremely hot;
- the UI story and server ranking can disagree;
- the formula version is not persisted with later trade outcomes.

The conclusion is not that the current component is bad. It is that it is a
rendering and product-language experiment that should consume a shared scanner
state rather than own the market definition.

## The New Formula Should Be Three Primitives

Do not replace the current score with a more complicated magic score. The
durable TICK formula is a transparent state vector:

```text
ACTIVE      how unusual is movement for this market now?
TRADEABLE   how large is observed movement relative to current route cost?
AVAILABLE   can this user and route execute the preset now?
```

### ACTIVE

Start with real 90-second and five-minute observations:

```text
current_range_bps
current_path_bps
meaningful_price_changes
range_expansion
```

Normalize them against:

```text
same market
same venue/source
same time-of-week bucket
recent volatility regime
```

Output a robust percentile, not an unexplained raw score:

```text
ACTIVE 87
FASTER THAN 87% OF COMPARABLE WINDOWS
```

Use quantile ranks or median/MAD normalization so a few shocks do not distort
the baseline.

### TRADEABLE

Calculate the current route hurdle for the user's visible preset:

```text
round_trip_cost_bps =
  open fee
  + estimated close fee
  + spread
  + current price impact
  + expected slippage
  + expected holding cost
```

Then expose:

```text
movement_to_cost =
  recent realized range bps
  / round_trip_cost_bps
```

Path movement can support the activity description, but range is a more
conservative cost comparison because repeated oscillation can inflate path
length without giving one directional trade a recoverable move.

Example:

```text
MOVEMENT 1.6x COST
```

This does not mean expected profit. It means the recent observed range was 1.6
times the estimated current route hurdle.

### AVAILABLE

This is a hard gate:

```text
market/session open
feed fresh
route healthy
quote valid
ticket and leverage supported
wallet prepared
user has spendable collateral
no active position or command conflict
no halt or execution restriction
```

Output:

```text
OPEN
CLOSE ONLY
MARKET CLOSED
ROUTE DELAYED
EVENT RESTRICTION
```

### Ranking

Rank lexicographically rather than hiding arbitrary weights:

```text
1. AVAILABLE
2. route and feed confidence
3. ACTIVE percentile
4. movement-to-cost
5. event freshness
```

The row must always expose the components that caused its position.

Leverage must not increase ACTIVE. Leverage changes the user's exposure and
risk; it does not make the underlying market more interesting.

## Data Needed to Make the Formula Real

The current 24-hour one-second store is enough for product context but not for
normality.

Use tiered retention:

```text
one-second bars     24 hours
five-second bars     7 days
one-minute bars     90 days
```

This remains small for a private MVP and provides enough history to build
time-of-week and regime baselines. Store scanner outputs separately with:

```text
scanner_version
market
source
calculated_at
active_percentile
movement_to_cost
availability
route_health
story
```

For every scanner observation, calculate future realized movement over:

```text
10 seconds
30 seconds
60 seconds
5 minutes
```

This is the evidence required to answer whether high-ranked markets remain
more active long enough for a human to use the information.

## Can TICK Democratize Trading?

### Yes, in four concrete ways

TICK can democratize:

1. **Market attention** - monitor many markets continuously instead of making a
   person search charts manually.
2. **Economic comparability** - translate different venues and asset classes
   into movement, cost, availability, exposure, and risk.
3. **Execution access** - compress route mechanics into one visible preset and
   one honest state machine.
4. **Financial understanding** - make net result, cost recovery, liquidation,
   and reconciliation understandable on a phone.

This is meaningful. Professional traders have tools and routines for all four;
many retail users do not.

### No, not in the sense of distributing profitable edge

TICK cannot currently claim to democratize:

```text
predictive direction
positive expected return
profitable day trading
protection from leverage losses
```

The external evidence is unfavorable: persistent net profitability is rare,
costs materially reduce outcomes, and mobile engagement can increase activity
and risk without improving decisions.

The defensible product statement is:

> TICK can democratize access to market discovery and execution truth. It
> cannot democratize profits, but it can make the decision materially less
> blind.

## Highest-Value Next Work

1. Move `ACTIVE`, `TRADEABLE`, `AVAILABLE`, and stories into one versioned
   server-side scanner.
2. Keep the existing chart and interaction component, but make every user
   consume the same scanner state.
3. Add tiered historical rollups and start shadow-scoring every supported
   market.
4. Persist future movement and route outcomes for every score, including
   candidates not shown.
5. Run recent-trade reconstruction and comprehension sessions with current
   testers.
6. Require 30-50 clean execution cycles per route plus restart, stream-gap, and
   ambiguous-broadcast canaries.
7. Add FX, indices, commodities, equities, and rates to discovery in shadow
   mode before enabling their execution.

Do not add a directional signal, social competition, or another venue merely
to make the product look broader. The next moat is the quality and
explainability of market selection.
