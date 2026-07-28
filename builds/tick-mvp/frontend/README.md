# TICK PWA

iPhone-first web app for the TICK trading loop.

## Local

```bash
npm install
npm run dev
```

Vite proxies `/api`, `/health`, and `/ready` to `http://127.0.0.1:8787`.
The local and deployed apps both use an invitation code and receive
the same backend-issued JWT session.

Opening the URL in a normal browser shows the install landing. The full product
opens in standalone PWA mode. Add `?app=1` for a browser-only development
preview.

## Authentication

- Invitation login calls `POST /api/auth/invite`.
- The invite code is the private MVP account credential.
- First use creates one TICK account and platform wallet.
- Reusing the same invite restores that account and wallet.
- The backend uses an internal placeholder email until optional verified
  account linking is added.

Every authenticated identity receives its own platform-created Arbitrum wallet.

## Wallet

Me contains:

- Arbitrum USDC deposit address and QR;
- spendable balance after platform gas charges;
- automatic USDC withdrawals;
- trade settings and filtered net-result history.

## Verify

```bash
npm run build
npm run smoke
```

The smoke test checks the install landing, trading screen, and account screen at
an iPhone-sized viewport with headless Chrome.

## Deploy

The Vercel project root is this directory. Configure:

```text
VITE_API_BASE_URL=https://<backend-host>
```

## Rendering

The chart stores only real gTrade observations. Canvas owns the 60 FPS visual
interpolation of the live edge; animation frames never become market history or
affect PnL, chart extrema, or execution terms.
