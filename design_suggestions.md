# Overall: yes, I like what you are building

The current product screens are **more compelling than the older black-and-white mockups** because they feel like an actual product rather than a generic crypto concept.

The current version already has a recognizable core:

* one market dominating the screen;
* a large, alive chart;
* a simple Pulse → TICK → Me structure;
* presets applied to each gesture;
* net results and execution state;
* a volatility feed rather than an exchange pair list.

That is aligned with the real product thesis: the scanner finds the market moment, the trade screen compresses the decision, and the user watches net PnL rather than a terminal full of controls.

My preferred combination is:

> **Keep your current information architecture, borrow the designers’ visual restraint, make orange the brand accent, let charts have asset personality, and reserve green/red almost exclusively for financial outcomes.**

The older designer mock has cleaner spacing and restraint, but it also feels more generic: leaderboards, avatars, five navigation items, social profiles, and a standard dark crypto-dashboard aesthetic. Your current three-screen structure—Pulse, TICK, Me—is much closer to the differentiated product described in the build spec.

## The desired feeling

The design should consistently communicate:

> **Fast, not frantic.**
> **Intense, not noisy.**
> **Retail-clear, not childish.**
> **Premium, not institutional.**
> **Market energy, not casino energy.**

You are around **75% toward a compelling product direction** and around **55–60% toward a finished retail interface**. The foundation is good. The polishing work is mostly about hierarchy, semantic color, spacing, terminology, and designing every execution state intentionally.

---

# The color direction

Your black/white/orange idea is stronger than making mint the main brand color.

Use a restrained base:

| Role                     | Suggested treatment                  |
| ------------------------ | ------------------------------------ |
| App background           | Near-black, slightly warm or neutral |
| Raised surfaces          | Two subtle graphite levels           |
| Primary text             | Warm white, not pure white           |
| Secondary text           | Muted gray-green                     |
| Brand/selection          | Orange                               |
| Profit                   | Green                                |
| Loss                     | Red                                  |
| Warning/near-liquidation | Red or amber, with text/icon         |
| Disabled/watch state     | Neutral gray                         |
| Chart identity           | Fixed color by asset or asset class  |

An example palette—not a rigid requirement:

```text
Background        #070A0A
Surface 1         #0E1313
Surface 2         #141A19
Border            #27302E
Primary text      #F5F2EA
Secondary text    #929B97
Brand orange      #FF9C32
Profit green      #32D5A1
Loss red          #FF6175
```

## Color semantics must be disciplined

At the moment, green is being used for the trading balance, long direction, positive results, toggles, and general emphasis. Red is being used for negative movement, short direction, leverage, chart identity, and losses.

That creates semantic collisions.

Use these rules:

```text
Orange:
brand, selected controls, hot opportunity, primary emphasis

Green/red:
PnL and financial outcome

Asset colors:
chart identity only

Gray:
inactive, waiting, secondary information
```

A profitable short should not contain a red `DOWN` chip next to a green profit if red already means loss. Prefer neutral direction chips:

```text
↓ SHORT       +$4.19
↑ LONG        -$1.84
```

Use icons and words for direction. Let green/red describe the result.

Likewise, a balance is not inherently positive PnL. The `$13.91` balance should probably be warm white, with orange or neutral framing—not bright green.

---

# Trade screen

This is the strongest screen. The giant chart and minimal chrome give the product identity.

It already feels substantially more differentiated than a standard perp terminal. Keep the chart dominant.

## 1. Do not make `500x` the visual identity

In the current header:

```text
ZEC 500x Zcash
```

the red `500x` is almost as prominent as the asset itself.

For an internal demo that gets attention. For retail, it makes the product appear to be principally about extreme leverage rather than volatility discovery.

The build spec already says 500x is internal/demo mode, while external defaults should be materially lower and gated.

Use:

```text
ZEC    Zcash
       [500x · Experimental]
```

or:

```text
ZEC  [500x]
Zcash
```

The leverage chip should be orange or neutral, not red. Red should indicate a loss or immediate risk condition.

At ordinary leverage:

```text
ZEC    [50x]
Zcash
```

