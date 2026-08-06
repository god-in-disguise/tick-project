# Flash Trade

Snapshot: 2026-08-06.

Status: shadowed. The TICK adapter completed live `$10 x 500` BTC/ETH
open/close canaries, a live `$10 x 100` BTC cycle, and a funded XAU `100x`
cycle. Its code, wallet isolation, market observations, and execution history
remain available for research. Flash is disabled as a production user route
because positive PnL is reference-capped during its market-specific delay
window, while losses and liquidation remain live.

## Bottom Line

Flash Trade V2 has the strongest measured fast path among TICK's tested gTrade
alternatives. That speed belongs to a structured high-leverage product rather
than the canonical mark-to-market perp model TICK currently wants. For BTC and
ETH Degen positions, positive PnL is delayed for 30 seconds; SOL uses 10
seconds. During that window the closeable positive result is constrained by a
reference price even though losses and liquidation continue normally. TICK
must not display ordinary gross mark PnL as immediately realizable PnL for this
product.

On 2026-08-06, Chronos's remaining Flash balance was withdrawn. The venue
settlement returned `5.000000 USDC` to the user's Solana wallet after the prior
liquidation, and that amount was transferred to the operational Solana wallet.
The user basket is flat with no positions or orders. Production now has only
gTrade enabled and `FLASH_REAL_EXECUTION_ENABLED=false`.

```text
Flash withdrawal action:
5GCWC1xsfQ6gxfYMCa4K1vSpViVv3jRfMq9sJTEBbxwKJP1hYx1ypZmamtaoqXc6PXL8HmVPxhck5SwftMGJEiwC

Chronos -> operational USDC transfer:
46LcoA4VbuRhgUvAToCSEDqRgLu5M8pRv8jwa6ikywD3dY2kurKswX32qGHby2sqTBboZjPN9qeG4mJ5PPJcKty7
```

The documented Degen product supports BTC, ETH, and SOL from 125x through 500x.
The current public API accepted an unsigned `$10 x 500` quote for all three
markets. V2 uses a MagicBlock Ephemeral Rollup and exposes transaction builders,
signed submission, session keys, owner state streaming, and recovery snapshots.

The first funded cycle made the economic position visible in `474 ms` after
submission started and removed it in `444 ms` after close submission started.
Including fresh transaction construction and local signing, the paths were
about `973 ms` open and `624 ms` close. The realized venue result was
`-$1.666698` on a nearly flat `$10 x 500` round trip, versus the quoted `$1.66`
open-plus-close fee estimate.

## Live Cycle Evidence

TICK funded a dedicated Solana canary on 2026-08-04 with `0.067875411 SOL` and
`31.289278 USDC`.

The following setup actions succeeded:

```text
init basket:         finalized
init deposit ledger: finalized
deposit:             15 USDC finalized
```

The deposit path measured:

```text
transaction build: 475.7 ms
sign:                 3.5 ms
Flash submission:   233.7 ms
base confirmation:  452.2 ms
```

The two account initializations consumed about `0.064 SOL`, primarily account
rent rather than transaction fees. Basket delegation required another roughly
`0.00314 SOL` of rent and succeeded after the wallet was topped up.

The live BTC cycle then produced:

```text
OPEN
transaction build:              496.620 ms
local sign:                        1.833 ms
submit start -> basket open:     474.084 ms
full build start -> visible:     972.537 ms

CLOSE
transaction build:              179.752 ms
local sign:                        0.143 ms
submit start -> basket closed:   444.125 ms
full build start -> visible:     624.020 ms
```

The first serialized trace could not reliably order the HTTP response against
the already queued basket event. A later concurrent trace measured the basket
event `4.0 ms` after the open response and `2.7 ms` after the close response.
They are effectively simultaneous. TICK should pre-arm the owner stream, race
both signals, and let the authoritative basket transition drive economic state.

The open used effective collateral of `$9.16`, effective exposure of
`$4,165.90`, and a quoted `$0.83` opening fee. The close quoted another `$0.83`
fee and returned `$8.333302` to the Flash account. No SOL was charged for the ER
open or close.

This is one successful sample, not a latency distribution.

## Production Adapter Verification

