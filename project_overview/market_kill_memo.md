# Kill Memo: Feed-First Mobile Perps CEX

Current as of July 6, 2026.

## Short Verdict

If the idea is "a consumer App Store app that makes leveraged crypto perps feel like a dopamine feed," the default answer should be: stop now.

Not because perps are small. They are huge. Not because mobile trading is fake. It is real. The problem is that the strongest growth mechanics of the product create the strongest regulatory, app-store, trust, and unit-economic risks.

The better version may still exist, but it is narrower:

> A market-intelligence and multi-venue execution wrapper for eligible traders, with a feed as the discovery layer.

The full CEX vision should not be the starting point. It is too expensive, too regulated, too trust-sensitive, and too easy for incumbents to copy once validated. The MVP should also not become a single-venue skin. If the product depends on one venue, routing, cost control, reward upside, and cross-asset coverage are too fragile.

## Why The Bull Case May Be Wrong

### 1. "Huge market" does not mean reachable market

Perps volume is massive, but most of that volume is not sitting there waiting for a better mobile UI.

Much of it comes from:

- Existing CEX liquidity
- Market makers
- Professional and semi-professional traders
- Bots and high-frequency strategies
- Large offshore venues
- Incentive farming
- Traders who already know exactly where they want to trade

The app would not be competing for "the perp market." It would be competing for the subset of users who:

- Are allowed to trade perps in their jurisdiction
- Want to trade perps from mobile
- Are willing to trust a new brand
- Are not already satisfied with Binance, Bybit, OKX, Hyperliquid, Coinbase, Robinhood, or Kalshi
- Care enough about feed discovery to switch

That is a much smaller reachable market.

### 2. Retail leveraged traders are a bad core customer

The retail action trader is attractive because they trade frequently. That is also the problem.

Retail leveraged trading products have a long history of customer losses, regulatory intervention, and reputational damage. ESMA found that 74-89% of retail CFD accounts typically lose money, with average losses across jurisdictions ranging from EUR 1,600 to EUR 29,000. Crypto perps are not identical to CFDs, but they share the dangerous traits: leverage, volatility, fast liquidation, and retail misunderstanding.

If the user loses money after the app pushed a "Fire" market, they will not think, "I made a bad trading decision." They will think, "The app fed me a bad trade."

That creates support burden, bad reviews, regulator complaints, social backlash, and long-term brand damage.

### 3. The feed may look like advice

The core product claim is: "We find the market worth trading now."

That is powerful UX, but it can also look like recommendation, solicitation, steering, or personalized investment nudging. The more the feed uses user behavior, predicted trade intent, risk appetite, streaks, and PnL history, the more it resembles a recommendation engine.

SEC concerns around predictive data analytics are directly relevant. The SEC has warned that broker-dealers and advisers using predictive technologies to guide investor behavior can create conflicts when the firm benefits from more trading.

This is a hard conflict to explain away if revenue increases when users swipe into more leveraged positions.

### 4. App Store distribution is fragile

The App Store path is not "we make it finance-native and we are fine." It is more fragile than that.

Apple says crypto futures and similar crypto-securities or quasi-securities trading apps must come from established banks, securities firms, futures commission merchants, or other approved financial institutions, and must comply with applicable law. Apple also says financial trading apps should be submitted by the financial institution performing the service and must have necessary licensing and permissions in the locations where the app is available. Binary options apps are not permitted.

Google Play also treats crypto as financial services, requires local compliance, and does not allow apps that let users trade binary options.

So the exact launch channel you want forces the hardest version of the company:

- Proper licensing or approved institution status
- Jurisdiction-by-jurisdiction availability
- Review notes and demo access
- Conservative metadata
- No hidden gambling framing
- No binary options
- Careful treatment of derivatives and leverage

If the UI feels like a game, review risk goes up.

### 5. EU and UK are structurally hostile to retail crypto derivatives

This is not a minor detail. The UK banned sale, marketing, and distribution of derivatives and ETNs referencing certain cryptoassets to retail consumers, effective January 6, 2021.

