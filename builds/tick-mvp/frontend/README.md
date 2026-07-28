# TICK PWA

iPhone-first web app for the TICK trading loop.

## Local

```bash
npm install
npm run dev
```

Vite proxies `/api`, `/health`, and `/ready` to `http://127.0.0.1:8787`.
The local app automatically creates a JWT session for the funded `funded-dev`
user.

Opening the URL in a normal browser shows the install landing. The full product
opens in standalone PWA mode. Add `?app=1` for a browser-only development
preview.

## Authentication

- Local development uses `VITE_DEV_USER_ID` when `VITE_AUTO_DEV_AUTH=true`.
- Production supports Google Identity Services with
  `VITE_GOOGLE_CLIENT_ID`.
- A private-demo access code can be enabled with
  `VITE_DEMO_AUTH_ENABLED=true`; the backend must also configure
  `TICK_DEMO_ACCESS_CODE`.

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
VITE_GOOGLE_CLIENT_ID=<google-web-client-id>
VITE_DEMO_AUTH_ENABLED=true
VITE_AUTO_DEV_AUTH=false
```

## Rendering

The chart stores only real gTrade observations. Canvas owns the 60 FPS visual
interpolation of the live edge; animation frames never become market history or
affect PnL, chart extrema, or execution terms.