The research canary was extracted into `tick_mvp.venues.flash` and exercised
through the same normalized `VenueQuote`, `VenueOpenResult`, and
`VenueCloseResult` contracts used by gTrade.

The latest cache-first BTC canary measured:

```text
OPEN
transaction build:              182.863 ms
local sign:                        1.286 ms
Flash submit HTTP response:      428.880 ms
submit -> raw basket open:       608.560 ms
complete adapter call:           793.301 ms

CLOSE
transaction build:              181.042 ms
local sign:                        0.160 ms
Flash submit HTTP response:      443.284 ms
submit -> raw basket flat:       623.607 ms
complete adapter call:           805.115 ms
```

The close returned `$8.33` from `$10` after two roughly `$0.83` venue fees.
The raw basket was independently checked after the command and contained zero
positions.

An ETH canary before the cache-first optimization measured `1.199 s` open and
`1.163 s` close. About `370 ms` of each path was redundant owner/basket
revalidation. The connector now caches the prepared basket and authoritative
raw position, submits a risk-reducing close immediately, and reconciles the raw
basket after submission.

The identical-transaction hedge was also tested deliberately. TICK withheld
the primary ETH close from Flash, waited `750 ms`, then submitted the exact same
signed bytes and signature. The basket became flat with one economic close and
no overlapping position. Deterministic program failures are rejected without
blind retries; timeouts and transport failures remain ambiguous and are
resolved from the raw basket.

Local router verification with `ENABLED_VENUES=gtrade,flash` produced:

```text
Flash markets:              10
Flash BTC chart feed:       live
90-second chart points:     218 in the sampled request
Flash live opening:         disabled
gTrade default route:       unchanged
```

The quote/API process starts market data without starting the signing wallet.
The durable worker resolves the venue stored on each execution attempt instead
of always using `DEFAULT_VENUE`.

## Synthetic Pool Result

The public builder accepted an XAU quote at `200x`, but two funded transactions
did not create a position. Program preflight returned custom error `6022`, which
maps to `TokenRatioOutOfRange` in Flash's public program source.

The current margin documentation distinguishes `100x` maximum initial leverage
from a `200x` maintenance threshold for the synthetic pool. A funded XAU `100x`
cycle now proves that the documented initial-leverage path executes. TICK still
exposes XAU, XAG, FX, and crude oil as quote/chart markets while repeated
execution, liquidation, and recovery canaries are pending. BTC and ETH remain
the only currently certified Flash execution markets; SOL remains disabled
after two transitions exceeded the bounded observation window.

## TICK Production Boundary

The venue adapter, per-user wallet split, setup sponsorship, custody deposit,
wallet withdrawal, continuous position monitoring, restart recovery, and
fee-aware venue metrics remain wired for research. The terminal monitor checks
normalized owner metrics first, verifies disappearance against the authoritative
raw basket twice, defers to an active close worker, and immediately reconciles
the post-trade basket balance. Any future activation still requires:

```text
funded end-to-end cycles through newly generated TICK user wallets
repeated liquidation and external-close classification canaries
venue-reported terminal reason and cash flow versus wallet reconciliation
owner-stream terminal events to reduce the current 200 ms polling interval
```

TICK does not route user money through the shared canary basket. Flash remains
shadowed from the production user route. Its isolated encrypted Solana wallets
and adapter are retained so the product can be reconsidered without rebuilding
the integration.

A follow-up 12-request builder benchmark isolated the open-build delay:

```text
cold first request: 533.8 ms
warm p50:           185.1 ms
warm minimum:       181.8 ms
```

The original `496.620 ms` open build was a cold-connection sample. The canary
now reuses one API session for status, build, and submission. A second funded
cycle confirmed the improvement:

```text
OPEN
build:                    186.866 ms
sign:                       0.659 ms
submit start -> visible:  432.713 ms
full path:                620.238 ms

CLOSE
build:                    182.529 ms
sign:                       0.143 ms
submit start -> closed:   435.999 ms
full path:                618.671 ms
```

Production should use a process-lifetime async client and keep its Flash
connection warm. The funded cycles prove operability and a warm-path
improvement; they still do not establish p50 or p95.

A third funded cycle raced HTTP submission against WebSocket observation and
measured `625 ms` full open and `713 ms` full close. The close builder rose to
`270 ms` in that sample while submission-to-basket remained `442 ms`. Across
the two warm cycles, full economic visibility remained about `0.62-0.71 s`.

