# Venue Checks

These probes are research and canary tools, not production connectors.

## Flash Trade V2

The guarded production-adapter canary uses the ignored Solana canary secret,
prepares its existing basket, requests a normalized quote, opens, closes, and
requires the raw basket to return flat:

```bash
builds/tick-mvp/backend/.venv/bin/python \
  research/experiments/venue-checks/flash_adapter_canary.py \
  --execute \
  --market BTC \
  --side short \
  --amount 10 \
  --leverage 500 \
  --hold-seconds 0.2 \
  --json-report research/experiments/venue-checks/reports/flash/adapter-btc-live.json
```

Only BTC and ETH are execution-certified. Flash submission acknowledgement is
not execution truth; the canary and production adapter require the intended raw
basket transition. A timeout may trigger one delayed resend of the identical
signed transaction. A deterministic program error is not retried.

For local quote and chart evaluation, set:

```text
ENABLED_VENUES=gtrade,flash
FLASH_REAL_EXECUTION_ENABLED=false
```

This does not make the shared research basket available to PWA users.

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

## Avantis ZFP

Install the pinned official SDK in the research-only virtual environment, then
run the read-only Base probe:

```bash
BASE_RPC_URL="<base-rpc>" \
  venue-checks/.venv/bin/python venue-checks/avantis_zfp_probe.py
```

The probe reads live pair eligibility, leverage limits, minimum notional,
spread, sample price impact, execution fee, balances, and allowance. It never
signs or broadcasts.

The guarded live canary is fixed to BTC/USD and `$10` margin. Leverage is
restricted to `75x`, `100x`, `250x`, or `500x`. It requires both live-risk
flags, approves exactly `$10` when needed, opens, correlates the callback order,
holds briefly, closes the exact callback trade, and verifies that no open or
pending trade remains:

```bash
BASE_RPC_URL="<base-rpc>" \
  venue-checks/.venv/bin/python venue-checks/avantis_zfp_canary.py \
  --execute \
  --i-understand-live-risk \
  --side short \
  --leverage 75 \
  --hold-seconds 1 \
  --json-report venue-checks/reports/avantis/latest_live.json
```

`WALLET_PK` must point to the dedicated canary wallet. RPC URLs and private keys
are not written to the report. The first clean live cycle returned the wallet
to a flat state with a `-$0.207268` USDC result. The current canary intentionally
uses HTTP callback polling for measurement; a production connector should
pre-arm a persistent Base WSS callback subscription.

The same canary supports the high-leverage comparison directly:

```bash
BASE_RPC_URL="<base-rpc>" \
  venue-checks/.venv/bin/python venue-checks/avantis_zfp_canary.py \
  --execute \
  --i-understand-live-risk \
  --side short \
  --leverage 500 \
  --hold-seconds 1 \
  --json-report venue-checks/reports/avantis/latest_500x_live.json
```

The clean 500x cycle returned `$8.961121` from `$10`, consumed
`0.000017815145207003558 ETH`, and finished with no open or pending trade. The
canary refreshes the pending wallet nonce immediately before every signature;
this prevents an SDK transaction template built after an approval from reusing
the approval nonce.

For the latency path, use the optimized canary. It prewarms the official SDK,
Pyth Lazer feed, execution fee, fee envelope, nonce, and gas estimate before the
gesture. The hot path locally encodes and signs the prepared transaction, sends
it over a reused HTTP connection, and races Base Flashblocks `pendingLogs`
against the sealed callback:

```bash
BASE_RPC_URL="<base-rpc>" \
BASE_WSS_URL="<base-wss>" \
  venue-checks/.venv/bin/python venue-checks/avantis_zfp_optimized_canary.py \
  --execute \
  --i-understand-live-risk \
  --side short \
  --leverage 500 \
  --hold-seconds 1 \
  --json-report venue-checks/reports/avantis/optimized_500x.json
```

`pendingLogs` is treated as preconfirmed visibility, not final settlement. The
canary waits separately for the sealed callback and verifies the final flat
state. It also decodes `PriceReceived`, `MarketExecuted`, and `FeesCharged` so
venue execution adjustment, market movement, and closing fee are not conflated.

Build a comparable latency and cost matrix from completed reports with:

```bash
venue-checks/.venv/bin/python venue-checks/avantis_zfp_matrix.py \
  venue-checks/reports/avantis/optimized_75x_flash_1.json \
  venue-checks/reports/avantis/optimized_100x_flash_1.json \
  venue-checks/reports/avantis/optimized_250x_flash_1.json \
  venue-checks/reports/avantis/optimized_500x_flash_2.json \
  --json-report venue-checks/reports/avantis/optimized_matrix.json \
  --markdown-report venue-checks/reports/avantis/optimized_matrix.md
```
