# TICK One-Wallet Canary

Local Python backend for testing the complete TICK loop against real gTrade/Gains execution on Arbitrum.

It is intentionally limited to:

- one hardcoded test wallet
- one concurrent isolated position
- one live venue connector, currently gTrade/Gains
- a `$20` default ticket
- leverage presets subject to the selected market and venue cap
- nine crypto feed markets by default

## Required Environment

The backend reads the repository root `.env`:

```text
WALLET_PK=...
ARB_RPC_URL=...
```

The private key must derive the hardcoded canary address:

```text
0xeD1fa479504Ec60DB8a314BfF2DbbD1bB481Db78
```

Optional local settings:

```text
TICK_LOCAL_API_TOKEN=tick-local-one-wallet
TICK_FEED_PAIRS=BTC-USD,ETH-USD,SOL-USD,HYPE-USD,BNB-USD,XRP-USD,LINK-USD,ADA-USD,TRX-USD
TICK_DEFAULT_TICKET_USD=20
TICK_DEFAULT_LEVERAGE=500
```

Every venue-open market is executable in the canary. Scanner state changes ranking and labels, not order eligibility.

## Run

```bash
builds/local-mvp/tick-mvp-local/.venv/bin/uvicorn backend.app:app \
  --app-dir builds/local-mvp/tick-mvp-local \
  --host 0.0.0.0 \
  --port 8787
```

Read-only health check:

```bash
curl http://127.0.0.1:8787/api/health
```

## Real Loop

```text
price sampler -> volatility ranking -> long/short preflights
-> one opening swipe -> opening -> open -> live estimated net PnL
-> same-direction swipe -> closing -> closed -> reconciled wallet result
```

Opening and closing run in a background execution worker. The API returns the durable execution state instead of keeping the phone request open while gTrade indexes and executes the order.

State is stored in:

```text
builds/local-mvp/tick-mvp-local/.local/tick.sqlite3
```

The database stores quotes, idempotency keys, execution transitions, transaction hashes, errors, balance snapshots, and completed local history. It contains no private key.

## Tests

Tests use a fake venue connector and never touch the wallet:

```bash
cd builds/local-mvp/tick-mvp-local
.venv/bin/python -m unittest discover -s tests -v
```

No test command submits a live transaction. Live opening and closing happen only through the protected API used by the phone app.

## Safety

All POST endpoints require `X-Tick-Token`. The default is only suitable for a trusted local network. Keep this backend local; it directly controls the canary wallet and is not a public deployment shape.