## Repeated Canary Findings

Repeated BTC/ETH/SOL testing changed the readiness assessment:

- Warm BTC and ETH opens repeatedly reached normalized state in about
  `0.61-0.65 s` including build and signing.
- SOL accepted 500x orders but appeared more than `15 s` late twice. SOL is
  disabled for TICK.
- The normalized owner feed transiently reported no positions after an ETH
  close while the raw basket still contained the ETH position. A subsequent
  BTC open created overlapping exposure. Both positions were recovered and
  closed.
- The close builder requires the exact executed `sizeUsd` from the raw basket.
  Using the rounded expected size from the opening quote can leave dust and
  produce a close transaction that never changes basket state.
- Two valid full-close submissions returned an ER signature without changing
  the basket. Freshly rebuilding and resubmitting the close from authoritative
  raw state succeeded.

The canary now treats owner WebSocket messages as fast hints and the decoded
raw basket as execution truth. An open starts only from an empty raw basket,
must produce exactly one raw position, and a close is final only when the raw
position list is empty. A missing state transition triggers an identical signed
transaction hedge and then a fresh close built from current raw state.

The two latest guarded BTC attempts spent `5.663195 USDC`: `3.996483` during a
20-second delayed close and `1.666712` during a flat recovery cycle. This is
why submit acknowledgement cannot drive user-visible terminal state.

After exact raw sizing and raw-basket gating were installed, six complete
BTC/ETH traces and one additional economically confirmed cycle all opened and
closed successfully. The six retained timing traces measured:

```text
authoritative full open median:     828.053 ms
authoritative full close median:    810.656 ms
submit -> raw open median:           624.508 ms
submit -> raw close median:          619.399 ms
state hedges required:                     0
```

The five-cycle alternating BTC/ETH sample cost `8.356916 USDC`. Its fifth
cycle closed economically, but the local command runner was interrupted before
writing the final report. The canary now checkpoints its report after every
execution stage so an interrupted process retains the open signature and raw
state needed for recovery.

This guarded sample supports the latency target. It does not erase the earlier
acknowledged-but-unexecuted closes; the identical-signature hedge and fresh
close recovery still need an intentional failure test before route activation.

## Funded 100x Result

Public `$10 x 100` quotes passed for all ten markets exposed by the current
Flash connector: BTC, ETH, SOL, XAU, XAG, EUR, GBP, crude oil, USDJPY, and
USDCNH. Each quote returned an opening fee of about `$0.19`, effective exposure
of about `$961.38`, and all three capacity checks passed.

A funded BTC cycle then proved that the lower-leverage quote executes through
the production adapter:

```text
BTC 100x open
build:                    229.529 ms
sign:                       1.879 ms
submit -> raw basket:      686.416 ms
full adapter call:         918.110 ms

BTC 100x close
build:                    210.752 ms
sign:                       0.487 ms
submit -> raw basket flat: 674.620 ms
full adapter call:         886.235 ms
```

The position used `$9.80` effective collateral and about `$961.38` exposure.
The quoted fixed round-trip fee was about `$0.38`. Price moved against the
position during the short hold, so the realized return was `$9.40`, a `$0.60`
loss including venue fees and market movement.

A funded XAU cycle proved the synthetic pool at its documented maximum initial
leverage:

```text
XAU 100x open
build:                    211.141 ms
submit -> raw basket:      666.292 ms

XAU 100x close
build:                    214.099 ms
submit -> raw basket flat: 666.066 ms
```

The raw basket contained exactly one XAU position after open and zero positions
after close. The quote charged about `$0.19` per side, and the short sample
returned `$9.47` after fees and adverse price movement. This establishes that
`100x` synthetic execution works. It is not yet enabled in TICK because one
successful cycle is insufficient to certify liquidation, recovery, and market
availability behavior.

## Public Quote Result

Fresh quote-only calls on 2026-08-04 returned the same core economics for BTC,
ETH, and SOL:

```text
requested collateral:       $10.00 USDC
requested leverage:         500x
accepted leverage:          500.00x
opening fee:                $0.83
opening fee rate:           2 bps of notional
effective exposure returned: $4,165.91
capacity checks:            passed
```

