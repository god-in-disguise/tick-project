# I agree: the structure is getting better, but the styling drifted too far toward “exchange app”

The current version feels more Binance-like because **orange is being used as decoration everywhere**, not because the information architecture is wrong.

Keep the present product structure:

```text
Pulse → discover
TICK  → trade
Me    → manage
```

That is much stronger and more original than the old leaderboard/social mockups. The source-of-truth spec also treats mobile as the differentiated product and defines Trade, the volatility dashboard, and Me as the three core surfaces.

The right move is:

> **Keep the current UX. Move the visual language back toward the designers’ monochrome mockups.**

I would reduce the orange by about **60–70%**, reduce card chrome by about **30%**, neutralize the green/brown tint, and keep the chart as the expressive part of the product.

---

# Why it currently feels like Binance

The exchange-app feeling comes from the combination of:

* orange labels on nearly every active Pulse row;
* orange progress bars repeated five times;
* orange leverage;
* orange selected navigation;
* warm brown/orange balance panels;
* dark green-tinted backgrounds;
* many rounded rectangular cards;
* dense financial values arranged like a terminal;
* a heavily tinted red chart background.

Orange itself is not the problem. The problem is that it appears at every level of hierarchy.

The eye currently sees:

```text
Orange = brand
Orange = scanner state
Orange = progress
Orange = leverage
Orange = navigation
Orange = card emphasis
Orange = account balance framing
```

Orange should mean one thing:

> **This is TICK’s active or selected moment.**

---

# Target visual language

Use approximately this distribution:

```text
70%  black / near-black
25%  white / silver / graphite
 5%  orange and semantic colors
```

## Suggested palette

```text
Canvas                #050606
Primary surface       #0C0E0F
Raised surface        #111314
Subtle surface        #17191A
Border                rgba(255,255,255,0.07)

Primary white         #F3F3EF
Silver                #A7ACA8
Secondary silver      #7C827F
Disabled              #555B58

TICK orange           #FF922B
Profit                #2FCF9A
Loss                  #FF5E73
```

Avoid:

* green-black page backgrounds;
* brown or amber card backgrounds;
* visible gradients on ordinary cards;
* orange borders around large sections;
* pure white on every text level.

Use warm white for primary content and silver for everything secondary.

## Color responsibilities

| Color       | Responsibility                                                        |
| ----------- | --------------------------------------------------------------------- |
| Orange      | TICK brand, active control, selected state, one important opportunity |
| Green/red   | Financial outcome and price direction                                 |
| Asset color | Chart identity                                                        |
| Silver      | Navigation, labels, scanner meters, secondary information             |
| Graphite    | Surfaces and separators                                               |

The chart can remain different for each asset, but avoid pure PnL red and green for chart identity.

For example:

```text
BTC       muted gold
ETH       electric blue
SOL       cyan
HYPE      violet
ZEC       silver-lilac
BNB       muted yellow
FX        pale teal
```

HYPE should probably not use a red/coral chart. That makes its chart look like an ongoing loss even before a position exists.

---

# Pulse

The information is much better now. “Cost-covered” and surplus are closer to the real product than a generic market mover list. The spec specifically says Pulse should rank by tradeability after costs and explain whether TICK found a real opportunity or the market is merely being watched.

Visually, however, there is too much orange.

## Change this

Current:

```text
VOLATILITY SCANNER          5 cost-covered

HYPE
SURPLUS +0.062%             orange bar

SOL
SURPLUS +0.027%             orange bar

ZEC
SURPLUS +0.018%             orange bar
```

Recommended:

```text
VOLATILITY SCANNER          5 cost-covered

HYPE
AFTER COST +0.062%          silver meter with orange endpoint

SOL
AFTER COST +0.027%          silver meter

ZEC
AFTER COST +0.018%          silver meter
```

Or:

```text
HYPE
COST COVERED · +0.062%
```

`SURPLUS` is accurate internally but slightly technical for retail. `AFTER COST` or `COST COVERED` communicates the meaning faster. The spec defines this value as movement remaining above estimated cost and explicitly says it is not directional edge.

