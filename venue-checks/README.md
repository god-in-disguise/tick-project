# Venue Checks

These probes are research and canary tools, not production connectors.

## GMTrade

## Aster

Public market-data smoke test:

```bash
venue-checks/.venv/bin/python venue-checks/aster_public_probe.py --check-fapi3
```

Use `https://fapi.asterdex.com` for V3. From this machine, `https://fapi3.asterdex.com` returned `403 Forbidden` even though the docs' Python example still references it. Signed trading still requires an approved Aster API wallet/agent.

If the probe is run through Codex sandboxing, Python DNS may fail while curl still works. That is a local sandbox/network-permission issue, not an Aster API result.

Wallet-native Aster 1001x direct-contract probe:

```bash
venue-checks/.venv/bin/python venue-checks/aster_1001x_probe.py --simulate-open
```

This probes the documented BNB Chain 1001x contract, reads pair/token/trading config, reads the local EVM wallet balance and allowance when `WALLET_PK` is set, and dry-runs a `$20` 100x BTC market-open by gas estimation. It does not sign or broadcast.

The GMTrade order probe uses the official Rust SDK/CLI to discover protocol accounts, then signs the resulting v0 message in Python memory and calls Solana `simulateTransaction`. It has no broadcast path.

```bash
venue-checks/.venv/bin/python venue-checks/gmtrade_order_probe.py \
  --collateral 20 \
  --leverage 100 \
  --side long \
  --acceptable-bps 30 \
  --stop-loss-bps 35
```

Required environment variables:

```text
GMTRADE_SOLANA_PRIVATE_KEY
GMTRADE_SOLANA_RPC_URL
GMTRADE_CLI_PATH
```

Use a test-only wallet. The first transaction creates several rent-bearing accounts, so keep at least `0.10 SOL` available in addition to the USDC collateral during canary work.

The probe fetches GMTrade's current keeper-oracle range, rejects closed or stale markets, and puts the side-aware acceptable price into the simulated order. Its reported fallback stop is informational: GMTrade creates that stop as a second order only after the position exists.

The user-triggered live canary is one command:

```bash
venue-checks/.venv/bin/python venue-checks/gmtrade_user_canary.py --execute
```

It is locked to $20 collateral at 100x. It runs a fresh signed simulation first, prints the exact terms, and requires the user to type `RUN LIVE GMTRADE CANARY` before broadcasting. It then opens, waits for the position, creates a separate stop, holds for three seconds, closes, attempts to cancel the stop, and prints the final positions/orders state.

The default submit path is now `direct-rpc`: the official CLI is used only to build the serialized GMTrade transaction, then Python refreshes the blockhash, signs, submits through JSON-RPC, and records build/sign/send/confirmation timings separately. This is the better benchmark path for TICK because it separates local plumbing latency from venue/keeper latency.

The canary also treats quote freshness as a hard execution condition. It fetches a live GMTrade keeper quote immediately before building the order, then fetches again after the transaction is built and before submit. If the quote is too old or has drifted beyond the configured threshold, it fails closed instead of broadcasting. This matches the TICK product rule: the UI can feel instant, but the backend must only execute against the freshest available quote.

```bash
venue-checks/.venv/bin/python venue-checks/gmtrade_user_canary.py \
  --execute \
  --i-understand-live-risk \
  --submit-mode direct-rpc \
  --priority-lamports 25000 \
  --max-price-age 10 \
  --max-quote-age-at-submit 5 \
  --max-quote-drift-bps 10 \
  --json-report venue-checks/reports/gmtrade/latest_live.json
```

The older official CLI submit path is still available:

```bash
venue-checks/.venv/bin/python venue-checks/gmtrade_user_canary.py \
  --execute \
  --submit-mode cli
```

For a small live benchmark batch, use the repeat runner. This is capped at five loops and still requires an explicit live-risk confirmation:

```bash
venue-checks/.venv/bin/python venue-checks/gmtrade_repeat_canary.py \
  --execute \
  --i-understand-live-risk \
  --iterations 3 \
  --hold-seconds 3 \
  --side-mode alternate
```

The repeat runner is non-interactive when `--execute --i-understand-live-risk` are present. It writes individual reports and a `summary.json` under `venue-checks/reports/gmtrade/<timestamp>/`.

## gTrade / Gains

Read-only Arbitrum probe:

```bash
venue-checks/.venv/bin/python venue-checks/gtrade_public_probe.py --stream-seconds 3 --wallet
```

This fetches the live Gains trading variables, parses leverage and minimum notional by pair, samples the public price websocket, and optionally reads the local EVM wallet's Arbitrum balances/allowances from `ARB_RPC_URL`. It does not sign or broadcast.

Dry-estimate a current open without broadcasting:

```bash
venue-checks/.venv/bin/python venue-checks/gtrade_public_probe.py \
  --stream-seconds 0 \
  --wallet \
  --dry-open BTCDEGEN/USD \
  --dry-open-margin 10 \
  --dry-open-side long
```

If allowance is zero, the dry estimate should revert with the ERC-20 allowance error. That means the calldata shape is valid and the next live step is an approval transaction before an open/close canary.
