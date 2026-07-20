# GMTrade

Snapshot: 2026-07-13.

Status: official documentation reviewed, public market feed measured, signed simulations passed, and three live BTC 100x open/close canaries completed from the TICK test wallet.

## Bottom Line

GMTrade is strong for TICK's high-leverage thesis, but the first live canaries make it a weak fit for the instant mobile loop as the primary venue.

Its live feed currently exposes much more than 100x on major crypto markets, low headline order fees, broad crypto/RWA coverage, and GT points that are explicitly connected to participation in its TGE. The problem is execution lifecycle latency. A user transaction creates an order on Solana; the actual trade happens only when a keeper later executes that order with pull-oracle data. In the live canary, this keeper leg consistently added about 4-5 seconds after the request transaction landed.

GMTrade is still useful as a high-leverage/pro/research venue. For the core TICK loop, Pacifica or another faster matching/execution model remains the required comparison.

## How It Works

- GMTrade is a self-custodial, Solana-based perpetual protocol derived from the GMX V2 pool model.
- GM/GLV liquidity pools are the counterparty rather than a central limit order book.
- A user submits an on-chain order request. A keeper later executes it using current oracle data.
- Positions keep their own collateral. Orders for the same market, collateral, and direction can modify the existing position, so TICK must track the exact position and order addresses.
- Max leverage is dynamic. It decreases as pool open interest rises and is checked when a position is opened or increased.
- Capacity is constrained by both configured open-interest limits and available pool reserves.
- Price impact can be positive or negative depending on whether the order improves the pool's long/short balance.

This fits TICK's isolated-position model, but it is a two-stage lifecycle. A landed request transaction is not the same thing as an open position.

## Live Market Snapshot

TICK subscribed to GMTrade's public `indexTokens` WebSocket feed on 2026-07-13. The feed reported 68 markets, all with GT enabled.

```text
BTC       500x     4 pools
ETH       294.1x   4 pools
SOL       250x     3 pools
BNB       250x     2 pools
AVAX      250x     1 pool
XRP       250x     2 pools
DOGE      200x     2 pools
XAU/XAG   200x     1 pool each
29 markets at exactly 100x
US forex  roughly 460x-500x
US stocks 50x in the live feed
```

In total, 54 of the 68 markets were at 100x or above at the time of measurement. The static RWA documentation advertises up to 500x during trading hours, but the live feed is the authority for a specific order: equities were capped at 50x in this snapshot while forex carried the highest RWA leverage.

Major-market capacity fields were comfortably above TICK's expected size:

```text
Market  Current max  Configured OI headroom      Reported directional liquidity
BTC     500x         $82.7m long / $83.2m short  about $0.89m / $0.88m
ETH     294.1x       $83.4m long / $83.6m short  about $0.69m / $0.69m
SOL     250x         $62.7m long / $62.9m short  about $1.07m / $1.08m
```

A `$20` ticket at 100x is `$2,000` notional. Liquidity is therefore not the limiting factor for a TICK canary on BTC, ETH, or SOL. The connector must still simulate each order because max leverage, reserves, price impact, and long/short imbalance change continuously.

## Leverage Decision

GMTrade can satisfy the product's 100x requirement today. It does not mean TICK should use the venue maximum.

```text
$20 at 100x =  $2,000 notional
$20 at 250x =  $5,000 notional
$20 at 500x = $10,000 notional
```

At 500x, a tiny adverse move can liquidate the position and fees consume a material part of collateral. TICK should initially cap its product preset at 100x even where the venue reports 250x-500x. Activity can select the market; a risk and cost gate should decide whether 100x is currently tradeable.

## Cost

Official base open/close fees are:

```text
Forex:                    0.004% or 0.006% per fill
Crypto, stock, commodity: 0.010% or 0.012% per fill
```

The lower fee applies when the order improves pool balance; the higher fee applies when it worsens balance. Before price impact, borrowing, funding, and Solana execution costs, the simplified round-trip crypto fee consumes approximately:

```text
100x: 2.0%-2.4% of margin
250x: 5.0%-6.0% of margin
500x: 10.0%-12.0% of margin
```

This makes 100x economically credible for the short TICK loop. The 500x headline is useful market coverage, not a sensible default preset.

## Points And Commercial Upside

