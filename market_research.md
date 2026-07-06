# Market Research: Feed-First Mobile Perps CEX

Current as of July 6, 2026.

## Short Verdict

The idea is real. The primitive is not new, but the composition is still open.

Crypto perps are already a massive market. Mobile trading is already proven. Gamified high-leverage perps already exist through products like Rocket Perps. What is still underbuilt is a mobile-first trading product where the main interface is not a dashboard, but a ranked feed of markets moving right now.

The strongest framing:

> A feed-first mobile trading app for high-velocity market moments.

This is not "TikTok for trading" as the full idea. That line is useful for explaining the interaction model, but too shallow for the company. The real company is a trading venue or broker layer that compresses discovery, risk understanding, execution, and cost selection into one mobile loop.

## What Is Actually New

Not new:

- Perpetual futures
- Mobile crypto trading
- High-leverage retail speculation
- Trading leaderboards, competitions, rewards, and copy trading
- Simple long/short interfaces
- Derivatives metrics like funding, OI, liquidations, spread, volume

Newer / less saturated:

- The market feed as the primary trading interface
- The main TICK product and TICK Pro built on the same volatility explorer
- Real execution quality surfaced in retail language
- A phone-native perps terminal that does not feel like a compressed desktop dashboard
- A cross-asset market-moment feed covering crypto, stocks, indices, commodities, and FX when venues support it
- Dynamic leverage selection based on volatility and all-in trading cost
- A CEX path where opportunity discovery is the wedge, not just lower fees or more listings

The key product insight is that most exchanges answer: "Where can I trade?" This product answers: "What is worth looking at right now, and what is the cleanest route to trade it?"

## Market Context

Perps are one of crypto's core products. Recent reporting around Kalshi and Coinbase's 2026 U.S. perpetuals push cited crypto derivatives as roughly 80% of crypto trading volume, with perpetuals volume growing from about $28T in 2023 to more than $90T in 2025.

This matters because the market is no longer a niche casino corner. It is becoming a mainstream derivatives format:

- Offshore CEXs made perps huge.
- Hyperliquid proved that a focused perp venue can become culturally important.
- Kalshi and Coinbase are pushing regulated U.S. access.
- Robinhood is expanding perpetual futures in Europe.
- Traditional exchange owners like ICE are moving toward tokenized and 24/7 derivative products.

The timing is good, but it also means the product must be serious. A toy wrapper over leverage will not be defensible for long.

## Customer Segments

### 1. Retail Action Trader

This user wants fast movement, simple decisions, and a small ticket size. They do not want to study 200 pairs. They want to open the app and see what is alive.

Needs:

- Simple chart
- Clear long/short action
- Small default sizing
- Obvious max loss and liquidation
- Fast feedback
- Streaks, PnL, share cards, rankings

Risk:

- They can churn fast after losses.
- They can attract regulatory and app-store attention if the app feels predatory.
- They need guardrails without killing the energy.

### 2. Mobile Pro Trader

This user already trades perps on Binance, Bybit, OKX, Hyperliquid, or similar venues. They use mobile because crypto is 24/7 and opportunities happen away from the desk.

Needs:

- Funding, OI, volume, spread, liquidity, liquidation risk
- Fast position management
- TP/SL, reduce-only, bracket orders
- Clear mark/index price
- Low-latency execution
- Watchlists and alerts
- No childish UI in TICK Pro

Risk:

- Pros will not tolerate bad fills, fake metrics, hidden fees, or toy controls.
- If TICK Pro is weak, the product stays a novelty.

### 3. Social/Competitive Trader

This user trades partly for status. They care about screenshots, leaderboards, competitions, and public PnL.

Needs:

- Shareable trade results
- Daily/weekly competitions
- Creator rooms or squads
- Copy/follow features later

Risk:

- Leaderboards can encourage reckless sizing.
- Public PnL needs anti-fake and anti-multi-account controls.

## Competitive Map

### CEX Apps: Binance, Bybit, OKX, Bitget, MEXC

Strength:

- Liquidity
- Familiar order types
- Deep listings
- Existing mobile users
- Futures/perps infrastructure

Weakness:

- Dashboard-first UX
- Too many tabs and products
- Discovery is mostly manual
- Mobile feels like a compressed terminal
- "What is moving now?" is not the core screen

Takeaway:

These are the liquidity incumbents. They are not weak companies, but they are broad. The opening is to beat them on attention, discovery, and mobile speed.

### Analytics: TradingView and CoinGlass

Strength:

- Charts, screeners, data, funding, OI, liquidations, market context
- Pro trader trust
- Large user bases

Weakness:

- Not native execution-first apps
- The user still has to move from analysis to exchange
- Not built around a one-handed trading loop

Takeaway:

They prove demand for the data layer. Your product should absorb the most important derivatives metrics into the trading surface, not send users elsewhere.

### DEX / Perp Venues: Hyperliquid, Aster, Lighter, Ostium, GMX, Jupiter Perps, Drift, Paradex

Strength:

- Crypto-native
- Fast listings
- Strong trader culture
- On-chain or semi-on-chain transparency
- Hyperliquid especially proved that a focused perp venue can break through
- Lighter and Aster are strategically relevant for low-cost execution, points/reward upside, and direct competitive learning
- Ostium-style venues expand the feed beyond crypto into stocks, indices, commodities, and FX

Weakness:

- Onboarding is still crypto-native
- App-store path is not always clean
- UX is often still terminal-like
- Retail discovery is not solved

Takeaway:

Hyperliquid is an important strategic reference because it shows that traders will move away from old CEX brands if the product is fast, focused, and culturally alive. But TICK should not depend on one venue. The MVP should start with at least two execution venues behind the same intent model, then add cross-asset venues once the adapter and reconciliation layer are working.

### Rocket Perps

Rocket Perps is the closest emotional competitor.

Based on the Defi App docs, Rocket Perps is a gamified perpetuals product with:

- Long/short crypto trades
- 1000x leverage
- Aark Digital execution and settlement
- Oracle-based execution instead of an order book
- Short-duration positions
- 100% take-profit cap
- Arcade-style UI
- XP, coin tapping, frenzy mode, win streaks, leaderboards, trial mode
- Fees including opening fees, profit closing fees, and liquidation fees

This validates that "perps as a game" is already in market.

But it also shows the weakness of that lane. Rocket Perps is not really a pro trading terminal. It is closer to a high-leverage arcade product. The fee structure and 1000x framing make it feel like a degen minigame, not a foundation for a CEX.

Takeaway:

Do not copy Rocket Perps. Use it as proof that retail wants a faster emotional trading loop. Then go bigger: real CEX-grade perps, cleaner risk display, stronger market discovery, and TICK Pro.

### Robinhood, Kalshi, Coinbase

These are not direct UX competitors yet, but they matter strategically.

Kalshi and Coinbase moved into U.S. perpetuals in 2026. Robinhood is pushing perpetual futures in Europe and broader crypto/tokenized trading internationally. This confirms the direction: perps and 24/7 derivative exposure are moving from offshore crypto culture toward regulated mainstream finance.

Takeaway:

The window is open, but it will not stay empty. A startup has to move with a sharper product wedge before the giant apps normalize the category.

## Product Wedge

The wedge is not "we have perps." Everyone has perps.

The wedge is:

> We find the tradeable market for you.

The moat is the volatility explorer for day trading: a system that knows what is moving, whether it is clean to trade, what route is best, what leverage makes sense, and when the market moment is worth surfacing.

The app should feel like opening TikTok, but the feed is not content. The feed is markets.

Each card answers:

- What asset is moving?
- Why is it moving?
- Is there enough liquidity?
- Is the spread acceptable?
- Is volatility high enough to matter?
- Is the move crowded or early?
- What does the trade cost?
- What is the liquidation risk?
- Which route gives the cleanest execution without forcing the user to choose a venue?

Main product users see this as a Fire Score. TICK Pro users see the underlying data.

## Main TICK Product

The main TICK product should be fast, but not fake-simple.

Recommended loop:

- Swipe sideways: next market
- Swipe up: prepare long
- Swipe down: prepare short
- Hold/confirm: execute

The confirmation is important. It prevents accidental leveraged trades and helps app-store/regulatory optics.

Minimum visible fields:

- Asset
- Direction
- Size
- Leverage
- Max loss
- Liquidation price
- TP/SL
- Fee estimate
- Slippage/spread warning

The experience can still feel intense. The energy comes from fast market switching, visual movement, streaks, and feedback, not from hiding risk.

Leverage should be dynamic. The useful main product range is roughly 25x-100x. At 100x the live PnL loop is strong, but fees are amplified by leverage:

```text
round-trip fee as % of margin = 2 * taker fee * leverage
```

This means the app should not blindly offer 100x on every market. 100x belongs on low-cost routes and genuinely hot markets. If the route is expensive or the market is slow, the product should suggest lower leverage or warn that cost may eat the move.

