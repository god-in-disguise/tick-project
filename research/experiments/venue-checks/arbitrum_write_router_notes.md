# Arbitrum Write Router Notes

TICK should pick its Arbitrum write path from measurements, not theory. Users will be in different geos, and one route can win in median while losing badly in p95.

## Routes to Benchmark

- `primary`: current private/provider RPC from `ARB_RPC_URL`.
- `direct`: Arbitrum public direct sequencer endpoint.
- `kairos-standard`: Kairos RPC using normal `eth_sendRawTransaction`.
- `kairos-express`: Kairos `timeboost_sendTransaction`.
- `kairos-bundle`: Kairos `timeboost_sendBundle`, only useful with explicit payment economics.

The local benchmark script is:

```bash
venue-checks/.venv/bin/python venue-checks/arbitrum_write_router_benchmark.py \
  --routes primary,direct,kairos-standard,kairos-express \
  --samples 5 \
  --execute \
  --i-understand-live-risk
```

It sends tiny 0-value ETH self-transfers by default, so the cost is gas only. Use this before spending gTrade market risk on route testing.

## Important Mechanics

The direct sequencer endpoint is not a full RPC. It accepts raw transaction submission methods only. A successful `eth_sendRawTransaction` response means the transaction has already been sequenced into an L2 block at soft finality, but the endpoint is still public and has no formal SLA.

Timeboost is different from direct sequencer submission. Direct sequencer removes provider forwarding, but regular-lane transactions may still get Timeboost delay. Express-lane access can avoid that delay, but only the current express-lane controller or a service with controller access can submit that way.

Kairos is not the Arbitrum block builder. Their docs say submissions need explicit ETH payment in the transaction or bundle payload. That means `kairos-express` may not be economically meaningful without payment, and `kairos-bundle` needs a measured cost/latency tradeoff before production use.

## Kairos Payment Address Reality Check

Kairos docs list the Arbitrum payment address as:

```text
0x60E6a31591392f926e627ED871e670C3e81f1AB8
```

Recent Blockscout sampling on July 21, 2026:

```text
Internal payments sampled: 500
Direct transfers sampled:  200
Combined sampled:          700

Internal median: 0.000002183 ETH
Direct median:   0.000003 ETH
Combined median: 0.000003 ETH
Combined p90:    0.00001 ETH
Combined p95:    0.000021684 ETH
```

At roughly `$1,940/ETH`, that puts the median payment around `$0.006`, p90 around `$0.019`, and p95 around `$0.042` in the sampled set. These are small enough that Timeboost can be economically reasonable for TICK tests, but the payment must be shaped correctly.

The important finding is structure:

- Direct transfers are plain ETH transfers to the payment address with `raw_input=0x` and about 21k gas. They exist, but they are not the main structure for active express use.
- Internal payments are contract `call` transfers into the payment address from strategy/router contracts.
- Top recent internal senders were contracts, especially `0x8A1Ba3d5B7864621A6214627A85A3f252B2E6180` tagged `DEXRebalancer`, plus `0xEa84593154D5834EF39b832Bf9745126771861A2`, `0xfA037a0dd661B22da58d27c895690FFf58A72CA2`, and `0x09EFd9E4578036a712E66FA999Cf9cCaCA664E0c`.
- Parent transaction samples call strategy/router contracts, then those contracts internally transfer ETH to Kairos. Some use a 2300-gas internal payment, while DEXRebalancer-style calls use larger parent gas limits.

This explains why the initial TICK test bundle was accepted by Kairos but showed `payment_initial_sim=0` and never reached the sequencer: a separate self-transfer plus separate payment-transfer bundle did not simulate as a paid useful order. For gTrade, the likely correct production shape is either:

```text
1. a wrapper contract call that executes the delegated gTrade action and pays Kairos inside the same call; or
2. a Kairos bundle format confirmed with their team where the payment is recognized against the useful transaction.
```

The repeatable analyzer is:

```bash
venue-checks/.venv/bin/python venue-checks/kairos_payment_analysis.py \
  --internal-pages 10 \
  --direct-pages 4 \
  --detail-samples 8
```

Latest local report:

```text
venue-checks/reports/kairos-payments/20260721T083052Z.json
```