- GT points are awarded for trading, liquidity, and referrals.
- The documentation explicitly says GT points serve as credentials for participation in the TGE.
- GT minted from trading depends on order fees after discounts. The initial minting cost is `$0.01` per GT and increases by 2.1% for each 210,000 GT cycle.
- Referred users receive a 10% order-fee discount. Referrers receive GT rebates based on VIP level.
- Self-referral and mutual referrals are prohibited.

This is more concrete TGE alignment than Pacifica's current public points language. It still is not guaranteed token value. TICK should ask GMTrade for a direct integration or builder agreement rather than assume referral GT is a durable revenue model.

## Integration

GMTrade publishes its programs and an official Rust SDK. The current `gmsol-sdk` is version 0.9.0 and includes transaction builders, simulations, JavaScript support, callbacks, and optional Jito sending.

There is no documented high-level Python SDK. The practical choices are:

1. Keep FastAPI and the rest of TICK in Python, with a small Rust execution sidecar built on the official SDK.
2. Build a Python connector from the published Anchor IDLs using `solders`, while porting the required simulation and account-discovery logic.

The first choice is lower protocol risk. The second keeps one language but gives TICK ownership of more moving instruction/account logic. Either can sit behind the same `VenueConnector` contract.

Estimated effort after funding a Solana test wallet:

```text
public scanner and capacity gate:      already proven
signed Rust-SDK happy-path canary:     1-2 focused days
Python-native happy-path connector:    2-4 focused days
recovery, reconciliation, and limits:  another 2-4 focused days
```

## Latency

The live canary confirms the protocol lifecycle:

```text
build and sign request
-> Solana request transaction lands
-> keeper observes executable order
-> keeper/oracle execution transaction lands
-> position account update is observed
```

Solana request transactions are not the whole story. The keeper step dominates actual fill visibility, and the frontend's source code correctly refreshes position state after execution rather than treating request submission as final.

TICK can show an immediate local pending position after signing, but must not display executable PnL as if the fill already exists.

## Live Canary Results

On 2026-07-13, TICK ran three live BTC-USD canaries from the test wallet:

```text
ticket:       $20 collateral
leverage:     100x
notional:     $2,000
hold time:    3 seconds after stop creation
route:        GMTrade BTC-USDC market
submit path:  Python direct JSON-RPC using the official CLI only for transaction build
```

Final state was clean:

```text
positions: []
orders:    {}
```

Aggregate timings:

```text
avg open request confirmation:   8.96s
avg open usable/visible:        14.43s
avg stop request confirmation:   4.63s
avg close request confirmation:  5.47s
avg close complete/gone:         9.21s

total USDC delta: -1.473388
total SOL delta:  -0.000657558
```

Per-run timings:

```text
1 long:  open usable 10.49s, close complete  8.09s, USDC -0.754698
2 short: open usable  9.79s, close complete 11.01s, USDC -0.194582
3 long:  open usable 23.01s, close complete  8.54s, USDC -0.524108
```

The third open was an outlier because the request transaction confirmation took `14.75s`. The transaction paid only the `5,000` lamport base fee; no compute-budget priority instruction was present in the serialized transaction we submitted. This means our `priority_lamports` setting did not actually prioritize the user request path. That can be improved, but it does not remove the keeper leg.

## Where Time Was Lost

The observed open path splits into these buckets:

```text
pre-execution safety reads:
  read positions: 1.49-1.78s
  read orders:    1.43-2.92s

quote/build/simulation preview:
  keeper quote:   0.44-0.98s
  build open tx:  1.88-2.03s
  sign/simulate:  0.95-1.30s
  read balances:  1.02-2.08s

live open request:
  build tx:       1.95-2.20s
  blockhash/sign: 0.48-0.54s
  send RPC:       0.51-0.57s
  confirmation:   1.24-1.39s normal, 14.75s outlier

keeper execution after request lands:
  open keeper fill: 4-5s on-chain
  close keeper fill: about 4s on-chain
```

On-chain signatures show the exact two-step flow:

```text
user open tx:
  PreparePosition
  PrepareUser
  CreateOrderV2

keeper open tx:
  PrepareTradeEventBuffer
  ExecuteIncreaseOrSwapOrderV2
  CloseOrderV2

user close tx:
  PrepareUser
  CreateOrderV2
  SetShouldKeepPositionAccount

keeper close tx:
  UseClaimableAccount
  PrepareTradeEventBuffer
  ExecuteDecreaseOrderV2
  CloseOrderV2
  CloseEmptyClaimableAccount
```

