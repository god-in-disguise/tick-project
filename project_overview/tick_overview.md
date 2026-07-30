# TICK Overview

Status: private alpha, July 2026.

TICK is a mobile-first market discovery and trading product. It ranks markets
that are moving, presents one market at a time, and lets a user open or close a
leveraged position with a gesture. The interface stays simple while the backend
handles wallets, quotes, execution, venue events, accounting, and recovery.

The current product is live on Arbitrum with gTrade/Gains as its first
execution venue. It also has a fully isolated demo mode that uses the same live
market feed and delayed fill model without sending blockchain transactions.

## Commercial Summary

Most trading apps begin with a pair list or a professional terminal. TICK begins
with the question: **what is moving now?**

Pulse ranks active markets. TICK turns the selected market into a focused
mobile trading loop. Me holds the user's balance, risk preset, history, and
account controls.

The product is intended for people who want a clearer way to participate in
short-term market movement without learning a full derivatives terminal. It
does not predict direction or promise profit. It helps users find activity,
understand the trade terms, execute, and see the result after costs.

Potential revenue sources are:

- a disclosed execution or routing fee;
- venue fee-sharing agreements;
- a paid TICK Pro subscription;
- partner integrations using the TICK execution and discovery API;
- sponsored campaigns or points programs that do not alter execution truth.

No broad public launch or stable revenue model is active yet.

## Product Surfaces

### Pulse

Pulse is the discovery screen.

- Ranks the currently supported markets by observed activity.
- Shows price, recent movement, market character, and short live history.
- Uses plain-language states such as `SURGING`, `DUMPING`, `SWINGING`,
  `NEAR 90s HIGH`, and `NEAR 90s LOW`.
- Opens a selected market in TICK.

The current scanner is useful product instrumentation, not a proven alpha
signal. The planned TICK Engine will evaluate every signal against later
movement and route cost before stronger claims are made.

### TICK

TICK is the main trading surface.

- Displays a truthful live price tape from the shared backend feed.
- Shows the active amount, leverage, estimated costs, stop loss, take profit,
  exposure, and liquidation information where available.
- Swipe up opens long; swipe down opens short.
- Horizontal swipes change markets while the user is flat.
- An explicit Close button remains available during a position.
- Live PnL is an estimate of the net result if the position closed now.
- Opening, live, closing, closed, stopped, liquidated, failed, and recovery
  states are visually distinct.
- The 90-second live tape can expand into a one-hour context view using the
  same price source.

### Me

Me is the account surface.

- Shows available USDC or the active demo balance.
- Provides deposit and withdrawal controls in Live mode.
- Holds the active amount, leverage, stop-loss, and take-profit preset.
- Shows completed trades, net results, win rate, and liquidation filtering.
- Switches between the Live and Demo trading profiles.
- Resets a demo season after confirmation.
- Provides account and sign-out controls.

## User Actions

### Join

Private-alpha users enter with an invite code. The backend issues a signed
session JWT and restores the same user and wallet on later logins with that
code. Email linking and Google authentication are not active.

### Deposit

Each user has one platform-created Arbitrum wallet. The app displays its USDC
deposit address and refreshes the onchain balance. Only Arbitrum USDC is treated
as trading collateral.

### Configure

The active preset is applied to each opening gesture:

- collateral amount;
- leverage;
- optional venue stop-loss budget;
- optional venue take-profit budget.

The venue can require a higher minimum collateral for a specific market. The
UI must show that requirement before opening.

### Open

1. The PWA requests a short-lived quote.
2. The quote captures the selected market, side, collateral, leverage, costs,
   stop, take profit, liquidation estimate, profile, season, and venue terms.
3. The API validates the session, quote age, balance, active-position rule, and
   idempotency key.
4. Postgres stores the trade intent, execution attempt, and opening position
   before a job is queued.
5. The worker builds and signs the venue transaction.
6. A delegated platform agent submits the transaction and pays Arbitrum gas.
7. gTrade records the market-order initiation onchain.
8. Its oracle fulfiller submits a second callback transaction that creates the
   position at the venue.
9. Direct contract events, the Gains event stream, and position snapshots feed
   the local state reducer.
10. The PWA receives the confirmed position state.

A successful initiation transaction does not by itself mean the position is
filled. The venue callback establishes economic execution. Recent canaries
commonly reached visible execution in roughly two to four seconds, with
variation from RPC, Arbitrum sequencing, and the venue oracle. This is not an
SLA.

