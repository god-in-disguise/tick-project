# Ostium

Snapshot: 2026-07-13.

Status: live tested by TICK with real orders on Arbitrum.

## Bottom Line

Ostium proved that TICK can open, display, close, and reconcile a real leveraged position. Its cross-asset coverage is valuable. Its on-chain request plus oracle-callback lifecycle is not ideal for the primary 30-60 second crypto loop because both visible latency and effective cost are materially higher than the best CLOB candidates.

Ostium should not be discarded. Its likely TICK role is cross-asset execution for stocks, indices, commodities, and FX, with crypto routed elsewhere when a faster and cheaper venue is available.

## How It Works

- Execution is on Arbitrum.
- The first transaction requests an order.
- An oracle/automation callback confirms the execution and creates or closes the position.
- The position must remain `opening` or `closing` until callback state is confirmed.
- Delegated/gasless mode can remove a wallet prompt, but it does not remove the two-stage protocol lifecycle.

Arbitrum block time is not the entire order time. Paying more gas or using a priority lane can improve inclusion of the initial transaction, but it cannot eliminate the oracle callback.

## TICK Measurements

July 2026 local canary observations:

```text
open request -> confirmed position: roughly 3.15 s
close request -> position gone:     roughly 3.35 s
oracle callback latency p50:        roughly 1 s
oracle callback latency p95:        roughly 2 s
```

These are end-to-end observations from our path, not protocol guarantees. The local connector is in `tick-mvp-local/backend/connectors/`, and independent probes are in `venue-checks/`.

## Cost

Current Ostium documentation states:

```text
opening fee:    3-10 bps of notional, pair-specific
oracle fee:     $0.10 per request
early close:    0-40 bps of notional when a profitable position closes within 15 s,
                capped at realized profit
rollover:       continuously accrued, pair-specific
```

The oracle fee is refunded on a successful full close, but not for partial closes or failed requests. Local tests also showed that the amount actively supporting a position can differ from the ticket shown before execution. TICK must derive net PnL from fills and venue fee/reserve events, then reconcile the wallet delta; gross mark movement is not profit.

The connector must consume live pair configuration. Do not hardcode one crypto fee across all Ostium markets.

## Strengths

- Already integrated and live tested.
- Isolated positions fit the TICK mental model.
- Broad 24/7 and market-hours-aware cross-asset catalog.
- High pair-specific leverage, up to 200x on supported markets.
- On-chain state provides a clear final source for reconciliation.
- Python connector code is already modular enough to serve as the adapter contract reference.

## Weaknesses For The Main Crypto Loop

- Multi-second open and close lifecycle.
- Oracle callback remains even after wallet friction is removed.
- Short holds can face a meaningful fee hurdle and an early-close fee.
- Price movement during the callback changes the realized entry/exit.
- A fast animation can improve perceived responsiveness but cannot pretend the position filled before confirmation.

## Current Role

```text
crypto discovery and primary short-hold route: not preferred
cross-asset expansion route:                  strong candidate
connector/reconciliation benchmark:           keep
fallback when another venue is degraded:      evaluate per market and cost
```

## Remaining Work

- Store exact venue fill, fee, reserve, and rollover events per position.
- Reconcile every historical canary balance delta.
- Measure delegated/gasless mode end to end.
- Verify live fee and leverage configuration per market.
- Test profitable closes inside and outside the 15-second early-close window.
- Keep the app honest while `opening` and `closing` are pending.

## Primary Sources

- [How Ostium works](https://docs.ostium.com/protocol/how-ostium-works)
- [Fees](https://docs.ostium.com/traders/reference/fees)
- [SDK overview](https://docs.ostium.com/developer/sdk/overview)
- [Client modes](https://docs.ostium.com/developer/client-modes/overview)
- [Delegated and gasless mode](https://docs.ostium.com/developer/client-modes/delegated-and-gasless)