Keeper executions consumed roughly `230k-325k` compute units. User request transactions consumed roughly `49k-154k` compute units and paid only base Solana fees in this canary path.

There were also failed keeper-side/cancel attempts with `Custom 3011 / AccountNotSystemOwned` around stop/order cleanup. They did not leave user exposure open, but they show the venue lifecycle is asynchronous and state-dependent. TICK must expect races between order, position, and cleanup state.

## Why It Feels Slow

GMTrade is not slow because Solana itself is slow. It is slow for TICK because the venue is not a direct immediate-fill matching venue.

For a market order, the user does not directly receive a final filled position. The user creates a request. A keeper then:

1. observes the order,
2. prepares fresh oracle data,
3. executes the order,
4. closes the order account,
5. then the app/indexer observes the changed position.

That design is reasonable for a GMX-style oracle/pool perpetual protocol, but it conflicts with TICK's desired "swipe, feel the fill now" product loop.

## What Can Be Improved

TICK can remove several local delays:

```text
replace CLI transaction building with a resident connector
cache static accounts and ALTs
parallelize preflight reads
use direct account/RPC subscriptions instead of CLI polling
add real compute-budget priority instructions
consider Jito/priority sending where supported
avoid creating stop orders when the product uses manual close-only testing
```

Expected savings:

```text
local build/read overhead: can probably save 2-5s
Solana confirmation outliers: can probably reduce with priority/Jito
keeper fill leg: probably still 4-5s unless GMTrade offers a faster/private keeper path
```

The critical unsolved issue is the keeper fill leg. Even a perfect connector is unlikely to make GMTrade feel like an instant execution venue unless we get direct/private keeper support or accept optimistic UI that later reconciles.

## Deeper Executor Finding

The first live canary used the official CLI only to build user request transactions. That binary was not compiled with the `execute` feature, so it did not expose:

```text
gmsol exchange execute <ORDER_ADDRESS>
```

After rebuilding `gmsol-cli` with `--features execute`, the command exists and can construct/send an executor transaction for an order account. This is the missing path that must be tested before permanently rejecting GMTrade.

The important catch is permissioning. GMTrade source marks both execution instructions as keeper-only:

```text
execute_increase_or_swap_order_v2 -> ORDER_KEEPER required
execute_decrease_order_v2        -> ORDER_KEEPER required
```

The CLI help also says execution "requires appropriate permissions." So this is not normal user self-execution unless GMTrade grants TICK an order-keeper role, exposes an approved executor lane, or lets integrators run through a permissioned keeper service.

This changes the interpretation:

```text
public keeper path:        measured, too slow for TICK core loop
private/order-keeper path: possible in code, not yet measured, needs GMTrade permission
normal user wallet path:   cannot be assumed to execute orders directly
```

If TICK can operate an order keeper, the GMTrade latency target becomes:

```text
create order tx lands
-> TICK executor immediately builds oracle bundle
-> TICK executor submits execute tx with priority/Jito
-> position visible from direct account subscription
```

That still remains a two-transaction lifecycle, not a single immediate fill. The test that matters is therefore not another public keeper run. The next GMTrade test is a permissioned/self-executor canary measuring request landing, execute submission, execute landing, and position visibility separately.

## Signed Simulation Results

On 2026-07-13, TICK used the official `gmsol` v0.9.0 builder and a funded test wallet to construct the BTC single-USDC-pool transaction. The Python probe replaced the serialization-only placeholder blockhash, signed the exact v0 message in memory, and submitted it to `simulateTransaction` with signature verification enabled. It did not broadcast.

```text
BTC long   $20 collateral   100x   $2,000 notional   passed   134,234 CU
BTC short  $20 collateral   100x   $2,000 notional   passed   126,723 CU

long:   1.825s SDK build + 0.457s blockhash/sign + 0.448s simulation
short:  1.842s SDK build + 0.448s blockhash/sign + 0.473s simulation
```

These are cold command-line build and RPC preflight timings, not user-visible execution latency. A resident connector should cache static account discovery and remove CLI startup overhead. Keeper fill latency remains unmeasured until a live canary is submitted.

