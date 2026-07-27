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

July 21 hardening:

- local chart density increased from `240` to roughly `520` points so a `90s`
  high-frequency tape does not constantly downsample and reshape itself
- current-price animation remains render-only
- the y-domain now expands immediately for real moves but contracts slowly, so
  render frames do not make old peaks appear to fall or rewrite chart scale
- result cards stay visible long enough to read final/settling state
- liquidation display is explicit; the UI no longer infers liquidation from a
  large `external_closed` wallet loss

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

The production MVP uses the configured commercial `ARB_RPC_URL` for reads,
receipts, recovery, and event delivery. Every signed write is submitted as the
same raw transaction to both the commercial RPC and Arbitrum's direct sequencer.
The first route returning the expected deterministic transaction hash wins.
This cannot create two economic actions because both routes receive identical
bytes, nonce, and hash. Kairos is not part of the production path.

July 27 direct-callback production-backend canary:

- live quote: `8.6ms`
- API open acceptance and persistence: `26ms`
- queue pickup: `70ms`
- open wallet preparation on the hot path: `9.1ms`
- open initiation transaction: `1.112s`
- direct onchain open callback wait: `980ms`
- open worker total: `2.104s`
- open visible through the polling canary: `2.257s`
- API close acceptance and persistence: `16.7ms`
- close queue pickup: below the log timer's `10ms` resolution
- close preparation: `4.7ms`
- close initiation transaction: `903ms`
- direct onchain close callback wait: `1.024s`
- close worker total: `1.932s`
- close visible through the polling canary: `1.958s`
- wallet reconciliation after close commit: about `263ms`
- venue result and wallet delta: both exactly `-$2.000223`

The open initiation landed four Arbitrum blocks before its callback. The close
initiation landed five blocks before its callback. Direct `MarketExecuted`
events won both confirmation races.

July 27 identical-byte dual-write canaries from the local Docker backend:

- 500x open: commercial RPC won in `843ms`; transaction plus receipt `1.355s`
- 500x close: direct sequencer won in `576ms` versus commercial RPC `798ms`
- 500x close worker total: `1.667s`; visible through polling in `1.909s`
- 100x open: commercial RPC won in `766ms`; transaction plus receipt `880ms`
- 100x close: direct sequencer won in `503ms`; transaction plus receipt `608ms`
- 100x close worker total: `1.479s`; visible through polling in `1.649s`

The direct sequencer was cold on each first open and warm by the corresponding
close. The fixed race therefore preserves the commercial RPC's warm-open path
while allowing the sequencer to remove roughly `220-300ms` when it wins. These
are development-machine samples; repeat the same trace from the deployed
backend region before setting an SLO.

The initial backend waited `4.49s` for the normalized close event even though
the economic close callback was already onchain. The current worker therefore
subscribes directly to the deployed Gains diamond and decodes the current
`MarketExecuted` and `LimitExecuted` callback ABI. The normalized Gains stream
remains a fallback.

The same canary paid `1.40s` of first-wallet preparation before the open.
Production now moves that work before the swipe: requesting a quote schedules
pending-nonce, allowance, and owner-event preparation for that user. A local
warm-path check returned a live quote in `55.9ms` and completed wallet
preparation in `0.65s` without submitting a trade.

Measure:

- API acceptance and queue pickup
- nonce/fee cache hit
- tx hash computed
- broadcast start
- broadcast response
- receipt seen
- receipt block
- callback block delta
- Gains event arrival
- REST recovery arrival
- normalized state commit
- winning write route
- commercial RPC and direct-sequencer response time

The gTrade open/close has two sequential chain legs: TICK's initiation and the
venue oracle/callback. RPC tuning only affects the first. The production path
therefore pre-arms direct callback and normalized venue events, removes wallet
preparation from the gesture path, and races those event sources against
delayed REST recovery.

Implementation order:

1. Keep the configured primary RPC warm.
2. Keep nonce, fee, allowance, and price state warm per active wallet/market.
3. Persist the deterministic hash before broadcasting identical signed bytes.
4. Race the commercial RPC and direct sequencer for transaction submission.
5. Use the shared direct Arbitrum callback stream for normal confirmation.
6. Keep normalized Gains events as fallback and REST as delayed recovery.
7. Compare route wins and end-to-end p50/p95 with identical live canaries.
