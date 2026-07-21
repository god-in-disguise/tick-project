# TICK Chart And Arbitrum Latency Notes

## Chart Verdict

The TICK chart must feel alive without inventing market movement.

Do not add fake vertical heartbeat movement when price is unchanged. Animate the
current-price marker, glow, time tail, or feed state, but the price line itself
must only move when a real venue observation changes price.

The current chart issue is that it mixes:

- real market observations
- synthetic interpolation points
- position/risk overlays

These need to stay separate.

## Current Problems

- The frontend keeps `240` points, but one real tick can become `1-4` visual
  points. That makes visible time depend on volatility.
- `/api/chart?minutes=20` can return only the recent live tape window once live
  points exist, so the API contract is misleading.
- `/api/markets` history and `/api/chart` history are merged into the same
  line. This can create jumps and duplicate source meaning.
- Entry and liquidation are included in the y-domain, so a 500x liquidation
  line can flatten actual tape movement.
- Neighbor smoothing changes the source values and can suppress local extrema.
- `candles` is empty for gTrade. Current bars are price observations, not real
  trade candles or volume.
- Liquidation/external-close state is caught, but UI visibility depends on
  polling/finalization timing.

## Target Chart Shape

- Main viewport: `60-90s` fixed wall-clock tape.
- Store exactly one canonical observation per real venue tick.
- Animate between observations only in the renderer.
- Keep source values untouched for domain, labels, PnL, markers, and risk.
- Trim history by timestamp, not by synthetic point count.
- Use y-domain from visible market prices only.
- Expand domain immediately when price breaks range.
- Contract domain slowly and use a current-price deadband.
- Draw entry/liquidation only when inside the viewport.
- If offscreen, show an edge indicator with percentage distance.
- During unchanged prices, extend a truthful horizontal held-price tail and
  pulse the current-price marker.

## Local MVP Patch Applied

The current local MVP now carries timestamped chart points through the Expo
model and renders the main chart against a fixed `90s` wall-clock window. The
frontend no longer appends synthetic interpolation points into chart history,
and it no longer merges `/api/markets`, `/api/chart`, and live ticks as equal
history sources.

The current renderer still keeps a simple line chart. It preserves source
prices, draws a flat held-price tail when no new price arrives, and keeps entry
and liquidation as overlays instead of forcing them into the y-domain.

Remaining chart work:

- server-side `1s` OHLC price bars for true longer history
- min/max-preserving server downsampling instead of simple thinning
- render-only curve smoothing that never overshoots source extrema
- push-based mobile execution events for close/liquidation markers

## Backend Contract Direction

`/api/chart` should expose:

- requested window
- actual coverage
- server time
- partial coverage flag
- last sequence
- feed status
- last market tick age
- last price change age
- canonical timestamped points

For longer history, keep derived OHLC price bars:

- raw ticks: last `3-5m`
- `1s` OHLC price bars: last `20-60m`
- optional `5s` OHLC price bars for longer views

These are derived price bars, not trade candles. Do not expose volume unless a
venue source provides real trade-size data.

## Execution Events

Price tape and economic state are separate clocks.

On authoritative open, close, external close, or liquidation:

- push the event to the app
- stop live exposure immediately for close/liquidation
- insert a marker at the venue execution time and price
- show `Closed` or `Liquidated` while final accounting reconciles

Polling should remain recovery, not the primary UX path.

## Arbitrum Latency Notes

The current gTrade path uses one `ARB_RPC_URL` for Web3 reads and writes. It
does not yet have a dedicated Arbitrum direct-sequencer write path.

Useful next benchmark:

- write RPC: `https://arb1-sequencer.arbitrum.io/rpc`
- read RPC: existing provider
- event RPC/WSS: existing provider or local Nitro later

Rename `sendRawTransactionMs` to `broadcastToSoftConfirmationMs` when using the
direct sequencer, because a successful direct-sequencer response means L2 soft
sequencing/execution, not just mempool acceptance.

Measure:

- tx hash persisted
- broadcast start
- broadcast response
- receipt seen
- receipt block
- receipt `timeboosted`
- callback tx hash
- callback receipt `timeboosted`
- callback block delta

Direct sequencer should reduce the initiation leg, but gTrade still has a
second oracle/callback transaction. Optimizing TICK's initiation cannot remove
the whole callback interval.

Implementation order:

1. Add direct-sequencer write mode.
2. Keep receipts and callback waiting parallel.
3. Record `timeboosted` for initiation and callback txs.
4. Add delayed identical raw-tx fallback.
5. Ask Gains whether callback transactions use direct sequencer or Timeboost.