The first simulation also exposed a meaningful setup requirement. With `0.042578434 SOL`, the new wallet ran out of lamports while `CreateOrderV2` tried to allocate the order account. It had `0.007925834 SOL` left at that step and needed `0.018096 SOL`. After funding the wallet to `0.142578434 SOL`, both directions passed. The extra requirement comes from first-use user, position, escrow, and order account rent plus execution/transaction fees; it is mostly independent of the USD ticket size. TICK should preflight SOL and keep at least `0.10 SOL` in a test execution wallet until steady-state refundable rent and consumed fees are measured from a live lifecycle.

The official market-order builder permits `acceptable_price` to be omitted. TICK must not do that in production. The connector must attach a fresh, side-aware acceptable price and reject stale quotes before signing.

TICK subsequently added a keeper-GraphQL fallback for the public WebSocket. On the guarded BTC-long simulation, GMTrade reported an open oracle range of `$62,247.27-$62,248.77` with a `4.5s`-old timestamp. The probe bounded the open at `$62,435.51631` (`30 bps` above the long-side reference), calculated a `$62,030.899305` fallback stop trigger (`35 bps` below reference), and passed at `129,777` compute units.

The stop is not atomic with the market increase. GMTrade requires a separate stop-loss decrease order after the position exists. TICK must expose that gap honestly and close immediately when stop creation fails; a calculated trigger is not protection until its order transaction has landed.

## Risks And Constraints

- Dynamic leverage can fall between feed display and order execution.
- Pool imbalance creates price impact even for market orders.
- Trigger orders may freeze when acceptable price, liquidity, or leverage checks fail.
- Synthetic markets can use auto-deleveraging when pending trader profit exceeds configured thresholds.
- The terms prohibit U.S. persons, sanctions-restricted users, circumvention using VPNs, and abusive practices including wash trading.
- The terms state that gmtrade.xyz is not licensed or registered by a regulator. TICK still needs its own legal launch model and user-eligibility policy.
- The existing `WALLET_PK` used for Ostium is an EVM key. A live GMTrade canary requires a separate, test-only Solana wallet funded with USDC and SOL.

## First Signed Canary

1. Create a test-only Solana wallet and fund it with a small amount of SOL and USDC.
2. Read the live BTC pools and select the route with sufficient reserve capacity and smallest simulated price impact.
3. Build both directions with a fresh acceptable price, then simulate a `$20` collateral, 100x order; reject if max leverage or total cost moves outside tolerance.
4. Submit the create-order transaction with priority/Jito settings recorded.
5. Observe the request signature, order account, keeper execution signature, trade event, and position account.
6. Close reduce-only after three to ten seconds and measure the same lifecycle.
7. Reconcile collateral, realized price PnL, open/close fees, impact, borrowing/funding, execution cost, and final wallet balance.
8. Repeat for short, duplicate intent, stale quote, reconnect, keeper delay, and rejected capacity cases.

## Current Recommendation

GMTrade should not be the primary venue for the first TICK mobile loop on the public keeper path. It can stay in contention only if GMTrade gives TICK an order-keeper/private executor route and live tests prove that create-order plus execute-order can feel close to instant.

The likely two-venue starting shape is:

```text
GMTrade: high leverage, broad feed, RWA expansion, explicit TGE points, slower keeper lifecycle
Pacifica: faster CLOB-style 50x crypto route and latency benchmark
```

Do not choose between venues from leverage alone. The next venue tests should compare visible fill latency, all-in net cost, failure rate, and reconciliation quality. For the TICK dopamine loop, lifecycle latency matters more than headline leverage once the venue supports at least 50x-100x.

## Primary Sources

- [GMTrade introduction](https://docs.gmtrade.xyz/)
- [Trading and dynamic leverage](https://docs.gmtrade.xyz/about/trading/)
- [Trading fees and price impact](https://docs.gmtrade.xyz/about/trading_fees_and_rebates/)
- [RWA leverage](https://docs.gmtrade.xyz/about/rwa_markets/)
- [Liquidity pools](https://docs.gmtrade.xyz/about/providing%20liquidity/)
- [GT points](https://docs.gmtrade.xyz/about/gt_point_system/)
- [Referrals](https://docs.gmtrade.xyz/about/referrals/)
- [User terms](https://docs.gmtrade.xyz/legal/user_terms/)
- [Open-source protocol and integration example](https://github.com/gmsol-labs/gmx-solana)
- [Rust SDK 0.9.0](https://docs.rs/gmsol-sdk/latest/gmsol_sdk/)