## Orange restraint on Pulse

Use orange in only one or two places:

* the small `VOLATILITY SCANNER` eyebrow; and
* the first-ranked opportunity’s meter or state.

Everything else can use white and silver.

For example:

```text
01  HYPE                       55.58
    AFTER COST +0.062%        -0.06%
    ━━━━━━━━━━━━━━━
```

The meter fill could be silver for all rows, with the top-ranked row using orange.

Keep the small asset-colored dots. They provide market identity without overwhelming the interface.

## Reduce the “stack of exchange cards” feeling

A more premium treatment would be one large list surface with dividers:

```text
┌─────────────────────────────────┐
│ 01  HYPE                       │
├─────────────────────────────────┤
│ 02  SOL                        │
├─────────────────────────────────┤
│ 03  ZEC                        │
└─────────────────────────────────┘
```

Rather than eight individually floating cards.

You can still retain a slightly highlighted top row.

---

# TICK trade screen

The chart-dominant layout is right. This is the most distinctive screen in the app, and the build spec correctly requires one market, a live chart, current price, balance, PnL, market state, and compact execution terms without turning it into an order form.

The problems are primarily the header, balance, chart tint, and orange hierarchy.

## 1. Fix the asset header

Current:

```text
HYPE 500x Hyperliquid
55.581 -0.16%
```

There are three different concepts competing on one baseline:

* symbol;
* leverage;
* full asset name.

Use a two-level layout:

```text
HYPE   [500×]                       AVAILABLE
Hyperliquid                             $0.00

55.581   -0.16%
```

Or:

```text
HYPE   [500×]                       AVAILABLE
Hyperliquid                             $0.00
55.581   -0.16%
```

Suggested sizing:

```text
Symbol             34–36px / bold
Leverage chip      13–14px / semibold
Asset name         14px / silver
Price              22–24px / tabular
Move               15px / tabular
```

The asset name should be a subtitle, not part of the main title line.

Use:

```text
numberOfLines={1}
ellipsizeMode="tail"
```

for long market names.

## 2. Make leverage neutral

The large orange `500x` dominates the asset.

Use a silver or graphite leverage chip:

```text
[500×]
```

with white text and a subtle border.

Because 500x is intended as internal/demo mode rather than the ordinary external default, an internal build can show:

```text
500× · EXPERIMENTAL
```

in a small amber treatment. The product spec already distinguishes internal 500x from lower external leverage defaults.

Do not let extreme leverage become the logo of the product.

## 3. Remove the balance pill

The current brown/olive balance card feels detached from the rest of the screen and competes with the market title.

Make the balance typographic:

```text
AVAILABLE
$13.91
```

No large container. No brown background. No green number.

A balance is not profit, so it should be warm white.

When the balance is zero:

```text
AVAILABLE
$0.00
Add funds
```

`Add funds` can be the orange element.

When funded:

```text
AVAILABLE
$13.91
```

No extra action is needed in the header.

## 4. Reduce chart tint dramatically

The current HYPE screen has a dark red wash over almost the entire chart. That is a major contributor to the exchange-app feeling.

Recommended:

```text
Chart background       neutral black
Chart line             asset color at 85–100%
Glow                   asset color at 8–12%
Area fill              asset color at 2–5%
Grid                    white at 4–6%
Axis labels            silver at 45–55%
```

The chart should feel colorful because of the line, not because the whole viewport is painted red.

For HYPE, switch the line from coral/red to violet or electric purple. Red should remain strongly associated with loss or negative movement.

## 5. The execution row is good, but make it quieter

Current:

```text
Amount    Leverage    Exposure     Est. cost
$10       500x        $5,000       $2.50
                                      25.0% of amount
```

The information hierarchy is correct.

Use silver labels, white values, and no colored background.

I would slightly increase the visibility of the cost percentage:

```text
EST. COST
$2.50
25% of amount
```

That is a material term and should not look like legal fine print.

When cost is unusually large, use a small amber warning icon—not a full orange panel.

