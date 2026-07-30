# TICK Swipe Interaction Research

## Decision

TICK needs two different swipe models because the gestures have different
consequences:

- Horizontal market navigation should feel fast, direct, and exploratory.
- Vertical trade execution should feel immediate but deliberately armed.

The recommended model is:

1. Use a full-screen, finger-tracking pager for horizontal market changes.
2. Use a constrained pull-to-arm gesture for vertical open and close actions.
3. Keep visible buttons as accessible alternatives for actions that move money.

This combines the strongest parts of feed paging, iOS direct manipulation, and
progressive swipe actions without making trading resemble dismissing a dating
card.

## Patterns Reviewed

### Full-screen feed paging

YouTube Shorts uses vertical swipes to move through full-screen content. Its
strength is continuity: the next item is spatially adjacent and navigation is
the content itself.

Useful for TICK:

- Adjacent markets are preloaded.
- The current and next market move with the finger.
- Release completes or cancels the transition according to distance and
  velocity.
- Returning to a market restores its existing chart state.

Not useful for TICK:

- Vertical paging conflicts with TICK's long and short gestures.
- An endless-feed transition is too casual for a financial command.

### Card decisions

Tinder uses left and right swipes as opposing decisions. Its progressive card
movement makes the pending result legible before release.

Useful for TICK:

- Direction becomes visible before commitment.
- A gesture below the threshold returns to rest.
- A decisive fling can complete quickly.

Not useful for TICK:

- Rotation, large color floods, and throwing the card away would feel too
  disposable and game-like.
- TICK must preserve the chart and economic state after submission.

### Native direct manipulation

Apple's fluid-interface guidance emphasizes immediate response, rubber-banding,
velocity projection, spring behavior, and continuity. The interface should
remain attached to the gesture and animations should be interruptible.

This is the core motion model TICK should follow.

### Progressive action reveal

Mail-style swipe actions reveal intent while the user drags and commit only
after crossing a threshold. This is the best conceptual base for opening and
closing risk, but TICK should apply it vertically and keep the market scene in
place.

## Recommended Interaction

### Horizontal: market pager

The whole market scene follows the finger horizontally at approximately 1:1:

- asset header;
- chart;
- market story;
- trade terms;
- asset-colored ambient surface.

The previous or next market is already rendered immediately beside it. There
must be no blank chart, delayed history request, or retrospective redraw after
the new market becomes visible.

On release:

- commit when displacement is about 25-30% of viewport width; or
- commit when projected velocity indicates an intentional fling;
- otherwise spring back to the current market.

At the first or last available market, movement should become progressively
resistant instead of hitting a hard wall.

Do not rotate the screen or make it shrink into a card. It is a spatial market
pager, not a discard interaction.

### Vertical: pull to arm

The chart remains the stable object. As the user drags:

1. The market scene moves only a constrained 60-90px and gains resistance.
2. A silver directional rail emerges from the relevant edge.
3. The command changes progressively:
   - `PULL FOR LONG`
   - `RELEASE FOR LONG`
   - `PULL FOR SHORT`
   - `RELEASE FOR SHORT`
4. The rail and label follow real gesture progress.
5. One light haptic fires when the action becomes armed.
6. Reversing below the threshold disarms it and produces one subtle selection
   haptic.
7. Releasing while armed submits immediately.
8. Releasing while unarmed springs back without side effects.

When a position is open, only the matching direction arms `CLOSE`. The opposite
direction visibly resists and explains that the existing position must be
closed first.

The submission must not wait for the reset animation. The scene returns to rest
immediately while the state becomes `OPENING` or `CLOSING` and the live chart
continues.

### Visual language

Before execution:

- use silver, white, the asset color, arrows, and explicit `LONG`/`SHORT` text;
- do not flood the screen green or red;
- do not add card rotation, confetti, or celebratory effects.

After execution:

- green and red remain reserved for financial outcomes;
- opening and closing use neutral execution states;
- liquidation and stop events use their existing risk semantics.

## Initial Motion Parameters

These values are starting points for device testing, not permanent constants:

| Parameter | Initial value |
| --- | ---: |
| Axis-lock slop | 10-14px |
| Horizontal commit distance | 25-30% viewport width |
| Horizontal velocity commit | 700-900px/s |
| Horizontal settle | 240-340ms |
| Vertical arm distance | 90-120px |
| Visible vertical travel cap | 60-90px |
| Armed haptic | One light impact |
| Disarm haptic | One subtle selection |

The final thresholds should be normalized by viewport size and tested on iPhone
11 through current Pro Max sizes.

## Implementation Direction

The current PWA can implement this with Pointer Events, CSS transforms, and a
small velocity tracker. A new animation framework is not required initially.

During an active drag:

- update transforms through `requestAnimationFrame`;
- avoid React state writes on every pointer move;
- set CSS custom properties or mutate a dedicated motion layer;
- keep the chart's data and y-domain unchanged;
- pause unrelated chart-transition animations;
- use compositor-friendly `transform` and `opacity`.

On release:

- project the endpoint from recent pointer samples;
- animate to the committed page or back to zero with an interruptible,
  critically damped spring;
- allow a new pointer-down to take control of an in-progress animation.

The adjacent market charts should be pre-mounted from the shared backend feed.
Changing market must not start from an empty client state.

Respect `prefers-reduced-motion` by shortening transitions, removing elastic
overshoot, and keeping all actions available through buttons.

## Acceptance Criteria

- The content visibly responds within the first animation frame of a drag.
- Horizontal navigation never presents a blank or stale chart frame.
- A canceled gesture never opens, closes, or changes market.
- Exactly one economic command is created per armed release.
- Double tap remains reserved for `90s` / `1H` chart context.
- Buttons, navigation, settings, and chart controls do not start trade gestures.
- The action can be canceled after crossing the threshold by dragging back.
- A position command is submitted before the reset animation finishes.
- Gesture animation never changes historical prices, peaks, or chart scale.
- The interaction remains smooth at 60fps on supported iPhones.

## Sources

- [Apple Human Interface Guidelines: Gestures](https://developer.apple.com/design/human-interface-guidelines/gestures/)
- [Apple WWDC: Designing Fluid Interfaces](https://developer.apple.com/videos/play/wwdc2018/803/)
- [Apple Human Interface Guidelines: Playing haptics](https://developer.apple.com/design/human-interface-guidelines/playing-haptics)
- [Android MotionLayout: OnSwipe](https://developer.android.com/training/constraint-layout/motionlayout/ref/onswipe)
- [Android: Advanced gesture animation](https://developer.android.com/develop/ui/compose/animation/advanced)
- [YouTube Shorts feed navigation](https://support.google.com/youtube/thread/102762882/shorts-beta-u-s-expansion-important-updates-for-shorts-creators)
- [Tinder swipe decisions](https://www.help.tinder.com/hc/en-us/articles/115005246123-Likes)