should feel calm and normal.

## 2. Show why this market is on screen

The trade screen currently shows price movement, but not the scanner decision.

A user should immediately understand:

```text
Why ZEC?
Is it actually tradeable?
Is movement large enough after costs?
```

Add a compact market-state line:

```text
HOT
MOVE 0.16% · COST 0.12%
```

or:

```text
COST COVERED · +0.04%
```

Do not call it edge. The product is identifying active movement after estimated costs, not predicting direction. That distinction is already correctly specified.

Possible hierarchy:

```text
HOT                         Balance $13.91
ZEC  [50x]  Zcash
$474.237  -0.05%
MOVE .16% · COST .12%
```

The market percentage change and the scanner window are different measurements. Label the time window when useful:

```text
MOVE 0.16% / 90s
```

## 3. Reorder the bottom trade terms

The current row says:

```text
Collateral  $10
Stop loss   $10
Take profit Off
Est. cost   $2.50
```

The most important pre-trade terms are actually:

```text
Amount
Leverage
Exposure
Estimated cost
Liquidation distance
```

A stronger compact row:

```text
AMOUNT       EXPOSURE      EST. COST      LIQ. AWAY
$10          $5,000        $2.50 · 25%    0.16%
```

Then place stop and take-profit in an expandable details sheet or a second compact line:

```text
STOP   $5 est. loss · placed on venue
TP     Off
```

`Stop loss $10` is ambiguous. It could mean:

* a stop price of `$10`;
* a maximum loss of `$10`;
* collateral at risk of `$10`;
* or a stop-loss budget of `$10`.

Use plain language:

```text
Loss limit
Stop budget
Stop price
Estimated loss at stop
```

Only say `Max loss` if the venue genuinely guarantees that limit. The build spec explicitly calls for visible ticket, leverage, exposure, costs, collateral at risk, and liquidation terms before the gesture.

The `$2.50` estimated cost on `$10` collateral is especially material. Do not make the user mentally calculate it:

```text
Est. cost $2.50 · 25% of amount
```

## 4. The chart should have asset identity, not outcome semantics

Different chart colors are a good idea. They make swiping across markets feel like entering a different room.

For example:

```text
BTC       orange
ETH       blue
SOL       cyan
ZEC       coral
HYPE      violet
Gold      yellow
FX        lime or cool white
```

But keep the chart color stable for that asset. Do not make the entire chart green when price rises and red when it falls. That can subtly push users toward a direction and creates confusion with PnL.

Use:

```text
Chart color        asset identity
Header move        green/red
Position PnL       green/red
Stop/liquidation   risk styling
```

The chart may remain coral for ZEC regardless of whether the latest movement is up or down.

## 5. Design four distinct trade-screen modes

Do not treat the interface as one screen with different labels pasted on top.

### Flat

```text
Market state
Chart
Visible terms
Subtle swipe affordance
```

### Opening

```text
LONG 50x
Opening…
Quote accepted
Waiting for venue
```

Freeze conflicting gestures and keep the chart alive.

### Live

The visual priority should change:

```text
EST. NET IF CLOSED NOW
+$1.42

Entry          $474.10
Stop away       0.09%
Liq away        0.15%

[Close]
```

Net PnL becomes the focal number. The chart remains large but is no longer the only hero.

### Closing

```text
Closing…
Position remains exposed
```

After authoritative close:

```text
Closed
Finalizing result…
```

Then:

```text
Net result -$1.17
```

This honest state progression is part of the product, not merely backend plumbing.

## 6. Teach gestures without clutter

The older designer’s “How it works” screen is one of the more useful parts of that concept. Keep the idea, but rewrite the tone.

Avoid:

```text
Just swipe to trade. Catch the tick!
```

Prefer:

```text
Swipe up to go long
Swipe down to go short
Swipe the same direction again to close
Your active preset applies automatically
```

On the first several sessions, show very subtle in-context cues:

```text
↑ LONG                         SHORT ↓
```

They can disappear after the user demonstrates understanding.

The normal flow can remain one deliberate gesture because the exact terms are already visible, which is consistent with the current spec.

