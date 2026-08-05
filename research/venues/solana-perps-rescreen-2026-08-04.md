# Solana Perpetual Venue Rescreen

Snapshot: 2026-08-04.

## Question

Can a Solana venue improve TICK's `$10` high-leverage loop relative to gTrade by
combining:

- 500x leverage;
- lower all-in fee drag;
- materially faster position visibility;
- programmatic open, close, and lifecycle state;
- and a connector that does not depend on browser automation?

## Verdict

Flash Trade V2 is the strongest newly live-tested Solana route.

It is the only newly screened Solana route that currently combines documented
500x leverage, successful public `$10 x 500` quotes, unsigned transaction
building, a signed transaction submission endpoint, session keys, and an owner
WebSocket. Its trading state runs on a MagicBlock Ephemeral Rollup, which is a
credible route to faster execution. TICK completed a funded BTC open, close,
and withdrawal. Basket visibility was `474 ms` after open submission and
`444 ms` after close submission; the nearly flat `$10 x 500` round trip lost
`$1.666698` at the venue.

GMTrade remains cheaper on headline basis, but its public keeper leg measured
about 4-5 seconds after the order transaction. The other active Solana venues
screened here currently cap leverage between 40x and 250x.

## Evidence Labels

- **Documented:** current official documentation or public API contract.
- **Public measured:** TICK called a public endpoint without signing or funds.
- **Live tested:** TICK broadcast a funded order and reconciled the result.
- **Estimated:** arithmetic from documented or public measured inputs, pending a
  funded cycle.

## Working Matrix

| Venue | Evidence | Current useful leverage | Baseline cost | Execution and integration | TICK view |
| --- | --- | ---: | --- | --- | --- |
| [Flash Trade](flash.md) | Live tested | 500x BTC/ETH/SOL | Live `$10 x 500` BTC cycle: `$0.83` open, `$0.83` close, realized account result `-$1.666698` | MagicBlock ER, public transaction builder, signed submission, session keys, owner WS | Open visible in 474 ms from submit; close visible in 444 ms; wallet withdrawal reconciled |
| [GMTrade](gmtrade.md) | Live tested | BTC 500x, ETH about 294x, SOL 250x | 1.0-1.2 bps per crypto fill | User request transaction followed by keeper/oracle execution | Cheap, but public keeper path is too slow for the core loop |
| Jupiter Perps | Documented | Up to 250x | 6 bps per side plus impact, borrow, and network costs | Mature Solana product | Too expensive and not 500x |
| BULK | Documented | Up to 100x | Tier-one taker 3.5 bps per fill | CLOB, agent keys, HTTP/WS, conditional orders | Interesting pro route, not a 500x replacement |
| Bullet | Documented | Up to 100x | Tier-dependent | Solana network extension and CLOB | Fast architecture, insufficient leverage |
| Adrena | Documented | Up to 100x | Pool and dynamic execution costs require canary | Peer-to-pool, open source keepers | Insufficient leverage |
| Phoenix | Documented + public measured | BTC 40x, ETH/SOL 25x in current public config | Taker 3.5 bps | Rise SDK, HTTP/WS, triggers, private-beta activation | Strong pro/cross-asset research venue, not the degen loop |
| Pacifica | Public measured | BTC/ETH 50x, SOL 20x | Taker 4 bps per fill | Signed REST/WS, agent keys, intentional 200 ms taker delay | Fast moderate-leverage fallback |
| Velocity / former Drift surface | Documented | Moderate, market-specific | Tiered | Mature SDK and SWIFT off-chain intent flow | Useful pro infrastructure, not a 500x route |
| JTX | Documented | Perpetuals not live | N/A | Current product is spot; perps remain roadmap | Monitor only |
| Imperial | Public product review | Route-dependent | Route-dependent | Aggregates other Solana venues | Product comparator, not an independent execution rail |

Costs above are not all-in TICK costs. Spread, price impact, borrow or funding,
execution fees, account setup, and liquidation behavior still apply.

## Flash Public Measurement

TICK requested unsigned quote-only market opens from the public Flash API on
2026-08-04. The request used USDC collateral, `$10` input, 500x leverage, and a
long market order.