In Europe, ESMA issued a February 24, 2026 reminder that derivatives marketed as perpetual futures or perpetual contracts, including those referencing cryptoassets, may fall under CFD product intervention measures. Those measures include leverage limits, risk warnings, margin close-out, negative balance protection, and bans on incentives.

On July 3, 2026, ESMA also reminded firms that event contracts with binary financial outcomes may fall under binary-option intervention measures.

That means the simple retail mode is not a globally portable product. It has to be carved up by jurisdiction before it can scale.

### 6. The competitors are not sleeping

The research memo frames incumbents as dashboard-first. True. But the incumbents have massive advantages:

- Binance, OKX, Bybit, Bitget, MEXC: liquidity, listings, fee tiers, referral networks, brand familiarity
- Hyperliquid: trader culture, focused perps venue, fast product loop
- Coinbase, Kalshi, Robinhood: regulated-market access and consumer trust
- TradingView and CoinGlass: chart/data mindshare
- Rocket Perps: closest emotional competitor for arcade perps

If a feed-first UI works, it is copyable. Incumbents can add:

- "Hot markets" feed
- Volatility cards
- Swipe execution
- Mobile main TICK product
- Streaks and competitions
- AI trade scanner

They do not need to copy the whole company. They only need to copy the part that works.

### 7. The "Main TICK + TICK Pro" split may be incoherent

The main TICK product wants speed, emotion, and low friction.

TICK Pro wants control, data density, precision, and trust.

Those can share a backend, but the brand tension is real. If the app is too arcade, pros will not trust it. If it is too serious, retail loses the dopamine loop. If both are in one product, each side may see the other as evidence that the app is not for them.

This is especially dangerous if the long-term goal is to become a CEX. Exchanges are trust businesses before they are UX businesses.

### 8. Pro traders may not switch for UX

Serious perp traders care about:

- Liquidity
- Fees
- Funding
- Fill quality
- Latency
- Reliability during volatility
- API support
- Margin system
- Withdrawal confidence

Mobile UI helps, but it is not usually enough to move serious volume. A good feed might get attention, but pro traders will still execute where the order book, fees, and reliability are best.

If the app is only a wrapper, economics are thin. If it becomes a venue, infrastructure burden explodes.

### 9. Becoming a CEX is a different company

"Start with a wrapper, then become a CEX" sounds logical. In practice, the second part is not an upgrade; it is a new company.

A real CEX needs:

- Custody or custody partners
- Wallet security
- KYC/AML
- Transaction monitoring
- Sanctions screening
- Market surveillance
- Risk engine
- Liquidation engine
- Insurance fund logic
- Market-maker relationships
- Compliance staff
- Customer support
- Incident response
- Licenses or exemptions
- Banking and payment rails
- Proof of reserves / trust reporting

The Bybit hack shows the security burden at exchange scale. The FBI attributed approximately $1.5B in stolen virtual assets from Bybit to North Korean actors in February 2025. Even a major exchange can suffer catastrophic security events.

That is the trust bar for anyone touching custody or exchange infrastructure.

### 10. The unit economics may be worse than they look

The original model assumed frequent swipes, meaningful size, and a fee take.

Reality:

- Retail users may trade small
- They may churn after losses
- High leverage causes fast blowups
- Fee competition is brutal
- Pro traders demand discounts
- Venue partners keep economics
- Affiliates and creators need payouts
- Compliance, KYC, chargebacks, support, data, and infrastructure are expensive
- App Store acquisition is expensive
- Organic viral growth is unreliable

The product may generate attention without producing durable revenue.

At high leverage, the problem is sharper. Opening and closing fees are amplified by leverage:

```text
round-trip fee as % of margin = 2 * taker fee * leverage
```

This means 100x can work on low-cost routes in hot markets, but it can be a bad user loop on normal-fee routes or slow markets. If the app cannot route to low-cost execution, dynamic leverage becomes a requirement, not a nice-to-have.

### 10a. Single-venue dependency can kill the product

A one-venue wrapper is faster to build, but strategically weak.

Problems:

- Users get the venue's fee schedule whether or not it fits the moment.
- Market coverage is limited to that venue's listings.
- Reward/points upside can disappear overnight.
- Outages or degraded APIs become TICK outages.
- The product cannot prove it has a real volatility explorer or routing moat.
- The venue can copy the UI or change partner economics.