---

# Pulse

The screen is visually clean, but currently it reads more like a standard ranked market list than TICK’s moat.

## What works

* `Pulse` is a strong name.
* “Markets moving now” is clear.
* Seven rows fit comfortably.
* The screen is calm and scan-friendly.
* The three-tab navigation is much better than the five-tab designer concept.

## What needs to change

### The bars need a defined meaning

Currently each market uses a different bar color and length, but the user cannot know whether the bar means:

* percent move;
* volatility;
* scanner score;
* cost coverage;
* or volume.

Use one consistent scanner scale:

```text
Gray      Watching
White     Active
Orange    Hot after costs
```

Asset color can appear as a tiny dot, symbol accent, or sparkline. The actual score bar should use a consistent semantic scale.

### Show the after-cost reason

A row could look like:

```text
01  ZEC  Zcash                      $475.27
    HOT · MOVE .16 · COST .12       -0.01%
    ━━━━━━━━━━━━━━━
```

Or a more minimal version:

```text
ZEC                    $475.27
+0.04% after cost      -0.01%
```

Use `activity surplus`, `after costs`, or `cost covered`—not `edge`.

The dashboard is supposed to rank tradeability rather than raw movement, and the user should be able to distinguish a real active-after-cost opportunity from an ordinary moving market.

### Change `7 live`

`Live` can mean the feed connection is healthy.

Use:

```text
7 active
7 moving
4 cost-covered
2 hot now
```

This communicates scanner state rather than network state.

### Give the top opportunity more character

The screen could have one slightly larger top card:

```text
HOT NOW

ZEC
MOVE .16% · COST .12%
+0.04% activity surplus

[small sparkline]
```

Then show the remaining markets as compact ranked rows. That makes Pulse feel like a discovery product rather than a watchlist.

---

# Me

The screen contains the correct information, but it is visually the most crowded.

## 1. Make the balance neutral

The bright green balance card makes `$13.91` look like profit.

Use:

```text
Available to trade
$13.91
```

in warm white, with a subtle orange top border or accent. Green should appear only when a balance has increased or a result is positive.

Deposit and Withdraw are good primary actions. Keep them side by side.

The wallet address can move into a details row:

```text
Wallet & network ›
```

Most retail users do not need to see a truncated address permanently.

## 2. Collapse TICK config into a preset summary

The current grid makes Me look like an order ticket:

```text
4 collateral buttons
4 leverage buttons
4 stop buttons
2 toggles
```

Instead, show one active preset:

```text
ACTIVE PRESET

Fast
$10 amount · 50x · $5 stop
Take profit off

[Edit preset]
```

Tapping it opens a full-screen or bottom-sheet editor containing the grids.

That preserves the core preset behavior without making the main account page feel technical.

For 500x:

```text
500x
Experimental
Internal accounts only
```

should be explicitly differentiated.

## 3. Remove the word `Venue` from normal settings

The product is supposed to hide venue complexity. Do not show:

```text
Venue stop loss
Venue take profit
```

Use:

```text
Stop loss
Take profit
```

Then show a small trust detail:

```text
Placed directly on venue
```

or an information icon explaining that the stop remains active even if the TICK app disconnects.

Venue abstraction is a core product decision; venue-specific concepts should not leak into ordinary consumer surfaces.

## 4. Reconsider `Wins`

`Net PnL`, `Trades`, and `Wins` can create an unnecessarily game-like performance hierarchy.

A more informative set:

```text
Net result
Trades
Win rate
```

or:

```text
Net result
Avg. cost
Trades
```

Win count by itself is not especially meaningful. A trader can win many tiny trades and lose one large trade.

## 5. Clean up history semantics

The history layout is structurally good, but change:

```text
UP / DOWN
```

to:

```text
LONG / SHORT
```

or:

```text
↑ LONG
↓ SHORT
```

Use neutral chips, not green/red direction chips.

Spell out:

```text
Liquidated
```

rather than `Liq` in retail-facing filters.

Replace the contradictory:

```text
Settling
closed
```

with:

```text
Closed
Finalizing result
```