## TICK Pro

TICK Pro is where the company becomes more than a novelty.

Must-have metrics:

- Mark price and index price
- Funding rate
- Open interest
- 24h volume and recent volume acceleration
- Spread and depth
- Liquidation estimate
- Position margin
- Isolated/cross margin
- Realized/unrealized PnL
- TP/SL and bracket orders
- Reduce-only
- Position history
- Fees and expected execution cost

The TICK Pro UX should be dense but calm. It should feel like a serious mobile trading cockpit, not a game.

## Becoming A CEX

The CEX path is credible if staged correctly.

Stage 1: Multi-venue wrapper / broker layer

- Connect to at least two execution venues
- Build the feed, UX, risk layer, onboarding, and brand
- Earn from referral, broker fee, or spread/take-rate share
- Validate retention, volume, and user behavior

Stage 2: Liquidity and routing layer

- Add smart routing across venues
- Improve fill quality
- Build market-maker relationships
- Add proprietary market quality scoring
- Own more of the execution economics
- Add cross-asset venues so the feed covers crypto, stocks, indices, commodities, and FX when legally available

Stage 3: Regulated exchange / CEX

- Own accounts, custody partners, matching/risk systems, compliance, listings, market surveillance
- Keep the feed as the main interface
- Use TICK Pro to attract serious traders and liquidity
- Use the main TICK product to onboard retail

The big strategic point: becoming a CEX is not just about infrastructure. The reason users would care is because the product discovers opportunities better than incumbent exchanges.

## App Store Reality

If the app is going on the App Store, the safest framing is financial trading, not gambling.

Apple's guidelines say:

- Crypto futures and similar crypto-securities/quasi-securities trading apps must come from established or approved financial institutions and comply with applicable law.
- Financial trading, investing, or money-management apps should be submitted by the institution performing the service and must have necessary licensing and permissions where available.
- Binary options apps are not permitted.
- CFDs and other derivatives must be properly licensed in all jurisdictions where available.

Google Play also treats crypto as financial services, requires local compliance, and does not allow apps that let users trade binary options.

Implication:

- Perps-first is viable if licensed/partnered/geofenced.
- Binary options should not be part of the App Store MVP.
- Do not use casino language in App Store metadata.
- Do not market as guaranteed profit, signals, or financial advice.
- Use jurisdiction gating from day one.

## Regulatory / Trust Risks

Key risks:

- Retail derivatives restrictions by jurisdiction
- UK-style retail crypto-derivatives bans
- App-store rejection if it looks like binary options or gambling
- User losses causing reputation damage
- Hidden fees or bad fills destroying trust
- Single-venue dependency creating bad economics or bad product coverage
- High leverage creating bad press
- Multi-account abuse and leaderboard farming
- Market manipulation on illiquid listings
- Custody/security risk if becoming a CEX

The product should be aggressive in UX, but conservative in risk disclosure and execution transparency.

## Business Model

Possible revenue streams:

- Trading fee share
- Spread/rebate economics from routing
- TICK Pro subscription for advanced feed metrics, alerts, and analytics
- VIP fee tiers
- Market-maker/listing economics later
- Competition sponsorships
- Creator/referral programs

Avoid making the whole business depend on "more swipes." That creates ugly incentives and makes the company fragile. The better model is: better discovery creates more qualified trading volume.

## Defensibility

The defensible asset is not the swipe UI. Anyone can copy gestures.

Potential moat:

- Volatility explorer tuned on real day-trading outcomes
- Cross-asset volatility and tradeability history
- Execution-quality data across venues
- Cost/leverage decisioning across venues
- User behavior data: what traders skip, inspect, trade, close, and repeat
- Mobile UX muscle around fast risk comprehension
- Brand trust with retail traders
- Liquidity relationships and routing economics
- Eventually, licenses and exchange infrastructure

The hard part is proving that the feed is not just entertainment. The volatility explorer has to produce better trade selection, cleaner execution, or higher user confidence than a normal watchlist.

## Go-To-Market

Best first market:

- Crypto-native retail traders outside heavily restricted jurisdictions
- Already comfortable with perps
- Mobile-first behavior
- Small to medium ticket sizes
- Uses CEX apps but hates their complexity

Initial hook:

> Open the app and see the markets moving right now.

Launch loop:

- Daily "Fire Markets"
- Shareable PnL cards
- Small competitions
- Trial mode / paper mode for viral onboarding
- Creator rooms later
- Pro traders can publish watchlists or market feeds