### Watch

The shared market stream updates the chart and estimated PnL. Entry,
break-even, stop, take-profit, and liquidation overlays use the position's real
terms. The UI stops treating a position as exposed when an authoritative close,
stop, or liquidation event is observed.

### Close

1. The API locks the current position and creates an idempotent close intent.
2. A worker immediately submits the close from cached normalized position
   state.
3. The venue validates whether the position still exists.
4. The gTrade callback executes the close.
5. The UI moves to `Closed · finalizing result`.
6. Venue cash flow, wallet balance, trading fees, and platform gas charges are
   reconciled.
7. The final net result replaces the estimate.

The close path does not block on a pre-submit REST revalidation during normal
operation. Recovery checks run after submission or when local state is unknown.

### Withdraw

The user enters an Arbitrum destination and USDC amount. The backend validates
balance and account state, stores an idempotent withdrawal request, signs from
the user's platform wallet, broadcasts it, and records gas accounting.
Withdrawals are unavailable while a position or withdrawal is already active.

## Live And Demo Profiles

Every account has two isolated profiles.

**Live**

- Uses the user's real USDC wallet.
- Sends real delegated gTrade transactions.
- Includes real venue fees, market movement, and platform gas charges.
- Preserves live positions, history, reconciliations, and balance.

**Demo**

- Starts each season with `$1,000`.
- Uses the same real market feed and venue quote calculations.
- Simulates open fills after approximately `1.25-1.65s`.
- Simulates manual close fills after approximately `0.95-1.35s`.
- Requotes at simulated fulfillment time instead of filling at the swipe price.
- Applies opening cost, closing cost, PnL, stop loss, take profit, and
  liquidation.
- Runs a backend risk monitor even when the phone is backgrounded.
- Never signs or broadcasts a blockchain transaction.

A user cannot switch profiles or reset Demo while any position is active.

Resetting Demo creates a new season and restores `$1,000`. The previous
season's starting balance, ending balance, realized PnL, trade count, win count,
and reset time are stored in an append-only reset record.

## Technical Architecture

```text
iOS PWA on Vercel
        |
        | HTTPS + JWT + server events
        v
FastAPI API on DigitalOcean
        |
        +-- Postgres: durable users, wallets, profiles, trades and ledger
        +-- Redis: job queue, cache and live distribution
        +-- ARQ worker: open, close, withdrawal and reconciliation jobs
        +-- Market feed: shared live prices and retained bars
        +-- Venue events: direct gTrade/Gains execution observations
        +-- Caddy: TLS and API reverse proxy
        |
        v
Venue adapters
        |
        +-- gTrade/Gains on Arbitrum: active live route
        +-- Aark: researched and canary-tested, not an active product route
```

The backend is one modular Python codebase with separate process roles. It is
not split into microservices.

### Data Model

The durable core includes:

- `User` and authentication identities;
- encrypted per-user `WalletAccount`;
- Live and Demo `TradingProfile`;
- immutable `Quote`;
- user-authorized `TradeIntent`;
- transaction-level `ExecutionAttempt`;
- normalized economic `Position`;
- accounting `Reconciliation`;
- append-only `LedgerEvent`;
- `Withdrawal`;
- audited `DemoProfileReset`;
- retained market observations and one-second bars.

Trade intent, transaction execution, economic exposure, and financial
reconciliation are separate lifecycles. Workers and venue listeners store
observations; normalized position state is persisted before it is published.

### Wallet And Gas Model

The current private alpha is custodial:

- TICK creates one Arbitrum wallet per user.
- Private keys are encrypted before storage in Postgres.
- The encryption key lives in the backend environment.
- The user wallet owns its USDC and gTrade position.
- A platform agent is delegated to open and close for the user.
- The platform agent pays ETH gas.
- Gas is priced in USD and recorded as a USDC charge in the trade ledger.

This avoids requiring users to hold ETH. Encrypted database custody is suitable
for a controlled alpha, not the intended final security model. KMS/HSM-backed
keys, external wallets, embedded-wallet providers, stronger operator controls,
and legal custody review remain future work.

### Market Data

One backend feed is shared by every user. The system does not open one venue
price connection per phone.

- The live chart stores real observations only.
- Rendering can animate between real observations without modifying history.
- One-second bars are retained for context and research.
- Current retention is 24 hours for the selected market universe.
- The live view uses roughly 60-90 seconds.
- The context view can show one hour.
- Execution quotes and fills use the active venue's price and rules.

