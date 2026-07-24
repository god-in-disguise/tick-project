# TICK Local Expo Client

Expo SDK 54 client for the real one-wallet canary backend.

## Configure

Use the laptop LAN address that the phone can reach:

```bash
export EXPO_PUBLIC_API_BASE=http://192.168.1.189:8787
export EXPO_PUBLIC_TICK_TOKEN=tick-local-one-wallet
```

The defaults use those same values, but environment variables avoid another code edit when the LAN IP changes.

## Run

Start the Python backend first, then:

```bash
cd tick-mvp-local-expo
PATH=/Users/savvasepelev/.nvm/versions/node/v22.21.1/bin:$PATH \
  npm run start -- --host lan --port 8086 --clear
```

Scan the QR from Expo Go while the phone and laptop are on the same Wi-Fi.

## Gestures

```text
flat + swipe up       open long
flat + swipe down     open short
live long + swipe up  close
live short + swipe down close
flat + swipe left/right change market
```

Horizontal market switching is locked while a position is opening, live, or closing. The Close button remains available as a fallback.

The client contains no fake trade history or fake prices. Minute closes seed the chart, then the local backend supplies timestamped real samples for the moving tape.

## Verify

```bash
PATH=/Users/savvasepelev/.nvm/versions/node/v22.21.1/bin:$PATH npm run typecheck
PATH=/Users/savvasepelev/.nvm/versions/node/v22.21.1/bin:$PATH npx expo export --platform web
```