---

# Me

The information structure is much better than before:

* neutral account statistics;
* available balance;
* deposit/withdraw;
* active preset;
* history;
* settings.

The `Active preset` simplification is especially good.

## 1. Remove the orange/brown balance-card treatment

Use a neutral surface:

```text
AVAILABLE TO TRADE
$13.91
```

with a subtle silver border or no border.

For zero balance:

* make `Deposit` the single orange primary action;
* keep `Withdraw` gray or disabled.

For a funded balance:

* both Deposit and Withdraw can be monochrome outlined controls.

## 2. Keep the active preset card

This is a strong retail simplification:

```text
AMOUNT      LEVERAGE      LOSS LIMIT
$10         500×          $10
```

Keep it.

But make 500x look like an exceptional setting:

```text
500×
Experimental
```

or show a small warning state inside the preset editor, not throughout the whole app.

## 3. Fix the content being hidden by navigation

In the screenshot, the Settings area is being obscured by the bottom navigation. This is a layout implementation problem, not a visual preference.

`Me` must be a scroll view whose bottom content padding includes:

```text
tab bar height
+ iPhone bottom safe area
+ 20–24px breathing space
```

The user must be able to scroll the final Settings row completely above the navigation.

---

# Bottom navigation

You are correct: it is too high.

In these screenshots, the tab bar appears roughly **one half to one full tab-bar height too far above the home indicator**.

It should sit:

```text
8px above the top of the bottom safe area
```

not 50–80px above it.

## Visual treatment

Current navigation has:

* a large outer capsule;
* a large selected inner capsule;
* tinted dark-green surfaces;
* relatively heavy height.

That contributes to the exchange feel.

Recommended:

```text
Height             58–62px
Horizontal inset   20px
Bottom             safe-area inset + 8px
Background         #0C0E0F
Border             rgba(255,255,255,0.08)
Radius             29–31px
```

Selected tab:

```text
Icon                orange
Label               warm white
Background          transparent or rgba(255,255,255,0.04)
```

Inactive tab:

```text
Icon and label      muted silver
```

Do not use a large bright selected capsule. A subtle tonal fill is enough.

The active TICK icon being orange works. You do not also need orange text and a prominent selected panel.

---

# Correct iPhone safe-area implementation

The likely bug is that the app is applying the bottom safe area more than once:

```text
SafeAreaView bottom padding
+ tab bar bottom offset
+ screen bottom padding
```

That pushes the navigation too high.

## For a PWA

Include:

```html
<meta
  name="viewport"
  content="width=device-width, initial-scale=1, viewport-fit=cover"
/>
```

Use:

```css
:root {
  --tab-bar-height: 60px;
}

html,
body {
  margin: 0;
  background: #050606;
}

.app-shell {
  min-height: 100dvh;
  padding-top: env(safe-area-inset-top);
}

.page-content {
  min-height: 100%;
  padding-bottom: calc(
    var(--tab-bar-height) +
    env(safe-area-inset-bottom) +
    24px
  );
}

.bottom-tabs {
  position: fixed;
  left: 20px;
  right: 20px;
  bottom: calc(env(safe-area-inset-bottom) + 8px);
  height: var(--tab-bar-height);
  z-index: 100;
}
```

Use `100dvh`, not `100vh`, so iPhone browser and standalone-PWA viewport changes do not distort the layout.

Do not also give `.app-shell` a bottom safe-area padding when the tab bar already consumes it.

## For Expo / React Native

At the root:

```tsx
<SafeAreaProvider>
  <App />
</SafeAreaProvider>
```

For a screen with an absolute tab bar:

```tsx
const insets = useSafeAreaInsets();
const TAB_HEIGHT = 60;

return (
  <View style={{ flex: 1, backgroundColor: colors.background }}>
    <ScrollView
      contentContainerStyle={{
        paddingTop: 12,
        paddingBottom: TAB_HEIGHT + insets.bottom + 24,
      }}
    >
      {content}
    </ScrollView>

    <View
      style={{
        position: "absolute",
        left: 20,
        right: 20,
        bottom: insets.bottom + 8,
        height: TAB_HEIGHT,
      }}
    >
      {tabs}
    </View>
  </View>
);
```