The MVP should start with at least two execution venues behind one normalized trade-intent model. Ostium-style cross-asset coverage is interesting, but it should be an expansion path, not the only rail.

### 11. The product may select for bad markets

The volatility explorer wants movement. But volatile retail-friendly markets often come with:

- Wider spreads
- Thinner depth
- Higher slippage
- Higher manipulation risk
- Faster liquidations
- More news/rumor risk
- Worse fills during congestion

If the ranking engine shows only "safe" markets, the app may feel boring. If it shows exciting markets, execution quality and user outcomes may deteriorate.

This is the core product contradiction.

### 12. The emotional loop is a liability

The casino/slot-machine instinct is useful for consumer engagement, but dangerous for a trading product.

Any of these features can become evidence against the company:

- Streaks
- Frenzy modes
- Flashing "Fire" markets
- Rewards for activity
- Leaderboards
- Push alerts during volatility
- Social PnL cards
- Swipe-to-trade
- XP or missions tied to volume

Even if legal, the optics are bad if customers lose money. The better the dopamine system works, the easier it is to argue that the product encouraged overtrading.

## Why The Research Memo Is Too Bullish

The research memo says the gap is "a mobile-native perp CEX where the feed is the terminal."

The bearish response:

The gap may exist because it is not a good business, not because nobody noticed it.

Reasons:

- Incumbents avoid full feed-first leverage UX because it increases regulatory and reputational risk.
- App stores may tolerate trading dashboards more easily than trading games.
- Pro traders do not need a feed enough to switch.
- Retail traders who love the feed may be the least durable and highest-risk customers.
- The best market data layer may be a feature, not a company.
- If the ranking engine works, CEXs can copy it.
- If it does not work, the product is just a prettier way to lose money.

## Stop Criteria

Stop the project if any of these are true:

- You cannot get at least two serious licensed or eligible venue/broker integrations.
- One venue's economics, uptime, or API shape dominates the product.
- Apple review path requires institution status you do not have.
- Legal counsel says the feed creates recommendation/advice/suitability exposure you cannot manage.
- You cannot operate in your desired launch jurisdictions with retail perps.
- Your first tests show users treat the feed as "signals" rather than discovery.
- Paper trading retention does not survive after real-money losses.
- Median retail users blow up too fast.
- Pro traders say they like the UX but would not route real size through it.
- Unit economics require encouraging more trades, not better trades.
- Fee/spread drag makes 100x feel exciting visually but bad economically.
- The product roadmap depends on binary options or casino framing to be exciting.

If three or more are true, kill or pivot.

## What Could Still Be Worth Building

Do not start with "mobile CEX."

A safer wedge:

> A perp market scanner and execution assistant for eligible traders.

This version:

- Starts with analytics/feed, not custody
- Targets experienced traders first
- Avoids binary options
- Avoids casino language
- Treats "Fire" as explainable market state, not a signal
- Makes money from pro tools, alerts, and routing economics
- Uses real-money trading only through licensed/eligible partners
- Keeps the App Store copy conservative

Potential first products:

- Mobile "Fire Feed" for perps
- TICK Pro alerts: OI spike, funding dislocation, liquidation cluster, volume acceleration
- Execution ticket that pre-fills but does not recommend
- Paper trading main TICK product
- B2B feed/ranking API for exchanges

This is less sexy, but more survivable.

## Decision Matrix

| Version | Decision | Why |
| --- | --- | --- |
| Casino-like swipe perps for everyone | Stop | Highest regulatory, app-store, loss, and reputation risk |
| Full CEX from day one | Stop | Too much licensing, custody, liquidity, compliance, and security burden before product proof |
| App Store retail perps with main TICK product first | Probably stop | Distribution depends on licensing, review risk, and jurisdiction gating before learning enough |
| Paper-trading main TICK product | Test | Useful for retention and UX learning without financial harm |
| TICK Pro mobile perp scanner | Test | Stronger customer, cleaner positioning, lower regulatory temperature if framed as analytics |
| Single-venue execution wrapper | Weak test | Useful for a demo, but not enough to prove routing, cost control, or defensibility |
| Multi-venue execution wrapper for eligible users | Test carefully | Can validate flow without owning custody or matching while avoiding venue lock-in |
| B2B market-ranking API for exchanges | Explore | Lower consumer risk and easier to monetize if the ranking engine works |

