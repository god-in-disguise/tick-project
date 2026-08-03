# Variational Omni

Snapshot: 2026-08-03.

Evidence: documented; not currently integrable through a public trading API.

## Bottom Line

Variational Omni is a strong future route and a current watchlist item. Its
RFQ model, zero explicit trading fee, gasless Arbitrum UX, broad cross-asset
catalog, and up to 50x leverage fit TICK conceptually. The official developer
documentation says the trading API is still under development and unavailable
to users, so it cannot enter the canary queue yet.

## Current Fit

- More than 500 documented markets across crypto, stocks, commodities, and
  other instruments.
- Up to 50x leverage.
- No explicit trading fee; liquidity providers earn through quoted spread.
- Gasless trading with Arbitrum USDC account balances.
- Native TP/SL.
- RFQ quotes account for size and risk before becoming firm.

## Main Risks

- No public trading API today.
- RFQ completion is described in seconds, which may be too slow for TICK's
  shortest loop until measured.
- Quote spread can vary by size, market, and maker risk.
- Account collateral is held in the venue system rather than remaining as a
  simple wallet balance.

## Next Step

Contact Variational for API/partner access. Do not build a browser-automation
or private-endpoint connector. A proper route requires documented signing,
idempotency, order lifecycle events, account history, and withdrawal behavior.

## Primary Sources

- [Omni overview](https://docs.variational.io/omni/about-omni)
- [Omni fees](https://docs.variational.io/omni/trading/fees)
- [RFQ trading](https://docs.variational.io/variational-protocol/key-concepts/trading-via-rfq)
- [Quoted prices](https://docs.variational.io/omni/trading/quoted-index-and-mark-prices)
- [Developer API status](https://docs.variational.io/for-developers/api)