Do not lead with "1000x" or "casino." Lead with speed, market discovery, and mobile execution.

## Positioning

Weak positioning:

- TikTok for trading
- Casino for markets
- Swipe to gamble
- Easier Binance

Strong positioning:

- Feed-first mobile trading app
- Mobile terminal for high-velocity market moments
- Real-time market discovery plus execution
- The fastest way to find and trade volatile markets across supported asset classes

Best one-liner:

> A mobile-first trading app that ranks live market opportunities and lets traders act in one gesture.

## MVP Recommendation

Build the MVP as an execution wrapper, not a full CEX.

MVP should include:

- Feed of ranked market moments
- Main TICK product
- TICK Pro preview
- At least two execution venues behind the scenes
- Fee-aware route selection
- Dynamic leverage suggestions in the 25x-100x range
- Real or paper trading depending on licensing path
- Fire Score with transparent ingredients
- Bracket TP/SL by default
- Isolated margin by default
- Trade history and PnL
- App-store-safe copy
- Geofencing

Do not include in MVP:

- Binary options
- 1000x leverage
- Full casino language
- Too many assets before routing and eligibility are proven
- Single-venue dependency
- Copy trading
- Complex social systems
- Own matching engine

The first product question to validate:

> Does a ranked market feed increase trading frequency, retention, and user trust versus a normal CEX watchlist?

## Validation Metrics

Track these from the first test:

- Feed-to-inspect rate: how often users stop on a market
- Inspect-to-trade rate: how often the feed produces real intent
- Skip reason: boring, too volatile, bad liquidity, unclear setup
- Time from app open to first qualified trade
- Average trades per active day
- D1, D7, D30 retention
- Percentage of trades with TP/SL attached
- Liquidation rate by user cohort
- Fee and slippage as percentage of trade size
- Round-trip cost as percentage of user margin
- Suggested leverage versus user-selected leverage
- Route distribution by venue
- Net revenue per active trader
- Support tickets per 1,000 trades
- User trust score after losses

The most important early proof is not just volume. It is whether users believe the feed helped them find a better market.

## Main Conclusion

This is a real opportunity, but the winning version is not a game layered on trading. It is a trading product that uses feed psychology to solve discovery.

Rocket Perps proves the arcade-perps lane exists. CEXs prove the volume. TradingView and CoinGlass prove demand for analytics. Robinhood, Kalshi, and Coinbase prove perps are moving into mainstream regulated finance. Ostium-style venues show why the feed can become broader than crypto if execution and eligibility are handled correctly.

The gap is a mobile-native trading router where the feed is the terminal.

If built well, the main TICK product gets retail attention. TICK Pro earns credibility. The volatility explorer, cost/leverage engine, and execution-quality data become the moat. The long-term company can become a CEX because the interface gives users a reason to switch before the infrastructure is fully owned, but the MVP should prove this with at least two venues behind the scenes.

## Sources

- Rocket Perps docs: https://docs.defi.app/knowledge-base/trade-and-earn/trade-perpetuals/rocket-perps
- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Google Play Financial Services policy: https://support.google.com/googleplay/android-developer/answer/9876821
- Google Play Real-Money Gambling policy: https://support.google.com/googleplay/android-developer/answer/9877032
- FCA retail crypto-derivatives ban: https://www.fca.org.uk/news/press-releases/fca-bans-sale-crypto-derivatives-retail-consumers
- Axios on Kalshi perpetual futures: https://www.axios.com/2026/05/29/kalshi-perps-perpetual-futures-crypto
- IBD on Coinbase/Kalshi perpetual futures and crypto derivatives volume: https://www.investors.com/news/coinbase-kalshi-prediction-markets-perpetual-futures-preps-coin-stock-cboe-cme-intercontinental-exchange-ice/
- IBD on Robinhood's 2026 international product expansion: https://www.investors.com/news/robinhood-stock-hood-expansion-europe/
- WSJ on ICE/OKX joint venture: https://www.wsj.com/livecoverage/stock-market-today-dow-sp-500-nasdaq-06-22-2026/card/ice-okx-form-crypto-joint-venture-WdVisQymuYen7EuYJSKx
- TradingView mobile: https://www.tradingview.com/mobile/
- CoinGlass: https://www.coinglass.com/
- Hyperliquid docs: https://hyperliquid.gitbook.io/hyperliquid-docs/trading
- Lighter docs: https://docs.lighter.xyz/
- Aster docs: https://docs.asterdex.com/
- Ostium docs: https://docs.ostium.io/
