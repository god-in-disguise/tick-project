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

## Rendering

The chart stores only real gTrade observations. Canvas owns the 60 FPS visual
interpolation of the live edge; animation frames never become market history or
affect PnL, chart extrema, or execution terms.