or:

```text
Reconciling
```

Rows should open into a detail sheet:

```text
Entry
Exit
Gross movement
Fees
Price impact
Net result
Transaction
Execution time
```

That reinforces trust and explains why a visually successful trade might still lose after costs.

---

# Navigation

`Pulse / TICK / Me` is one of the strongest decisions in the current build.

Keep it.

The present navigation pill is slightly too tall and heavy. Reduce its visual weight by around 15–20%:

* smaller vertical padding;
* tighter icon-label spacing;
* slightly narrower selected capsule;
* brighter inactive labels;
* less visible outer border.

The selected center tab can use the TICK symbol plus white text. Orange does not need to fill the whole navigation state; a small orange tick or underline may be enough.

The older concept’s five-tab navigation, leaderboard, home tab, and social profile weaken the product. Do not bring those back into V1.

---

# Logo

The logo idea is good.

The vertical stroke cutting through the wordmark can represent:

* a price tick;
* a candlestick;
* a timing marker;
* the moment of execution.

That gives it a relevant concept without drawing a cliché chart arrow.

## What to refine

### Use two lockups

**Wordmark**

```text
TICK
```

for splash, marketing, and headers.

**App/navigation icon**

A standalone vertical tick/candle symbol that remains readable at 16–24 pixels.

The current wordmark will not necessarily reduce cleanly into a navigation icon.

### Use orange for the tick

Instead of mint:

```text
T  [orange vertical tick]  CK
```

with the letters in warm white.

The mint version looks clean but feels like a generic fintech palette. Orange gives TICK more intensity and connects to the current product.

### Fix optical alignment

The vertical line currently appears to extend far above and below the letter area. Refine:

* exact height;
* relationship with the `I`;
* spacing between `T`, stroke, and `C`;
* thickness at small sizes;
* whether it reads as `T|CK` instead of `TICK`.

Test the mark at:

```text
16px
24px
40px
80px
app-icon size
```

### Brand-motion opportunity

On launch, the vertical tick could:

1. appear as a thin line;
2. pulse once;
3. expand into the full wordmark;
4. transition into the live chart cursor.

That creates a very ownable motion identity without being loud.

---

# What to take from the designers’ black-and-white concept

Take:

* restraint;
* confident white typography;
* large negative space;
* simple rounded cards;
* minimal navigation;
* the onboarding gesture illustrations;
* the wordmark concept.

Do not take:

* leaderboard as a central destination;
* fake social profiles;
* five navigation tabs;
* prominent venue labels;
* generic “trade this move” cards;
* large social PnL numbers;
* kiwi/avatar identity as core brand;
* mint as the only accent;
* “coming soon” placeholder surfaces in the main IA.

The older screens look polished, but they belong to a more generic social-crypto product. Your current structure is much more ownable.

---

# Retail design rules for the whole app

Every screen should answer one primary question.

```text
Pulse:
What is worth watching now?

TICK:
Can I act, what are the terms, and what is happening to my position?

Me:
What is my balance, preset, and history?
```

Use an 8-point spacing system and reduce the number of outlined rectangles. Right now, many controls, cards, filters, balances, and navigation items all have visible borders. Let spacing and surface tone create hierarchy; use outlines primarily for:

* selected controls;
* focused fields;
* risk warnings;
* actionable cards.

Keep at least 44×44-point touch targets.

Use tabular numerals for:

* price;
* balance;
* exposure;
* PnL;
* percentages.

Never use color as the only indicator. Pair it with:

* `+` and `−`;
* arrows;
* text labels;
* icons;
* line style.

The design should include explicit states for:

```text
Watching
Hot
Stale
Market closed
Opening
Open long
Open short
Closing
Closed, finalizing
Failed
Unknown/recovery
Liquidated
Stop hit
```

The app must not shift layout dramatically as it moves between these states. Important values should remain in stable positions.

---

# Copy this brief to the design or UI agent

