# Cross-Asset Market and Scanner Model

Last reviewed: 2026-07-30

## Strategic Call

TICK should be crypto-first and cross-asset by design.

The scanner becomes more valuable as the eligible market universe expands:

```text
instead of asking the user which market to inspect,
TICK continuously asks which supported market is unusually active,
executable, and understandable now.
```

Leverage does not create a good market. It changes how a market move affects
collateral. Market selection and risk configuration must remain separate.

## Candidate Asset Classes

| Asset class | Product value | Current structural issue |
| --- | --- | --- |
| Crypto | 24/7, broad long tail, high natural volatility | funding, fragmentation, liquidation, variable liquidity |
| FX | many liquid macro pairs, high leverage can amplify small moves | 24/5 sessions, rollover, weekend gaps, event restrictions |
| Indices | concentrated macro expression, familiar products | cash hours, gaps, price limits, reference-market state |
| Commodities | event-driven movement across gold, oil, metals | session breaks, contract/reference details, news restrictions |
| Equities | recognizable stories and earnings-driven movement | market hours, halts, dividends, earnings, corporate actions |
| Rates | strong macro-event response and deep futures markets | futures maturity, yield/price inversion, route complexity |

The current gTrade route already demonstrates that one oracle-based venue can
cover more than crypto:

- crypto: over 220 pairs, currently documented at 1.1x-500x;
- FX: over 30 pairs, currently documented at 10x-1000x;
- commodities: gold up to 250x and several metals/oil pairs up to 150x;
- indices: currently documented up to 100x;
- stocks: currently documented up to 50x.

These are venue capabilities, not permanent TICK product limits. They must be
loaded from current route configuration rather than copied into UI code.

Sources:

- [Gains: Crypto](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/cryptocurrencies)
- [Gains: Forex](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/forex)
- [Gains: Commodities](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/commodities)
- [Gains: Indices](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/indices)
- [Gains: Stocks](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/stocks)

## Rates, Not Individual Bonds

Individual cash bonds are not a clean fit for TICK's default loop because many
have limited liquidity and weaker price transparency. Liquid rates exposure is
more plausible through Treasury futures, yield futures, bond ETFs, or a venue's
normalized rates derivative.

CME describes deep centralized liquidity in Treasury and SOFR futures and
offers smaller Micro Treasury and Yield contracts. This makes `rates` the
correct asset-class abstraction; `bond` should identify an underlying exposure,
not imply that TICK is day-trading an individual cash bond.

Sources:

- [Investor.gov: Bonds and Liquidity Risk](https://www.investor.gov/introduction-investing/investing-basics/investment-products/bonds-or-fixed-income-products/bonds)
- [CME: Interest Rate Products](https://www.cmegroup.com/markets/interest-rates.html)
- [CME: Micro Treasury and Yield Futures](https://www.cmegroup.com/articles/2024/micro-treasury-futures-vs-yield-futures.html)

## Normalized Market Capabilities

Every route-market combination should expose:

```text
MarketCapability
  market_id
  venue_id
  asset_class
  underlying
  quote_currency
  reference_price_source
  collateral_assets

  market_state
  session_name
  opens_at
  closes_at
  next_session_at
  close_only
  gap_risk
  halt_state
  scheduled_event_state

  min_ticket_usd
  max_ticket_usd
  min_leverage
  max_leverage
  leverage_step
  stop_supported
  stop_guarantee
  take_profit_supported

  open_fee
  close_fee
  spread
  price_impact
  borrowing_or_funding
  estimated_slippage

  quote_age_ms
  feed_age_ms
  route_health
  p50_open_ms
  p95_open_ms
  p50_close_ms
  p95_close_ms
  reconciliation_quality
```

No gTrade-specific field belongs in the product domain. Connectors translate
their mechanics into these primitives and retain raw venue data for audit.

## Three Separate Scanner Outputs

### 1. ACTIVE

Measures whether the market is moving unusually for itself.

Candidate inputs:

```text
path_movement_bps(window)
realized_range_bps(window)
meaningful_price_changes(window)
range_expansion
break of recent high or low
```

Normalize against:

```text
same market
same session or time-of-week bucket
recent regime
same data source
```

A robust implementation should use medians and median absolute deviation or
quantile ranks rather than a single global mean that is distorted by shocks.

Example output:

```text
FAST
1.8x its normal 90s movement
```

### 2. TRADEABLE

Measures whether the current route economics and conditions permit a sensible
opening for the configured preset.

Inputs:

```text
estimated round-trip cost
spread and current price impact
expected slippage
quote freshness
route latency
liquidity or depth proxy
stress movement during p95 close latency
selected ticket and leverage
```

Useful descriptive ratio:

```text
movement_to_cost =
  recent_realized_path_or_range_bps / estimated_round_trip_cost_bps
```

This ratio is not expected return. It says only that recent observed movement
was large or small relative to the route's estimated hurdle.

Example output:

```text
MOVEMENT 1.6x COST
```

### 3. AVAILABLE

Measures whether an order can actually be accepted:

```text
market session open
route healthy
price fresh
quote valid
pair enabled
ticket and leverage supported
user eligible
wallet prepared
no halt or maintenance
```

Example output:

```text
OPEN
CLOSE ONLY
EVENT RESTRICTION
MARKET CLOSED
ROUTE DEGRADED
```

## Ranking Without a Fake Edge Score

Pulse may need one stable order, but it should preserve the components behind
that order.

Recommended ranking:

```text
1. AVAILABLE for the user's current configuration
2. feed and route health
3. ACTIVE percentile versus the market's own baseline
4. movement-to-cost relationship
5. execution and reconciliation confidence
6. freshness of the detected market event
```

Avoid a single unexplained `Fire Score`. If a compact score is required, every
row must still expose the reason:

```text
ZEC  FAST 1.8x
MOVE 0.17% / COST 0.05%
NEAR 1H LOW
```

## Session and Event Model

Crypto can use a continuous weekly baseline. Other assets require explicit
session state.

Examples:

- NYSE core trading is currently 9:30 a.m.-4:00 p.m. ET.
- CME FX and many futures products trade nearly 23 hours on weekdays but still
  have maintenance windows and expiries.
- gTrade documents weekend gaps and reduced leverage or wider spread around
  news, market close, and low-liquidity periods.
- Stocks add earnings, dividends, corporate actions, and halts.

Sources:

- [NYSE: Trading Hours](https://www.nyse.com/markets/hours-calendars)
- [CME: FX Futures Hours](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-cme-fx-futures-calendar-spreads.html)
- [NYSE: Corporate Actions and Market Watch](https://www.nyse.com/regulation/corporate-actions-market-watch-proxy-compliance)
- [Federal Reserve: FOMC Calendar](https://www.federalreserve.gov/fomc/)
- [BLS: Release Calendar](https://www.bls.gov/schedule/2026/home.htm)

Scheduled events are metadata, not a direction signal:

```text
CPI IN 12m
SPREAD ELEVATED
OPENING PAUSED
```

## Expansion Sequence

```text
1. Crypto live execution through the hardened route.
2. Cross-asset collection and scanner in shadow mode.
3. Display non-crypto candidates only when price, session, and route state are
   trustworthy.
4. Controlled non-crypto canaries by asset class.
5. Enable one class at a time with explicit gap and event behavior.
6. Add a second venue only after its normalized lifecycle reconciles cleanly.
```

Breadth should arrive in discovery before it arrives in live execution.
