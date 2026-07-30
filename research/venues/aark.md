# Aark

Snapshot: 2026-07-30.

Status: live tested with the TICK funded development wallet on Arbitrum.

## Bottom Line

Aark's Moon execution path works and is attractive for small, high-leverage
TICK tickets. TICK completed a real deposit, delegated BTC 500x open, close,
accounting reconciliation, and full withdrawal.

Aark is not enabled as a product route yet. Its current integration guide
documents a self-serve browser path: every open carries the user's signed order
plus a fresh reCAPTCHA Enterprise `TRADE` token. Aark's published production
site key issues tokens from TICK's production PWA origin,
`https://tick-project.vercel.app`, but Aark's open endpoint rejects those tokens
with the generic error `9999`, including in a visible browser with the
otherwise-valid live signature.

A token issued on `app.aark.digital` works in a visible browser. TICK therefore
still needs either Aark to accept the TICK production/staging origins or an
Aark-registered partner signing address for server-to-server opens.

## Live Canary

Wallet:

```text
0xD843B63F0829fdA5F8adf4C82a8E36EB9CcbF4f9
```

Terms:

```text
market:       BTC
direction:    long
margin:       $10.00
leverage:     500x
notional:     about $5,000
entry:        63,332.08271317
close:        63,311.33686036
position ID:  390168
```

Observed accounting:

```text
venue balance before open:    $12.000000
execution/network fee:         $0.600000
open fee:                      $0.500000
price PnL:                    -$1.637862
venue balance after close:     $9.262138
withdrawn to user wallet:      $9.262138
venue balance after withdraw:  $0.000000
```

Reconciliation:

```text
$12.000000
- $0.600000 execution fee
- $0.500000 open fee
- $1.637862 price loss
= $9.262138
```

The platform wallet ended with `25.312208 USDC` and unchanged ETH. No Aark
position remained open.

Measured close visibility from the canary command was approximately `2.42s`.
The open request returned `code: 200`, but this first browser-origin canary did
not yet capture a trustworthy gesture-to-position-visible timestamp.

## Documentation Compatibility Canary

On 2026-07-30, TICK tested the new integration guide against Aark's live API
using the same funded wallet and a visible browser:

| Challenge origin | Open signature | Result |
| --- | --- | --- |
| `app.aark.digital` | Documented EIP-191, no frontend-version header | `code: 400`, `Invalid Signature` |
| `tick-project.vercel.app` | Live EIP-712 `MoonOrder` | Generic Aark error `9999` |
| `app.aark.digital` | Live EIP-712 `MoonOrder` | `code: 200`; position opened and closed |

The positive-control trade used position `390584`. It closed in approximately
`2.021s`, with:

```text
venue balance before open:  $12.000000
execution fee:               $0.600000
opening fee:                 $0.500000
realized price PnL:          $0.000007
venue balance after close:  $10.900007
withdrawn to wallet:        $10.900007
venue balance after:         $0.000000
```

This isolates two current integration issues:

1. The documented EIP-191 open signature is not accepted by the live endpoint
   when encoded exactly as shown in the guide.
2. A challenge token issued on the TICK origin is not accepted by the live open
   endpoint, even though Google issues the token successfully.

## Integration Model

- Per-user platform wallet owns the funds.
- TICK derives and registers a deterministic per-user Aark delegate.
- USDC is deposited into the same user's Aark account.
- The delegate signs EIP-712 Moon open and close requests.
- Aark executes gaslessly through its API.
- Funds can be withdrawn back to the platform wallet.

Current production frontend observations:

```text
frontend version: v3.4.26
EIP-712 domain:   name=AARK, chainId=42161
open type:        MoonOrder
close type:       MoonCloseOrder
event transport: Socket.IO at wss://ws-api.aark.digital, path /ws/
```

Aark's integration guide updated in July 2026 instead documents EIP-191
signatures for open and close. The current `app.aark.digital` production bundle
still uses EIP-712 `MoonOrder` and `MoonCloseOrder`, matching TICK's successful
live canaries and current connector. The live endpoint rejected the documented
EIP-191 open as an invalid signature.

## Product Fit

Strengths:

- BTC supports 500x, 750x, and 1000x in the current public market config.
- Small `$10` collateral tickets are supported.
- No user gas prompt in the trading loop.
- No closing trading fee was charged on the losing canary.
- Deposit, delegated execution, close, and withdrawal all worked.

Risks:

- Browser opens depend on a fresh reCAPTCHA token from an origin accepted by
  Aark. The TICK production origin is not currently accepted.
- Backend-only opening requires an Aark-registered partner signing address.
- The new integration guide and current production frontend disagree on open
  and close signature format: documented EIP-191 versus live EIP-712.
- The venue uses a hybrid API/relayer path, so TICK depends on Aark's backend
  availability and authorization policy.
- Aark does not provide the venue-native stop-loss behavior currently required
  by the gTrade route.
- Exact profit-sharing economics must be modeled before enabling positive-PnL
  display or routing.

## Activation Gate

Do not add Aark to `ENABLED_VENUES` until:

1. Aark authorizes TICK's production/staging browser origins or registers a
   TICK partner signing address.
2. Aark confirms that new integrations should currently use the EIP-712 format
   used by its production app, or corrects the rejected EIP-191 example.
3. TICK obtains Aark's staging reCAPTCHA key for non-production testing.

After those checks, run at least 20 controlled cycles and measure:

```text
gesture_to_request_ack_ms
request_ack_to_position_visible_ms
close_request_to_position_gone_ms
terminal_event_delivery_ms
all_fees_usd
venue_balance_delta
withdrawal_latency_ms
```

## Contact

- Email: `contact@aark.digital`
- Discord: `https://discord.gg/aarkdigital`
- Telegram: `https://t.me/official_aark`
- X: `https://x.com/Aark_Digital`
