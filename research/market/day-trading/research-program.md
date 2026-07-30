# TICK Day-Trading Research Program

Last reviewed: 2026-07-30

## Objective

Validate that TICK shortens the work of finding and understanding an active
market while preserving cost, risk, and execution comprehension.

The program must distinguish:

```text
people enjoy watching the app
people understand the trade
the route executes correctly
the scanner identifies continued movement
people return for the product rather than a reward mechanic
```

## Research Questions

1. What happened immediately before the trader opened their last real
   short-horizon position?
2. How did they discover the market?
3. Which wider timeframe or external context changed their decision?
4. Which terms did they verify before acting?
5. What caused the exit?
6. Could they explain the difference between chart movement and net wallet
   result?
7. When do they decide that no trade is worth taking?
8. Which market classes do they monitor, and why?
9. What information do they need only before opening versus while exposed?
10. Which interruption or background-app failures matter on mobile?

## Qualitative Study

Recruit separately:

```text
crypto perp scalpers
multi-asset retail day traders
mobile-first active traders
experienced traders who stopped day trading
new but funded high-risk traders
```

Do not ask only for preferences. Use a recent-trade reconstruction:

```text
show the last real trade
reconstruct discovery, context, entry, monitoring, exit, and review
identify every app or screen used
record what was known before versus learned after
ask the participant to explain costs and liquidation in their own words
```

Then run a TICK task:

```text
find the most interesting available market
explain why it is ranked
inspect context
state amount, exposure, expected cost, and risk
choose long, short, or wait
explain every opening/closing state
interpret the final result
```

Record comprehension failures, not just task completion.

## Required Product Events

```text
session_started
pulse_candidate_impression
pulse_candidate_selected
market_story_seen
context_opened
context_closed
preflight_terms_seen
opening_gesture_started
opening_gesture_committed
opening_rejected
open_execution_confirmed
position_net_pnl_seen
close_requested
close_execution_confirmed
result_reconciled
result_breakdown_opened
session_ended
```

Every market observation should include:

```text
market_id
asset_class
venue_id
scanner_version
active_percentile
movement_to_cost
availability_state
story_type
story_age_ms
feed_age_ms
route_health
```

Every execution observation should include the existing durable IDs, quote
snapshot, transaction hashes, venue events, latency stages, cost estimate, and
realized reconciliation.

## Scanner Shadow Evaluation

Record every candidate, including candidates not displayed.

For each timestamp, measure future paths:

```text
next 10 seconds
next 30 seconds
next 60 seconds
next 5 minutes
```

Store:

```text
maximum favorable movement
maximum adverse movement
absolute path movement
range
time until movement cooled
whether estimated round-trip cost was crossed
route availability changes
quote and fill drift
```

Evaluate the scanner as a descriptive discovery system:

```text
Did high ACTIVE ranks retain more movement than low ranks?
Did TRADEABLE reject markets whose costs dominated?
Did AVAILABLE correctly predict executable route state?
How often did a story expire before selection?
```

Do not evaluate long/short profitability unless a separate directional model is
explicitly introduced.

## Product Experiments

### A. LIVE and CONTEXT

Compare:

```text
LIVE only
LIVE + one-tap 15m context + 1H range
```

Measure:

```text
market-state comprehension
time to decision
wait rate
context return-state correctness
opening errors
```

### B. Pace Language

Compare:

```text
TAPE HEAT
SWING TEMPO
PACE VS NORMAL
```

The user must be able to answer:

> What changed, over what window, and does this tell you direction?

### C. Scanner Decomposition

Compare:

```text
one opaque score
ACTIVE + MOVE/COST + AVAILABLE
```

Expected result: decomposition should improve explanation without materially
slowing market selection.

### D. Cross-Asset Shadow Feed

Before enabling execution, mix crypto with FX, indices, commodities, equities,
and rates candidates in research mode.

Measure:

```text
whether users understand asset class and market hours
whether ranking across classes feels coherent
whether slower assets become interesting at lower leverage
whether the route constraints overwhelm the simple UI
```

### E. Open and Close Feedback

Test the current honest states against a generic spinner.

Measure:

```text
duplicate gestures
perceived latency
correct understanding of initiation versus venue execution
confidence after recovery or failure
```

## Financial and Behavioral Guardrails

Monitor by user and session:

```text
trades per session
time between a loss and next opening
leverage changes after losses
ticket changes after losses
session realized loss
liquidation frequency
stop removal while losing
number of rejected openings
notification-to-trade conversion
```

These are not proof of harmful behavior on their own. They identify patterns
that need review.

Do not A/B test mechanics whose intended outcome is more turnover without a
user-benefit hypothesis.

## Demo Readiness Gates

Before broader teammate or investor testing:

```text
all visible market values have a named source
market stories have deterministic definitions
no story implies direction
estimated costs reconcile within a documented tolerance
open, close, stop, TP, and liquidation states are distinguishable
history explains final wallet movement
scanner can truthfully return no qualifying market
```

Before enabling a new asset class:

```text
session calendar and market state are correct
gap behavior is understood
event restrictions are represented
stop and liquidation behavior are documented
route costs and leverage are live configuration
open/close/recovery canaries pass
```

## Immediate Research Backlog

1. Run recent-trade reconstruction interviews with the current team testers.
2. Add a short comprehension prompt after selected demo sessions.
3. Start cross-asset shadow collection using normalized market capabilities.
4. Establish per-market, per-session activity baselines.
5. Compare current scanner ranks with future movement and route costs.
6. Audit all notification and animation behavior against the FCA findings.
7. Revisit LIVE/CONTEXT windows only after usage and comprehension data exist.