| Asset | Accepted leverage | Entry fee | Effective exposure returned | Entry | Liquidation | Capacity checks |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| BTC | 500.00x | `$0.83` | `$4,165.91` | `63,570.7681` | `63,507.1973` | Passed |
| ETH | 500.00x | `$0.83` | `$4,165.91` | `1,860.2448` | `1,858.3846` | Passed |
| SOL | 500.00x | `$0.83` | `$4,165.91` | `73.4895` | `73.4161` | Passed |

The response reported `openPositionFeePercent = 0.02000`, meaning 2 bps of
notional, and a separate `marginFeePercentage` value. Flash documentation says
standard open and close position fees still apply in Degen Mode. If the close
uses the same 2 bps rate against the effective exposure, the simplified
round-trip estimate is:

```text
opening fee:          about $0.83
estimated close fee: about $0.83
estimated round trip: about $1.66
```

The live BTC cycle confirmed a `$0.83` close fee and returned `$8.333302` from
the `$10` trade debit. Its `-$1.666698` account result was about `$0.83` better
than the representative gTrade `$2.50` round-trip cost. After withdrawing
`$13.33`, the wallet balance rose from `$16.290278` to `$29.620278`; the basket's
pending credit cleared to zero.

## Flash Live Measurement

TICK pre-armed the owner WebSocket, built and signed each transaction locally,
submitted through Flash's public router, and waited for authoritative basket
state.

```text
OPEN
build                              496.620 ms
sign                                 1.833 ms
submission start -> basket open    474.084 ms
full build start -> visible        972.537 ms

CLOSE
build                              179.752 ms
sign                                 0.143 ms
submission start -> basket closed  444.125 ms
full build start -> visible        624.020 ms
```

The first serialized trace could not reliably order the queued basket event
against the HTTP response. A later concurrent trace measured the basket event
`4.0 ms` after the open response and `2.7 ms` after the close response. The open
and close consumed no wallet SOL because they ran through the ER route.

A 12-request follow-up measured the public builder at `533.8 ms` cold and
`185.1 ms` warm p50. The first live open accidentally used a fresh HTTP session.
A second funded cycle reused the connection and measured `620.238 ms` full open
and `618.671 ms` full close, including build and signing. Submission-to-basket
visibility was `432.713 ms` open and `435.999 ms` close.

A third concurrent-observation cycle measured `625 ms` full open and `713 ms`
full close. Its close builder rose to `270 ms`, while the ER submission-to-basket
portion remained `442 ms`.

Repeated canaries then exposed two blockers hidden by the initial fast samples.
SOL positions appeared more than `15 s` after acknowledged submissions twice,
so SOL is disabled. The normalized owner feed also transiently reported an
empty position set while the decoded raw basket still contained an ETH
position, allowing an overlapping BTC open in the test harness. Finally, the
ER submit endpoint acknowledged BTC close transactions that did not change the
basket. Fresh close transactions built from the exact raw `sizeUsd` recovered
the positions.

The connector must therefore use the owner stream only as a fast hint. The
decoded raw basket is authoritative for the one-position invariant and close
finality. Exact raw position size, idempotent signed resubmission, and bounded
fresh-close recovery are route requirements.

A guarded retest then completed six fully traced BTC/ETH cycles plus one
additional economically confirmed cycle. The six traces measured `828 ms`
median full open and `811 ms` median full close. The five-cycle alternating
sample cost `8.356916 USDC`; no state hedge was required. These results restore
confidence in the fast path while leaving deliberate hedge, restart, and
recovery testing as activation gates.

The base-layer withdrawal required a separate client-owned rent sponsor. The
request and automatic settlement callback landed four seconds apart. The live
escrow allocations required slightly more than `0.01007112 SOL`; the OpenAPI's
example top-up was too small. Delegation and withdrawal also showed
false-negative preflight behavior, so deterministic signatures and post-submit
recovery are mandatory.

## Why Flash Could Be Faster

Flash's public OpenAPI describes V2 as basket-centric trading on a MagicBlock
Ephemeral Rollup. It exposes:

- unsigned builders for open, close, reverse, collateral, setup, and withdrawal;
- a signed transaction submission endpoint that routes Flash instructions to
  the ER or Solana base layer;