If using `SafeAreaView`, apply only the edges you need:

```tsx
<SafeAreaView edges={["top", "left", "right"]}>
```

Do **not** apply the bottom edge there and then apply `insets.bottom` again to the tab bar.

## Test these viewport sizes

```text
375 × 667   small iPhone / SE
375 × 812   compact Face ID
390 × 844   standard modern iPhone
393 × 852   Pro
430 × 932   Pro Max / Plus
```

Check:

* tab bar is 8px above the safe area;
* the final Me row scrolls above the bar;
* no content sits beneath the home indicator;
* headers do not collide with the Dynamic Island;
* no hardcoded status-bar height exists;
* chart height is calculated from remaining space rather than a fixed screen coordinate.

---

# Better trade-header structure for the coding agent

Do not absolutely position the asset name and balance independently.

Use a flex grid:

```tsx
<View style={styles.tradeHeader}>
  <View style={styles.assetBlock}>
    <View style={styles.symbolRow}>
      <Text style={styles.symbol}>HYPE</Text>
      <View style={styles.leverageChip}>
        <Text style={styles.leverageText}>500×</Text>
      </View>
    </View>

    <Text
      style={styles.assetName}
      numberOfLines={1}
      ellipsizeMode="tail"
    >
      Hyperliquid
    </Text>

    <View style={styles.priceRow}>
      <Text style={styles.price}>55.581</Text>
      <Text style={styles.negative}>−0.16%</Text>
    </View>
  </View>

  <View style={styles.balanceBlock}>
    <Text style={styles.balanceLabel}>AVAILABLE</Text>
    <Text style={styles.balanceValue}>$0.00</Text>
    <Text style={styles.addFunds}>Add funds</Text>
  </View>
</View>
```

Suggested layout:

```tsx
tradeHeader: {
  flexDirection: "row",
  alignItems: "flex-start",
  justifyContent: "space-between",
  paddingHorizontal: 20,
  paddingTop: 14,
  paddingBottom: 16,
},

assetBlock: {
  flex: 1,
  minWidth: 0,
  paddingRight: 16,
},

balanceBlock: {
  width: 105,
  alignItems: "flex-end",
},
```

This will remain stable when the asset name is longer, when the balance has more digits, and across different iPhone widths.

---

# Copy this to the design/coding agent