Flash documents standard open and close position fees in Degen Mode. The live
close confirmed the symmetric `$0.83 + $0.83` fee model. Rounding and negligible
market movement made the observed account result `-$1.666698`.

## Withdrawal Evidence

TICK withdrew `13.33 USDC` after the close. The request finalized on Solana and
Flash's automatic `WithdrawalSettle` callback transferred the funds to the
owner wallet four seconds later:

```text
wallet USDC before withdrawal: 16.290278
wallet USDC after withdrawal:  29.620278
withdrawn:                     13.330000
pending basket credit after:    0.000000
```

Flash requires a second client-owned signer for withdrawal escrow rent. The
OpenAPI example's `2,040,000` lamport top-up was insufficient for the live path;
onchain logs showed all allocations required slightly over `0.01007112 SOL`.
Provisioning the sponsor to `0.011 SOL` succeeded. Most of that SOL remains in
the sponsor account and can be reused.

The public submit endpoint also produced false-negative transaction simulations
for delegation and withdrawal. The canary had to use `skipPreflight`, persist
the deterministic signature, submit once, and inspect the resulting onchain
status. This behavior must be covered by the connector's recovery logic.

## Execution Model

The current public API describes this lifecycle:

```text
base-layer account, basket, ledger, and deposit setup
-> optional owner-authorized ER session key
-> quote and unsigned transaction build
-> client signs
-> Flash submit endpoint routes to ER or base RPC
-> owner basket WebSocket publishes account update
-> oracle-tick metrics update estimated position state
-> close changes basket state
-> state settles back to the Solana base layer
```

The submit endpoint returns a signature without waiting for confirmation. TICK
must therefore treat the owner basket update as the fast economic-state signal
and retain base-layer settlement and wallet balance as reconciliation signals.

The API documents a 100 ms minimum owner metrics interval. The basket stream
sends a full payload on connection and on basket account changes, while metric
updates follow oracle ticks.

## Session Keys

Flash exposes a session flow for ER transactions:

- TICK generates a session signer.
- The owner and session key both sign session creation.
- The session has a token account and optional expiry.
- The session signer can sign later ER transactions.
- The API says ER fees are subsidized, so session SOL top-up can remain off.

The owner-signed happy path is proven. Reliability certification is incomplete.
A scoped session-key comparison comes after raw-basket close recovery passes a
controlled BTC/ETH sample.

## Risk Controls

The official Degen page currently says:

- market orders only;
- no limit orders;
- no TP/SL;
- BTC, ETH, and SOL only;
- rapid liquidation at minimal adverse movement.

The V2 API DTO also exposes limit, TP, and SL fields. That is a documentation
conflict, not evidence that Degen TP/SL works. TICK should submit no trigger
orders until a funded simulation or canary proves their exact Degen behavior.

## Connector Boundary

The normalized connector should expose venue-neutral primitives:

```text
quote_open
prepare_account
deposit_collateral
build_open
submit_signed_transaction
observe_open
quote_close
build_close
observe_close
reconcile_settlement
withdraw_collateral
create_session
revoke_session
```

Flash-specific basket, custody, ER, and session-token concepts stay inside the
adapter.

## Remaining Canary Gate

Do not activate Flash for users until TICK has measured:

```text
execution-price drift
liquidation event behavior
WebSocket disconnect recovery
backend restart recovery
session expiry and revocation
20-cycle p50 and p95 latency/cost distribution
zero acknowledged-but-unexecuted commands after bounded recovery
zero overlap after transient normalized owner state
```

The full Solana comparison and canary timeline are in
[`solana-perps-rescreen-2026-08-04.md`](solana-perps-rescreen-2026-08-04.md).

## Primary Sources

- [Degen Mode](https://docs.flash.trade/flash-trade/getting-started/degen-mode)
- [Flash public API](https://flashapi.trade/docs/)
- [Flash OpenAPI](https://flashapi.trade/api-docs/openapi.json)
- [MagicBlock Ephemeral Rollup FAQ](https://docs.magicblock.gg/pages/ephemeral-rollups-ers/introduction/faq)
- [MagicBlock router and account delegation](https://docs.magicblock.gg/pages/get-started/how-integrate-your-program/quickstart)