The bar to keep going should be high: the volatility explorer must prove it creates better market selection, not just more trading.

## Experiments Before Spending Real Money

Do these before building a full app:

1. Legal memo

Ask counsel specifically about perps, CFDs, suitability/appropriateness, recommendations, incentives, and app-store distribution in the first launch countries.

2. Venue partner calls

Find out whether at least two serious CEX/DEX/regulated venues will let you route flow from a feed-first mobile app and what economics they offer. Ask specifically about fees, leverage limits, session keys, reward attribution, outage handling, and whether they can support the asset classes TICK wants to show.

3. Pro trader interviews

Talk to at least 30 active perp traders. The key question is not "do you like the UI?" It is "would you move real volume through this?"

4. Retail paper prototype

Run the swipe/feed loop with paper trading. Track retention after losses, not after wins.

5. Backtest Volatility Explorer

Test whether the ranking engine finds markets with better net tradeability after spread, slippage, funding, and fees. If the score only finds raw volatility, it is not enough.

6. Backtest Cost And Leverage

Test whether 25x, 50x, and 100x produce a good user loop after round-trip fees and spread. If 100x only works on one route or only during extreme volatility, the product must dynamically suggest lower leverage.

7. App Store preflight

Prepare conservative metadata and review notes. If the product cannot be described without sounding like gambling or advice, stop.

## Final Bearish Conclusion

The best reason to stop is not that the idea is fake. It is that the most exciting version is probably the least buildable.

The market is big, but regulated and dominated. Retail wants the dopamine loop, but retail losses create legal and reputational drag. Pros want better mobile tools, but they follow liquidity and fees. The feed is the wedge, but the feed may look like advice and is easy for incumbents to copy. Becoming a CEX is possible only after solving licensing, custody, liquidity, market surveillance, and trust.

So the honest answer:

- Stop if the goal is a casino-like consumer perp app in the App Store.
- Stop if the goal is to become a CEX from day one.
- Continue only if the first product is a constrained, finance-native market discovery tool for eligible traders.

The survivable thesis is not "make trading addictive."

The survivable thesis is:

> Help active traders find and execute tradeable volatility faster, with transparent risk, low-cost routing, and venue-grade execution.

That is still interesting. It is just a smaller, harder, more regulated company than the dopamine version suggests.

## Sources

- Apple App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
- Google Play Financial Services policy: https://support.google.com/googleplay/android-developer/answer/9876821
- FCA retail crypto-derivatives ban: https://www.fca.org.uk/news/press-releases/fca-bans-sale-crypto-derivatives-retail-consumers
- ESMA CFD/binary options retail intervention: https://www.esma.europa.eu/press-news/esma-news/esma-agrees-prohibit-binary-options-and-restrict-cfds-protect-retail-investors
- ESMA perpetual futures / CFD reminder, February 24, 2026: https://www.esma.europa.eu/press-news/esma-news/esma-reminds-firms-their-obligations-under-cfd-product-intervention-measures
- ESMA binary options / event contracts reminder, July 3, 2026: https://www.esma.europa.eu/press-news/esma-news/esma-reminds-firms-existing-rules-and-obligations-under-binary-option-measures
- SEC predictive data analytics conflicts proposal: https://www.sec.gov/newsroom/press-releases/2023-140
- FBI / IC3 Bybit hack PSA: https://www.ic3.gov/PSA/2025/PSA250226
- Rocket Perps docs: https://docs.defi.app/knowledge-base/trade-and-earn/trade-perpetuals/rocket-perps
- Axios on Kalshi perpetual futures: https://www.axios.com/2026/05/29/kalshi-perps-perpetual-futures-crypto
- IBD on Coinbase/Kalshi perpetual futures and crypto derivatives volume: https://www.investors.com/news/coinbase-kalshi-prediction-markets-perpetual-futures-preps-coin-stock-cboe-cme-intercontinental-exchange-ice/