```text
Perform a visual-restraint and iPhone-layout pass on the current TICK UI.

Do not change the product information architecture:

- Pulse
- TICK
- Me

The current UX structure is correct. The problem is that the visual styling
has become too similar to a conventional crypto exchange.

Target feeling:

- black and silver
- premium retail
- fast but calm
- minimal but not empty
- high-energy chart, restrained interface
- no casino styling
- no generic Binance-style orange everywhere

COLOR SYSTEM

Use:

Background:          #050606
Surface 1:           #0C0E0F
Surface 2:           #111314
Surface 3:           #17191A
Border:              rgba(255,255,255,0.07)
Primary text:        #F3F3EF
Silver text:         #A7ACA8
Muted text:          #6E7571
Brand orange:        #FF922B
Profit:              #2FCF9A
Loss:                #FF5E73

Approximately 70% black, 25% white/silver, and no more than 5% orange or
semantic color.

Orange is reserved for:

- primary TICK identity
- selected/active control
- one important scanner opportunity
- critical attention state

Do not use orange simultaneously for all labels, meters, leverage, cards,
navigation and balances.

Green and red are reserved primarily for financial outcomes and price
direction. Balances are neutral white, not green.

CHARTS

Every asset may have a stable chart identity color.

Do not use pure profit green or loss red as ordinary chart identity.
Use colors such as blue, cyan, violet, muted gold and silver-lilac.

Keep chart background neutral black.
Reduce chart area-fill opacity to 2–5%.
Keep chart-line opacity high and glow subtle.
Do not tint the whole chart panel red, green or orange.

PULSE

- Keep current scanner logic and ranked markets.
- Use one consistent silver scanner meter.
- Only the top opportunity may use an orange meter or endpoint.
- Keep small asset-colored identity dots.
- Replace repeated orange “SURPLUS” labels with:
  “AFTER COST +0.062%” or “COST COVERED +0.062%”.
- Keep WAIT rows gray.
- Consider one unified list surface with subtle dividers instead of eight
  visibly separate exchange-style cards.
- “5 cost-covered” may be the single orange status in the header.
- Do not add leaderboards or social profiles.

TICK HEADER

Replace:

HYPE 500x Hyperliquid

with a structured hierarchy:

HYPE [500×]                     AVAILABLE
Hyperliquid                         $0.00
55.581 −0.16%                    Add funds

- Symbol: 34–36px bold.
- Leverage: small neutral graphite/silver chip.
- Asset name: 14px silver subtitle on its own line.
- Price: 22–24px tabular numerals.
- Balance: right-aligned typography, no brown/green pill.
- Balance amount is white.
- When balance is zero, show a small orange “Add funds” action.
- Use flex layout, not absolute coordinates.
- Long names must truncate safely.
- 500× should be labeled Experimental/Internal where applicable.

TRADE TERMS

Keep:

Amount
Leverage
Exposure
Estimated cost

Use silver labels and white values.
Show cost in both dollars and percentage of the amount.
Do not hide a material percentage in tiny text.
Avoid colored row backgrounds.

ME

- Remove orange/brown tint and orange border from the balance card.
- Use a neutral black/graphite surface.
- Make Deposit orange only when the balance is zero.
- Keep Withdraw muted or disabled when unavailable.
- Retain the Active preset summary.
- Keep detailed preset controls in a separate editor.
- Ensure History and Settings can scroll fully above the tab bar.
- Do not let the navigation cover the Network row.

BOTTOM NAVIGATION

- Height: 58–62px.
- Left/right: 20px.
- Bottom: safe-area-inset-bottom + 8px.
- Neutral black background.
- Thin silver border.
- Active icon may be orange.
- Active text is white.
- Inactive icons/text are muted silver.
- Remove or greatly reduce the large selected inner capsule.
- Lower the current navigation by roughly 40–60 points on the shown iPhone
  layout.

SAFE AREA

PWA:

- set viewport-fit=cover
- use min-height: 100dvh
- position the nav at:
  bottom: calc(env(safe-area-inset-bottom) + 8px)
- page content padding-bottom must equal:
  tab height + safe-area bottom + 24px
- do not apply the bottom safe area twice

React Native:

- use SafeAreaProvider and useSafeAreaInsets
- absolute tab bar:
  bottom: insets.bottom + 8
- if SafeAreaView is used around the screen, exclude its bottom edge
- ScrollView content paddingBottom:
  TAB_HEIGHT + insets.bottom + 24
- do not hardcode status-bar or Dynamic Island heights

Test at:

375×667
375×812
390×844
393×852
430×932

TYPOGRAPHY

Use the system/SF font.
Use tabular numerals for all money, price and percentage values.
Primary headings are warm white.
Secondary labels are silver.
Avoid all-uppercase except small 10–11px eyebrows and field labels.

GENERAL

- no ordinary gradients
- no large colored card borders
- no more than one strong orange focal point per section
- fewer floating cards
- more spacing and subtle dividers
- preserve the current three-screen product
- borrow the monochrome atmosphere from the older designer mockups,
  not their leaderboard/social architecture
```

# Final direction

The old designer mockups have the **better brand mood**.

The current implementation has the **better product architecture**.

The finished product should combine them:

> **Current Pulse/TICK/Me experience, styled with the old mockups’ black, silver, typography, restraint and negative space—with orange used like punctuation, not wallpaper.**

The simplest instruction to the team is:

> **Do not redesign TICK. Desaturate it. Lower the navigation. Simplify the header. Remove 70% of the orange. Let the chart carry the energy.**