```text
Redesign and polish the current TICK product. Do not replace its information
architecture with the older social-trading mockup.

Keep the three primary tabs:

1. Pulse
2. TICK
3. Me

Brand principles:

- fast, not frantic
- intense, not noisy
- premium, not institutional
- retail-clear, not childish
- market energy, not casino energy

Visual system:

- near-black neutral background
- warm-white primary typography
- graphite surfaces with minimal borders
- orange is the only primary brand/selection accent
- green and red are reserved primarily for financial PnL/outcomes
- long/short direction must also use text/arrows, not color alone
- balances should be neutral, not green
- each asset may have a consistent chart identity color
- asset chart color must not change based only on price direction
- use tabular numerals for all prices, PnL, percentages, and balances
- use an 8px spacing grid and 44px minimum touch targets
- reduce decorative outlines; use spacing and tonal elevation

TICK trade screen:

- preserve the chart-dominant layout
- show market, asset name, current price, movement, and a small leverage chip
- do not make 500x the primary visual identity
- 500x must appear as Experimental/Internal when present
- add a clear scanner state: Watching, Cost covered, or Hot
- show MOVE and COST or a plain-language “after costs” measure
- do not use the term edge
- before opening, prioritize four terms:
  Amount, Exposure, Estimated cost, Liquidation distance
- show estimated cost in dollars and as a percentage of collateral
- stop-loss copy must distinguish stop price, loss budget, and estimated loss
- include subtle first-use swipe guidance
- design separate layouts for:
  Flat, Opening, Live long, Live short, Closing, Closed-finalizing,
  Stop hit, Liquidated, Failed, and Recovery
- during a live position, “Est. net if closed now” is the primary financial number
- keep a visible Close button in addition to the same-direction closing gesture
- after authoritative close, stop live exposure immediately and show
  “Closed · finalizing result” until reconciliation completes

Pulse:

- rank markets by tradeability after costs, not only raw percentage movement
- score bars must use one consistent semantic scale
- asset color may appear as a small identity accent or sparkline
- label the scanner metric clearly
- replace “7 live” with “7 active”, “4 cost-covered”, or an equivalent state
- consider one larger Hot Now card followed by compact ranked rows
- show enough information to explain why a market is ranked:
  MOVE, COST, activity surplus, or a clear plain-language equivalent
- do not add leaderboards, avatars, or social PnL to V1

Me:

- show available trading balance neutrally
- keep Deposit and Withdraw prominent
- move wallet address/network details behind a secondary row
- replace the full settings grid on the main page with an Active Preset summary
- open a separate editor for collateral, leverage, stop, and take profit
- remove “Venue” from ordinary stop-loss and take-profit labels
- optionally show “Placed directly on venue” as a trust detail
- use LONG/SHORT rather than UP/DOWN in history
- use neutral direction chips and green/red only for result PnL
- spell out Liquidated rather than Liq
- replace “Settling / closed” with “Closed · finalizing result”
- allow each history row to open an execution/cost breakdown

Navigation:

- retain Pulse / TICK / Me
- make the bottom navigation approximately 15–20% more compact
- create a standalone TICK icon based on the vertical tick/candle motif
- keep inactive navigation legible but subdued

Logo:

- refine the current TICK wordmark
- warm-white letters with an orange vertical tick
- create separate wordmark and compact app-icon versions
- verify legibility at 16px, 24px, 40px, and app-icon scale
- make sure the vertical stroke does not cause the word to read as T|CK
- provide a simple launch animation concept where the tick becomes the
  wordmark or chart cursor

Deliver:

- design tokens for color, type, spacing, radius, and motion
- reusable component definitions
- complete mockups for all execution states
- iPhone-sized responsive layouts
- motion/haptic notes
- accessibility annotations
- a list of removed or renamed terminology
```

# Final call

The current product direction is the right one.

The actual TICK screens are more valuable than the older concept because they express the unique loop: **discover movement, enter with a preset, watch net PnL, close, move on**. The older concept can help the team simplify and polish, but it should not replace the current product architecture.

The most important visual decision is:

> **Black and warm white establish trust. Orange makes TICK recognizable. Asset colors make markets feel alive. Green and red tell the truth about money.**

That combination can feel both retail-friendly and highly distinctive.
