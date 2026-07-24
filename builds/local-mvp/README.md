# Local MVP

This folder contains frozen prototype work.

## Contents

- `tick-mvp-local/` - FastAPI local backend and venue connector experiments.
- `tick-mvp-local-expo/` - Expo mobile app used for real gTrade canaries.
- `tick-mobile-mockup/` - earlier visual mockup.
- `tick-web-app/` - earlier web-board mockup.

This code should remain runnable for reference, but production work should move into `../tick-mvp/`.

When extracting code, prefer small, explicit modules:

- quote model;
- venue connector;
- execution state machine;
- event listener;
- reconciliation logic;
- chart data contract.

