# Aster

Snapshot: 2026-07-14.

Status: official documentation researched; public V3/RPC smoke tested; 1001x direct-contract read/dry-run tested; no TICK signed trade yet.

## Bottom Line

Aster is the strongest high-leverage candidate discussed so far, but its products must not be mixed together.

The main TICK candidate is Aster Perpetuals V3: an Aster L1-backed order-book API with API-wallet/agent signing, WebSocket market/user streams, market orders, isolated margin, reduce-only closes, and documented direct filled-result responses for market orders.

The separate 1001x product is a different pool/oracle/on-chain product. It has the insane leverage headline, but it should be treated as a separate experiment, not the default TICK connector.

## Aster Pro

- V3 is the current recommended API for new integrations.
- New V1 API key creation is no longer supported from 2026-03-25; existing V1 keys continue to work.
- V3 uses an API Wallet / Agent model rather than plain API-key HMAC.
- Futures V3 is built on Aster L1 and Aster documents stronger "Take Order" performance.
- Base endpoint in the V3 docs is `https://fapi.asterdex.com`.
- The docs' Python example still uses `https://fapi3.asterdex.com`, but this host returned `403 Forbidden` from this machine on 2026-07-13. Use `https://fapi.asterdex.com` for TICK probes unless Aster support says otherwise.
- Market data and user state also have an Aster Chain JSON-RPC path at `https://tapi.asterdex.com/info`.
- Order endpoint is `POST /fapi/v3/order`.
- Client order IDs and reduce-only orders are supported.
- Market orders support `newOrderRespType=RESULT`; the docs say a market order returns the final filled result directly.
- Cross and isolated margin are supported, with API operations for margin type and initial leverage.
- Documentation recommends WebSocket account updates because REST may lag under volatility.
- WebSocket depth can update as fast as 100ms; book ticker is real-time; ticker streams update at 500ms-1000ms.
- There is a `Noop` endpoint intended to cancel queued requests with the same nonce before on-chain completion, with no guarantee of success.

This is likely a strong Python connector target. The main work is not transaction building; it is agent onboarding, signing, nonce handling, isolated margin setup, stream ordering, and reconciliation.

## Public Connectivity Smoke

Measured from this repo machine on 2026-07-13 with `venue-checks/aster_public_probe.py`:

```text
GET  https://fapi.asterdex.com/fapi/v3/ping                              -> 200 {}
GET  https://fapi.asterdex.com/fapi/v3/ticker/bookTicker?symbol=BTCUSDT  -> live bid/ask, ~330ms
GET  https://fapi.asterdex.com/fapi/v3/depth?symbol=BTCUSDT&limit=5       -> live depth, ~330-360ms
GET  https://fapi.asterdex.com/fapi/v3/premiumIndex?symbol=BTCUSDT        -> mark/index/funding, ~330ms
GET  https://fapi.asterdex.com/fapi/v3/ticker/24hr?symbol=BTCUSDT         -> 24h stats, ~330ms
GET  https://fapi.asterdex.com/fapi/v3/exchangeInfo                      -> BTCUSDT metadata, ~420ms
POST https://tapi.asterdex.com/info aster_getBalance(dummy)               -> 200 JSON-RPC, ~625-1600ms
GET  https://fapi3.asterdex.com/fapi/v3/ping                             -> 403 awselb/2.0
```

BTCUSDT public metadata returned:

```text
status:                 TRADING
minNotional:            5 USDT
market min/max quantity: 0.001 / 120 BTC
requiredMarginPercent:  5.0000
maintMarginPercent:     2.5000
marketTakeBound:        0.02
triggerProtect:         0.0200
liquidationFee:         0.025000
```

The earlier "blocked IP" diagnosis was too broad. Public market data is reachable through `fapi.asterdex.com`. The real signed-trade blocker is API-wallet/agent setup. Local sandbox DNS did intermittently fail for Python until the probe was run with direct network permission, so the connector should use retries, keep WebSocket subscriptions warm, and cache expensive resources such as `exchangeInfo`.

## V3 Auth Model

V3 requests include:

```text
user      main account wallet
signer    API wallet / agent address
nonce     microsecond timestamp
signature ECDSA signature from the API wallet
timestamp where required
```

The signing flow is EIP-712 style:

```text
sort request params
urlencode them
put the encoded string into message.msg
sign with the API wallet private key
submit params plus signature
```

Agent registration and approval can be done through `POST /fapi/v3/registerAndApproveAgent`. The user signs approval with the main wallet. Permissions include spot trading, perp trading, withdrawals, expiration, and optional IP whitelist. For TICK, the first live setup should create an agent with:

```text
canPerpTrade=true
canSpotTrade=false unless needed
canWithdraw=false
short expiration at first
IP whitelist enabled if practical
```