## Real Kairos-Landed Transaction Check

We inspected parent transaction receipts from the Kairos payment-address sample. The useful finding is that the sampled strategy/router transactions were actually timeboosted:

```text
Receipt field: timeboosted = true
```

So these are not just normal transactions that happened to pay the Kairos address. They are real express-lane examples.

Observed shapes:

- Several EIP-1559 type-2 transactions called `0xEa84593154D5834EF39b832Bf9745126771861A2` with top-level `value = 0`, about `400,000` gas, selector `0x755f317c`, and `maxPriorityFeePerGas = 1 wei`. The Kairos payment appears as an internal transfer from the called contract.
- Several legacy type-0 transactions called `0x8A1Ba3d5B7864621A6214627A85A3f252B2E6180` (`DEXRebalancer`) with selector-like calldata beginning `0x00000000`, high gas limits, and `timeboosted = true`.
- At least one DEX-style parent transaction carried top-level ETH value, but the dominant active pattern is still: call strategy/router contract, then pay Kairos internally.

Direct RPC verification of sampled landed parents:

```text
0xad2a126c6a6127460d7772e0352813f039762793f0e453a9fb3eab97fd372aaf
  to 0xEa84593154D5834EF39b832Bf9745126771861A2, type 2, value 0,
  gas 400,000, gasUsed 145,059, selector 0x755f317c,
  maxPriorityFeePerGas 1 wei, timeboosted true

0x55dbce5d3bf29dc37323f99b31052fb9b079d9191c57c1a1cb7b321888400c68
  same 0xEa845... pattern, gasUsed 178,078, timeboosted true

0xf1c342fe41a111b571d4b52d3a02621790cce4973eefcb2e95f92bd432d50413
  same 0xEa845... pattern, gasUsed 145,021, timeboosted true

0xf2aaf20fff493fb39d4e8dbe9cd3b260e586b2f214014e9d18f34872725472b2
  to 0x8A1Ba3d5B7864621A6214627A85A3f252B2E6180, type 0, value 0,
  gas 7,500,002, gasUsed 307,940, selector 0x00000000,
  gasPrice 45,000,000 wei, timeboosted true
```

The closest cheap pattern for TICK is the first group, not the DEXRebalancer high-gas legacy route.

This means the right production shape is probably not "separate useful tx plus separate payment tx". It is closer to:

```text
agent tx -> useful wrapper/router contract
           -> gTrade action
           -> internal ETH payment to Kairos in the same execution
```

or a Kairos bundle format confirmed by Kairos where the payment is recognized against the useful transaction.

## Kairos Live Canaries

On July 21, 2026 we tried several paid Kairos submissions from the TICK agent:

```text
1. timeboost_sendTransaction directly to Kairos payment address
2. timeboost_sendTransaction to a tiny wrapper that internally pays Kairos
3. timeboost_sendBundle with [noop tx, wrapper-payment tx]
4. legacy/type-0 variants of the wrapper and bundle shapes
```

The wrapper was deployed successfully:

```text
Wrapper: 0x2646FDF91b234D509D60531006C8E49821Ae9C7c
Deploy tx: 0xb21c5b44c02f27426dfa052e4c769b1b02e961cc48c73403a7d8b7880f09ff69
Deploy gas used: 63,820
```

A normal primary-RPC call to that wrapper succeeded:

```text
Tx:       0x38bbb6f320c6a59a683b1bfcdd02afd68fdd7b866505dfb2c1946abc8d35d18f
Payment: 0.000003 ETH
Gas:     30,777
Total:   1,654.2ms
```

So the wrapper itself works. However, Kairos order-info still reported:

```text
payment_initial_sim = 0
payment_block_sim   = 0
sent_to_sequencer   = false
```

even in several samples where `expressLaneController=true`. This means the current TICK submission shape is not being recognized as a paid express-lane order by Kairos. Do not wire Kairos into the gTrade hot path until we either get a known-good transaction shape from Kairos or reproduce a nonzero `payment_initial_sim` locally.

We then recreated the real-world pattern more closely with a fixed-funded wrapper:

```text
Wrapper:      0xd50Bf36311554dFb8340DCd9336C4C4111fB24e9
Deploy tx:    0x86f35e7a9224f93d782e2adb81b36f2fd07804c51fc303f32d732b1fb94f3462
Funding tx:   0x2dcb91be1de90a2a6c2ca00b8ba1e4e8833d77d8668932b2166139c1327b2f67
Funding size: 0.000012 ETH
Payment size: 0.000003 ETH
Call data:    0x755f317c
```

This wrapper lets the top-level transaction use `value = 0` while the wrapper pays Kairos from its own ETH balance, matching the broad shape of the sampled real strategy/router transactions. The result was still negative:

```text
Report:                 venue-checks/reports/kairos-wrapper/20260721T090009Z.jsonl
Samples attempted:       40
Controller-true samples: at least 10 before interruption
payment_initial_sim:     0
payment_block_sim:       0
sent_to_sequencer:       false
receipts:                none
```

So we have not landed a TICK transaction through Kairos yet. The remaining gap is likely an exact contract/call-shape requirement, a Kairos simulation assumption, or an undocumented API/payment rule. The next useful step is to inspect or obtain a known-good minimal contract pattern from Kairos, not keep randomly changing payment size.

We then tested the user's concern that self-transfers might be a special bad canary by sending a tiny amount to the delegated gTrade agent instead:

```text
Sender:    0xeD1fa479504Ec60DB8a314BfF2DbbD1bB481Db78
Recipient: 0x12Aa0ED4adCbF83C0aC46bAF8218d757555A9C38
Value:     0.000001 ETH
Route:     kairos-standard / eth_sendRawTransaction
Report:    venue-checks/reports/arbitrum-write-router/20260721T095912Z.jsonl
Tx hash:   0x26dfa7f41e832c9e7e36d02014d5a2b39c9ad16a97a1ab3a191c374bb1b82ddd
Result:    Kairos returned the tx hash, but no receipt appeared after 12s.
Nonce:     unchanged at 54
ETH delta: 0
```

The exact same signed transaction hash was then sent through the normal primary RPC:

```text
Report:    venue-checks/reports/arbitrum-write-router/20260721T095942Z.jsonl
Tx hash:   0x26dfa7f41e832c9e7e36d02014d5a2b39c9ad16a97a1ab3a191c374bb1b82ddd
Block:     486147483
Status:    1
Gas used:  21,302
Timeboost: false
Nonce:     advanced to 55
```

This is the cleanest isolation test so far. The transaction was valid and did not depend on self-transfer behavior. Kairos standard returned a hash but did not relay it; the primary RPC landed the same raw transaction.

We also matched the active real Kairos transaction shape more closely:

```text
Wrapper kind:       fixed-funded-2300
Wrapper:            0x5FCf917B8EA528Ba65Eab3d153206DbFfC6d4b72
Deploy tx:          0x827e48e22f5206aa239161880502e02184a5efa5ef8a7e22de5002bc5ec879f9
Funding tx:         0xa25b86d3463613642efc660c687cdd1eb9672fee4e906705018dc09da9a9c275
Primary proof tx:   0xdd64f91a996b94810596f3a57b03db522fcb40e573641afdbf870cf22202c450
Call shape:         top-level value 0, selector 0x755f317c, 292-byte calldata, gas 400,000
Internal payment:   0.000003 ETH to Kairos with 2,300 gas
Report, proof:      venue-checks/reports/kairos-wrapper/20260721T100306Z.jsonl
Report, Kairos:     venue-checks/reports/kairos-wrapper/20260721T100322Z.jsonl
```

The primary proof call succeeded. The Kairos version still did not land:

```text
Samples attempted:        36
Controller-true samples:  present
payment_initial_sim:      0
payment_block_sim:        0
sim_status:               false
sent_to_sequencer:        false
nonce:                    unchanged at 68
```

This rules out the obvious transaction-shape issues:

```text
not a self-transfer issue
not an invalid transaction issue
not a top-level value issue
not a selector/calldata-length issue
not an internal payment gas-stipend issue
not simply underpaying versus sampled medians
```

The remaining likely explanations are now narrower:

```text
1. Kairos public intake is allowlisted or requires integration registration.
2. Kairos payment recognition supports only known router/strategy contracts.
3. Arbitrary contracts are not simulated the same way as sampled production routers.
4. kairos-standard's documented eth_sendRawTransaction endpoint may not be a general relay path from our sender.
5. The endpoint requires an extra payment/order field not reflected in the public docs or current examples.
```

The new useful artifacts to send Kairos are:

```text
User wallet:          0xeD1fa479504Ec60DB8a314BfF2DbbD1bB481Db78
Delegate/agent:       0x12Aa0ED4adCbF83C0aC46bAF8218d757555A9C38
2300 wrapper:         0x5FCf917B8EA528Ba65Eab3d153206DbFfC6d4b72
Primary proof tx:     0xdd64f91a996b94810596f3a57b03db522fcb40e573641afdbf870cf22202c450
Delegate transfer tx: 0x26dfa7f41e832c9e7e36d02014d5a2b39c9ad16a97a1ab3a191c374bb1b82ddd
Symptom:              same tx lands through primary RPC, while Kairos returns a hash/order but does not sequence.
```

## Fresh Kairos Pending-State Canaries

After the first wrapper tests, we tested the more exact `pendingTxs` hypothesis:

```text
txs:        [raw signed payment tx]
pendingTxs: [raw signed deploy tx, where applicable]
```

We also deployed a cleaner payable canary that:

```text
1. increments storage slot 0
2. forwards full msg.value to Kairos
3. reverts if the internal payment fails
```

Fresh deployed canary:

```text
Canary:    0x233B180124715e15346D04239ee35d0F71E56F94
Deploy tx: 0xe8e3e14973aed5e81297921f72de6ce5666c2d7255c184f9cec98ae77b071cd5
```

A normal primary-RPC call to that canary succeeded:

```text
Tx:          0xb5445d548f77981483065905c65a81b96f45c22f4bece0bf3c0152ac5de29101
Block:       486141028
Status:      1
Gas used:    52,785
Timeboosted: false
```

This proves the wrapper logic and calldata are valid on Arbitrum. Kairos still rejected the same family of transactions before sequencing.

Fresh Kairos report summary:

```text
venue-checks/reports/kairos-pending/20260721T092722Z.jsonl
  mode: bundle with raw deploy tx in pendingTxs
  samples: 20
  controller-true: 3
  sequenced: 0
  nonce unchanged after deploy

venue-checks/reports/kairos-pending/20260721T093014Z.jsonl
  mode: timeboost_sendTransaction to deployed payable canary
  samples: 30
  controller-true: 16
  sequenced: 0
  nonce unchanged

venue-checks/reports/kairos-pending/20260721T093306Z.jsonl
  mode: repeat single after normal primary-RPC proof
  samples: 30
  controller-true: 30
  sequenced: 0
  nonce unchanged

venue-checks/reports/kairos-pending/20260721T093500Z.jsonl
  mode: legacy/type-0 single
  samples: 25
  controller-true: 1
  sequenced: 0
  nonce unchanged

venue-checks/reports/kairos-pending/20260721T093713Z.jsonl
  mode: fixed-funded wrapper, tx value = 0
  samples: 30
  controller-true: 30
  sequenced: 0
  nonce unchanged
```

The repeated Kairos order-info shape was:

```text
order_validation       = ""
express_lane_controller = true
sim_status             = false
sim_result             = ""
payment_initial_sim    = "0"
payment_block_sim      = "0"
sent_to_sequencer      = false
express_lane_status_code = 0
mined_block_number     = null
```

We also tested the simplest possible direct payment:

```text
To:       0x60E6a31591392f926e627ED871e670C3e81f1AB8
Value:    0.000003 ETH
Gas:      21,000
Method:   timeboost_sendTransaction
Report:   venue-checks/reports/kairos-wrapper/20260721T094214Z.jsonl
Samples:  5
```

All five samples returned `expressLaneController=true`, but all five remained:

```text
sim_status          = false
payment_initial_sim = "0"
payment_block_sim   = "0"
sent_to_sequencer   = false
nonce unchanged
balance unchanged
```

Finally, we tested Kairos's documented standard `eth_sendRawTransaction` path with a plain 0-value self-transfer:

```text
Report:     venue-checks/reports/arbitrum-write-router/20260721T095239Z.jsonl
Method:     eth_sendRawTransaction
Route:      https://rpc.kairos-timeboost.xyz
Tx hash:    0x21b0b5e70349ee0922db79b1879f467a9a28d05632566e4fe72e239265436968
Result:     Kairos returned the tx hash, but no receipt appeared.
Nonce:      unchanged at 65
ETH delta:  0
```

Conclusion: we have not landed any TICK-originated transaction through Kairos. The failure is no longer explained by stale deployment/funding state, bad wrapper code, payment size, or a too-specific wrapper transaction. Even a top-level payment to the Kairos address was not recognized as a paid order, and a plain `eth_sendRawTransaction` self-transfer through Kairos did not relay on-chain. This now looks like either an undocumented Kairos intake rule, an allowlist/access issue, or a public endpoint behavior that differs from the docs.

The useful artifacts to send Kairos are:

```text
Agent:              0x12Aa0ED4adCbF83C0aC46bAF8218d757555A9C38
Canary contract:    0x233B180124715e15346D04239ee35d0F71E56F94
Normal proof tx:    0xb5445d548f77981483065905c65a81b96f45c22f4bece0bf3c0152ac5de29101
Standard relay fail: 0x21b0b5e70349ee0922db79b1879f467a9a28d05632566e4fe72e239265436968
Failed direct IDs:  73a23a2a-3bf7-426f-a2e4-2cd33fef492d,
                    036c90a0-f39f-4c5e-9667-be7d2b80ba4a,
                    855d4444-1081-49d8-a6d3-4356cfbf037f
Symptom:            sim_status=false with empty sim_result and both payment fields zero.
```

Current useful scripts:

```bash
# Deploy/test the internal-payment wrapper.
venue-checks/.venv/bin/python venue-checks/kairos_wrapper_canary.py \
  --send-mode kairos-bundle \
  --samples 3 \
  --payment-wei 3000000000000 \
  --execute \
  --i-understand-live-risk
```

Latest reports:

```text
venue-checks/reports/kairos-wrapper/20260721T083616Z.jsonl
venue-checks/reports/kairos-wrapper/20260721T084001Z.jsonl
venue-checks/reports/kairos-wrapper/20260721T084649Z.jsonl
venue-checks/reports/kairos-wrapper/20260721T084906Z.jsonl
```

## Fresh Primary vs Direct Sequencer Benchmark

On July 21, 2026 we reran 5 samples each with tiny self-transfers:

```text
Report: venue-checks/reports/arbitrum-write-router/20260721T084928Z.jsonl
```

Results:

```text
primary:
  ok:          5/5
  broadcast:  p50 537.3ms, p95 1953.7ms
  receipt:    p50 142.5ms, p95 148.6ms
  total:      p50 1087.4ms, p95 2497.0ms

direct sequencer:
  ok:          5/5
  broadcast:  p50 553.9ms, p95 1809.3ms
  receipt:    p50 144.1ms, p95 404.7ms
  total:      p50 1118.9ms, p95 2365.7ms
```

Decision from this sample:

```text
Use the current private/provider RPC as the default write path for now.
Keep direct sequencer as measured fallback/hedge candidate.
Do not assume public direct sequencer is faster from this machine.
```

## Decision Rule

Choose by p95 over live samples:

```text
best write route =
  lowest p95 broadcast/soft-confirmation
  + low error rate
  + no nonce ambiguity
  + acceptable gas/payment cost
```

For the app hot path, `ARB_WRITE_MODE` now supports:

```text
primary_rpc
direct_sequencer
kairos_standard
kairos_express
```

`ARB_WRITE_RPC_URL` still overrides the endpoint when we want to test a specific paid RPC.

Sources:
- Arbitrum chain info and direct sequencer behavior: https://docs.arbitrum.io/for-devs/dev-tools-and-resources/chain-info
- Arbitrum Timeboost usage: https://docs.arbitrum.io/how-arbitrum-works/timeboost/how-to-use-timeboost
- Kairos submission API: https://docs.kairos-timeboost.xyz/json-rpc-endpoints/submission-api
