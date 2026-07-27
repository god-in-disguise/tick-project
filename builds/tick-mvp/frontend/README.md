# iOS PWA

The first production client is an iPhone-shaped, installable PWA deployed
separately from backend Compose.

Use the visual and interaction lessons from
`../../local-mvp/tick-mvp-local-expo/`, but rebuild against the production API
contracts.

Initial screens:

- live trade screen;
- volatility feed;
- active position;
- deposit/withdraw;
- history;
- account/settings.

The chart must remain truthful: real venue ticks only, no fake vertical motion.

The runtime contract is:

- one backend price stream for the whitelisted market set
- one canonical timestamped tape per market, shared by every user
- wallet-scoped position and execution events
- immediate optimistic `opening`/`closing` state after API acceptance
- authoritative `open`/`closed` state after venue execution
- settlement and wallet PnL reconciliation as a separate state
- snapshot recovery after reconnect or iOS background suspension

The trading surface owns vertical direction/close gestures and horizontal
market navigation. Canvas rendering and gesture animation stay outside React's
per-tick render path.