This model fits TICK better than raw exchange custody because the user/account can approve a constrained agent, while TICK keeps a backend signer for fast order placement.

## 1001x Is Separate

Aster's 1001x product is an on-chain high-leverage product with its own pool/oracle model and direct contract interaction path.

Current documented leverage:

```text
BTC/USD:       up to 1001x
ETH/USD:       up to 250x
Other crypto:  up to 75x
Forex:         up to 200x
```

For 500x, 750x, and 1001x BTC leverage, Aster documents:

```text
0% open fee
dynamic PnL-based close fee
no adding margin to open positions
maximum net profit ROI cap
```

For leverage below 500x, 1001x uses 0.08% open and 0.08% close fees. It also has an execution fee: documented as `$0.50` on BNB Chain and `$0.20` on Arbitrum.

Direct contract interaction is documented on BNB Chain through contract `0x1b6f2d3844c6ae7d56ceb3c3643b9060ba28feb0`, with methods such as `openMarketTrade`, `closeTrade`, `addMargin`, `updateTradeTpAndSl`, and `cancelLimitOrder`. Margin amount uses 1e18 decimals for USDT/USDC, price uses 1e8, and contract quantity uses 1e10.

### 1001x Direct-Contract Probe

Measured on 2026-07-14 and 2026-07-20 with `venue-checks/aster_1001x_probe.py`, direct RPC calls, and the official AsterEX ABI.

BNB Chain public contract reads worked:

```text
contract:              0x1b6F2d3844C6ae7D56ceb3C3643b9060ba28FEb0
chain:                 BNB Chain, chain id 56
paused:                false
marketTrading:         true
userCloseTrading:      true
executionFeeUsd:       $0.50
minNotionalUsd:        $200
contract code size:    6039 bytes
read latency:          about 1.5-1.9s through public RPC
```

The local `WALLET_PK` resolved to an EVM wallet, but that wallet had no BNB and no USDT on BNB Chain, so a live canary cannot execute until the wallet is funded and approved on BSC.

BTC and ETH live config reads:

```text
BTC/USD:
  pair status:       1
  max long OI:       $5.5m
  max short OI:      $5.5m
  leverage returned: 250x
  eth_call open:     reverts with "TradingCheckerFacet: The pair is temporarily unavailable for trading"

ETH/USD:
  pair status:       1
  max long OI:       $5.0m
  max short OI:      $5.0m
  leverage returned: 250x
  eth_call open:     reverts with "TradingCheckerFacet: The pair is temporarily unavailable for trading"
```

This means Aster 1001x fits the wallet-native requirement architecturally, but the current direct-contract path is not yet accepted for TICK execution. The next question for Aster is whether this contract is the active production path for 1001x trading, whether `status=1` means paused/unavailable, and where the documented BTC 1001x configuration is exposed.

Arbitrum direct-contract reads also worked against `0xB3879E95a4B8e3eE570c232B19d520821F540E48`. This address has a small proxy-like bytecode size but responds to AsterEX read methods.

Arbitrum `pairsV3()` returned 8 configured markets, all with `status=1`:

```text
500BTC/USD: 1000x, $750k max long OI / $750k max short OI
BTC/USD:     250x, $750k max long OI / $750k max short OI
ETH/USD:     250x, $500k max long OI / $500k max short OI
DOGE/USD:     75x
XRP/USD:      75x
ARB/USD:      50x
GMX/USD:      20x
RDNT/USD:     20x
```

Arbitrum `tokensV3()` returned margin-capable USDC.e, DAI, USDT, and WETH. The local wallet had ETH for gas on Arbitrum, but no USDC.e allowance or balance.

However, this is still not accepted for execution. A dry-run of `openMarketTradeCheck` and `openMarketTrade` against Arbitrum `500BTC/USD` reverted with:

```text
TradingCheckerFacet: The pair is temporarily unavailable for trading
```

The same unavailable-pair revert was seen on BNB BTC/ETH and Arbitrum 500BTC. So the issue is not merely missing BNB, missing USDC, allowance, or wrong BTC base address. It appears to be a protocol-side availability gate, product-mode gate, or stale/direct-contract route.

Verified source for the ApolloX/Aster-style contracts defines:

```text
PairStatus.AVAILABLE   = 0
PairStatus.REDUCE_ONLY = 1
PairStatus.CLOSE       = 2
```

`TradingCheckerFacet.openMarketTradeCheck` requires `pair.status == PairStatus.AVAILABLE`. Since the tested Arbitrum pairs returned `status=1`, they are reduce-only. That explains the revert:

```text
TradingCheckerFacet: The pair is temporarily unavailable for trading
```

Broker id was also tested on Arbitrum `500BTC/USD` with `0`, `1`, `100`, and `999999`; all returned the same pair-unavailable revert. This confirms the failure happens before broker attribution.