- owner and session-key signing;
- owner basket WebSocket updates when the basket account changes;
- position metrics on oracle ticks, with a documented 100 ms minimum update
  interval;
- and a one-shot owner snapshot for bootstrap and recovery.

MagicBlock documents a 50 ms ER slot time and sub-10 ms execution capability.
Those are infrastructure claims, not a measured Flash fill SLO. TICK must time
the full path from request through basket update and settlement.

## Important Flash Uncertainties

1. Degen documentation says TP/SL is unavailable, while the current V2 open DTO
   exposes optional TP and SL fields. Treat Degen TP/SL as unsupported until a
   funded canary proves otherwise.
2. The submission response does not independently prove economic execution;
   the owner basket transition does.
3. Direct owner setup, deposit, open, close, and withdrawal now work. Session
   signing remains untested.
4. The public config contains delay and leverage fields whose scaling and
   runtime meaning are not fully documented. Do not derive UX promises from
   them.
5. Only BTC, ETH, and SOL are accepted as verified 500x markets. Flash lists
   many other assets, but their quote behavior is not clean enough to classify
   as 500x Degen routes.
6. BTC and ETH prove a sub-second fast path, not a reliable SLO. SOL currently
   fails TICK's latency requirement.

## Next Canary Phase

The direct-owner phase is complete. Repeat through a scoped Flash session key,
then run a controlled sample set. Verify expiry, revocation, API interruption,
WebSocket reconnect, backend restart, liquidation, and withdrawal recovery.

### Required timings

```text
quote_request_to_response_ms
build_request_to_response_ms
sign_ms
submit_request_to_response_ms
submit_to_owner_basket_open_ms
submit_to_position_metrics_ms
open_to_base_settlement_ms
close_submit_to_response_ms
close_submit_to_owner_basket_closed_ms
close_to_base_settlement_ms
withdraw_to_wallet_ms
```

### Acceptance criteria

```text
500x displayed terms equal submitted and executed terms
one open and one close economic action
no state inferred from submit acknowledgement alone
position visible p50 target below 1 second for later sample set
close visible p50 target below 1 second for later sample set
realized round-trip venue cost below gTrade on the same ticket
wallet delta reconciles to venue cash flows
restart and WebSocket reconnect recover the exact position
direct signer and session signer produce the same economic result
```

One sample can prove operability. It cannot establish p50 or p95. After the
first successful cycle, run at least 20 low-value cycles before making a route
decision.

## Routing Decision

Current order for the high-leverage mobile loop:

1. gTrade remains the active route while its execution core is hardened.
2. Flash advances to repeated canary and connector work.
3. Avantis remains the best measured lower-fee losing-trade comparison, with a
   slower callback path.
4. Aark remains attractive if partner authentication is enabled.
5. GMTrade requires a faster keeper or partner lane before reconsideration.

Flash should become a live TICK route only after repeated cycles prove the
single-sample latency, session security, liquidation handling, and restart
recovery.

## Primary Sources

- [Flash Degen Mode](https://docs.flash.trade/flash-trade/getting-started/degen-mode)
- [Flash public API](https://flashapi.trade/docs/)
- [Flash OpenAPI](https://flashapi.trade/api-docs/openapi.json)
- [MagicBlock Ephemeral Rollup FAQ](https://docs.magicblock.gg/pages/ephemeral-rollups-ers/introduction/faq)
- [MagicBlock integration quickstart](https://docs.magicblock.gg/pages/get-started/how-integrate-your-program/quickstart)
- [Jupiter product index](https://docs.jup.ag/)
- [BULK contract specifications](https://docs.bulk.trade/bulk-exchange/Contract-Specifications)
- [BULK fees](https://docs.bulk.trade/bulk-exchange/fees)
- [Bullet contract specifications](https://docs.bullet.xyz/bulletx-exchange/contract-specifications)
- [Adrena overview](https://docs.adrena.trade/about-adrena/what-is-adrena)
- [Phoenix Rise SDK](https://docs.phoenix.trade/sdk/rise)
- [Velocity SWIFT API](https://docs.velocity.exchange/developers/market-makers/swift-api)
