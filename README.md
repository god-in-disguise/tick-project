# TICK Research Project

This repository now separates the proven local prototype from the next production-shaped MVP.

## Layout

- `project_overview/` - product, infra, and build-spec documents.
- `research/` - venue research, market notes, and live canary experiments.
- `builds/local-mvp/` - frozen prototype apps and local live-trading MVP code.
- `builds/tick-mvp/` - clean production MVP scaffold for backend on DigitalOcean and PWA frontend on Vercel.

## Current Decision

The local MVP is frozen as the reference implementation. It proved the core loop:

- live gTrade/Gains execution on Arbitrum;
- mobile-first trading UI;
- native stop-loss handling;
- wallet-delta reconciliation;
- chart and execution latency lessons.

New production work should happen in `builds/tick-mvp/`. Pull proven pieces out of `builds/local-mvp/`; do not keep productionizing the prototype in place.
