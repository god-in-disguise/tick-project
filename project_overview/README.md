# Project Overview

This folder contains the source-of-truth thinking for TICK:

- product framing;
- market research;
- technical architecture;
- local MVP lessons;
- real-build specification.

Use `tick_real_build_spec.md` as the current source of truth before changing `builds/tick-mvp/` architecture. Older concept, market, and kill-memo docs are supporting context and may describe earlier assumptions that the real-build spec has since superseded.

## Product TODOs

- Add a deliberate chart context control that switches between the truthful
  60-90 second live tape and a wider 5-15 minute view, then returns to the
  exact live state. Both views must use the same market source, preserve real
  extrema, and avoid a blank frame or retrospective rescaling during the
  transition.
- Research current crypto day-trader workflows after the private demo deploy,
  then translate only the highest-value context signals into TICK without
  turning the default screen into a professional terminal.