Longer-term discovery may use broader market-data sources, while final quote,
risk, and execution truth must remain tied to the selected venue.

### API

The PWA currently uses a private REST API plus a server event stream.

Main endpoint groups:

- invite authentication and session restoration;
- account and trading-profile state;
- market list, tape, chart, and retained bars;
- wallet balances, deposit address, withdrawals;
- quote, open, close;
- Demo mode switch and season reset;
- account state and event delivery.

Write operations require JWT authentication and idempotency keys. The same key
with a different payload is rejected. Jobs are stored before execution. The
signed transaction hash is persisted before ambiguous live broadcasts where
the venue path supports it.

This API is not public or versioned for external developers. A future partner
API should expose the same venue-agnostic primitives rather than gTrade
contract details.

## Venue Abstraction

The consumer app works with:

- market availability;
- collateral and notional;
- leverage limits;
- opening and closing cost;
- stop, take profit, and liquidation;
- expected open and close time;
- position and settlement state.

Venue-specific contract calls, indices, decimals, events, and recovery rules
remain inside adapters. gTrade is the only active live venue. Aark requires a
working partner authorization path before it can become a seamless route.

## Points Program

Points are planned, not shipped.

The first useful version can award separate Live and Demo points for:

- completing explainable trades;
- using risk controls;
- maintaining a positive season result;
- participating in time-limited Demo competitions;
- reporting reproducible product issues.

Reset count and season history are already recorded. Points should not reward
raw leverage, liquidation, or meaningless volume because those incentives
would conflict with user outcomes and produce easy abuse.

## Current Limits

- Private invite-only alpha.
- Platform custody with environment-managed encryption.
- One active position and one command in flight per user.
- One active live venue.
- Market orders and full closes only.
- No partial close or position resize.
- Scanner labels are observational and not validated trading signals.
- gTrade fees can be large relative to small collateral at extreme leverage.
- Execution time depends on external RPC, sequencer, oracle, and venue systems.
- Regulatory, jurisdiction, derivatives, and custody requirements are not
  complete for a public launch.
- Production operator tooling, automated incident controls, and security review
  need further work.

## Roadmap

### 1. Private Alpha

- Run repeated Live and Demo cycles with teammates.
- Track execution latency, failures, liquidations, PnL differences, and resets.
- Improve the gesture, chart context transition, and mobile state presentation.
- Add operator views for every intent, transaction, event, and reconciliation.

### 2. TICK Engine

- Centralize cross-market activity scoring.
- Distinguish directional and oscillating market regimes.
- Add participation, range context, cost coverage, and route availability.
- Shadow-score signals against 10-second, 30-second, 60-second, and five-minute
  outcomes.
- Use evidence to decide which labels deserve product prominence.

### 3. Safer External Beta

- Upgrade key storage and operational access controls.
- Add jurisdiction and eligibility controls.
- Add global, venue, market, and user kill switches.
- Formalize limits, disclosures, incident recovery, and reconciliation alerts.
- Certify reconnect, restart, duplicate request, ambiguous transaction, stop,
  and liquidation behavior under failure injection.

### 4. Multi-Venue And Cross-Asset

- Add a second venue only after its quote, execution, event, cost, and recovery
  behavior passes canary certification.
- Route by asset availability, cost, liquidity, leverage, latency, and health.
- Expand discovery toward crypto, indices, commodities, FX, and equities where
  data, venue support, and regulation allow.

### 5. TICK Pro Web

TICK Pro will expose more of the same engine rather than becoming a separate
trading backend.

Planned Pro controls include:

- multi-chart workspaces and longer timeframes;
- order types, bracket orders, reduce-only and partial close;
- funding, open interest, volume, spread, depth, and liquidation context;
- venue and route comparison;
- advanced leverage and margin controls;
- detailed execution timelines and fee attribution;
- alerts, watchlists, saved layouts, and API access.

The consumer PWA remains the focused mobile product. Pro web serves traders who
want more control and makes the shared execution infrastructure inspectable.

## Product Standard

TICK is ready for controlled teammate and investor demonstrations. It is not
ready for unrestricted public money.

The product is successful when it can repeatedly:

1. identify an active and executable market;
2. show the real terms before the gesture;
3. create or close exposure without duplicate actions;
4. display honest position state while execution is pending;
5. explain the final result through market PnL, venue costs, gas, and wallet
   reconciliation.