For Privy/TICK, the promising route is:

```text
Privy embedded EVM wallet
-> Arbitrum wallet address
-> user-funded USDC.e/USDT + ETH gas or gas sponsorship
-> Aster 1001x direct contract
```

But this route cannot be used until Aster confirms why the direct contract rejects market opens.

For TICK V1:

```text
Aster Perpetuals V3 = main candidate execution venue
Aster 1001x          = wallet-native high-leverage experiment, not accepted yet
```

Do not route the same normalized order blindly across both products.

## Fees And Points

Aster docs currently show several fee contexts:

```text
Aster Perpetuals / campaign docs: maker 0.005%, taker 0.040%
1001x below 500x:              0.08% open, 0.08% close
1001x BTC 500x+:               0% open, dynamic PnL-based close fee, minimum close fee 0.03%
```

The connector must fetch/verify the live user commission rate before quoting TICK costs.

Aster Convergence Stage 6 currently uses points for Aster Perpetual and Spot activity. The docs describe a scoring model based on trading points, position points, Aster asset points, liquidation points, PnL points, team boosts, and referral points. They also state that rules can be adjusted and that wash trading, market manipulation, bulk accounts, and fraud can be disqualified.

Aster Code allows approved builder attribution and builder fees. Builder use requires explicit user authorization and current program eligibility.

## TICK Fit

Strengths:

- Best high-leverage candidate if V3 fill latency is actually fast.
- `MARKET` with `newOrderRespType=RESULT` is promising because it should return filled result directly.
- API-wallet/agent model fits backend execution without handing full withdrawal control to the trading engine.
- Large market set and live WebSocket data.
- Current Stage 6 points and builder attribution.
- Agent permissions, expirations, and IP restrictions support backend execution controls.
- Isolated margin matches TICK's one-position risk model.
- Aster Chain RPC can query balances, positions, open orders, and fills by wallet address.

Risks and unknowns:

- High leverage does not fix the fee hurdle: two 4 bps taker fills cost about 8% of margin at 100x before spread/slippage/funding.
- V3 signing is more complex than V1 HMAC and nonce mistakes can reject trades.
- Product, chain, collateral, and custody details differ between Perpetuals V3 and 1001x.
- `fapi3.asterdex.com` is not a reliable target from this machine; it returned AWS ALB `403`. Public V3 reads worked through `fapi.asterdex.com`, with occasional local DNS flakiness.
- Signed live testing still needs a proper Aster API wallet/agent.
- Headline maximum leverage and the API leverage bracket may differ by symbol; query the live bracket before every preset decision.
- Need live measurements for order acknowledgement, fill result, user stream lag, Aster Chain RPC lag, and close latency.
- Points value and future distributions are uncertain.

## Next Test

1. Create a test Aster account and register an API wallet/agent with `canPerpTrade=true` and `canWithdraw=false`.
2. Confirm whether TICK should use EVM or Solana user wallet signing for agent approval.
3. Build the V3 Python signer first: EIP-712 message, microsecond nonce, deterministic param encoding, replay protection.
4. Query `/fapi/v3/exchangeInfo`, live leverage brackets, user commission rate, margin mode, position mode, and user stream behavior.
5. Set isolated margin and leverage on BTCUSDT.
6. Open and reduce-only close a small isolated BTC position with `MARKET` and `newOrderRespType=RESULT`.
7. Measure:

```text
submit HTTP latency
filled-result latency
user stream order update latency
position visible latency
close filled-result latency
balance/PnL reconciliation
```

8. Only after Perpetuals V3 is measured, decide whether 1001x direct-contract BTC deserves a separate canary.

## Primary Sources

- [Aster Pro API overview](https://docs.asterdex.com/product/aster-perpetuals/api)
- [Aster V1 vs V3 API overview](https://github.com/asterdex/api-docs/blob/master/Aster%20API%20Overview.md)
- [Aster Futures API V3](https://github.com/asterdex/api-docs/blob/master/V3%28Recommended%29/EN/aster-finance-futures-api-v3.md)
- [Aster Chain RPC](https://github.com/asterdex/api-docs/blob/master/RPC/aster-chain-rpc.md)
- [Aster Perpetuals margin](https://docs.asterdex.com/trading/perpetuals/margin)
- [Aster Code](https://docs.asterdex.com/program-and-rewards/aster-code)
- [Aster Convergence Stage 6](https://docs.asterdex.com/program-and-rewards/points-and-campaigns/aster-convergence-stage-6)
- [1001x leverage](https://docs.asterdex.com/trading/1001x/leverage)
- [1001x fees and slippage](https://docs.asterdex.com/trading/1001x/fees-and-slippage)
- [1001x direct contract interaction](https://docs.asterdex.com/trading/1001x/direct-contract-interaction)
