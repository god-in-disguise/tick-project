# Evidence on Short-Horizon Retail Trading

Last reviewed: 2026-07-30

## 1. Persistent Profitability Is Rare

Account-level studies consistently find that most day traders lose after costs,
although a very small skilled group exists.

- A 15-year Taiwan market study found that less than 1% of day traders
  predictably earned positive abnormal returns net of fees. The study is useful
  because it observes a complete market and repeated outcomes for each trader.
- A Brazilian equity-futures study found that 97% of people who persisted for
  more than 300 days lost money. Only 1.1% earned more than the local minimum
  wage.
- A second Taiwan study found that nearly three quarters of day-trading volume
  came from traders with a history of losses.

Sources:

- [Barber et al.: The Cross-Section of Speculator Skill](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf)
- [Chague et al.: Day Trading for a Living?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101)
- [Barber et al.: Do Day Traders Rationally Learn About Their Ability?](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf)

TICK implication:

> The product must be exceptionally honest about costs and outcomes. A smooth
> trade loop is not evidence that the trade was good.

## 2. Costs Turn Activity Into Losses

Research on more than 60,000 brokerage households found unremarkable gross
performance but materially worse net performance after commissions, spread,
and market impact. The most active households performed substantially worse
than the least active group.

This is directly relevant to TICK because a very short holding period gives
round-trip cost little time to be recovered. At high leverage, a small
percentage fee on notional can consume a large percentage of collateral.

Sources:

- [Barber and Odean: Trading Is Hazardous to Your Wealth](https://faculty.haas.berkeley.edu/odean/papers/returns/individual_investor_performance_4-99.pdf)
- [SEC: Day Trading - Your Dollars at Risk](https://www.sec.gov/about/reports-publications/investorpubsdaytipshtm)
- [Gains Network: Fees and Spread](https://docs.gains.trade/gtrade-leveraged-trading/fees-and-spread)

TICK implication:

```text
primary live number = estimated net if closed now
primary final number = reconciled net wallet result
```

Gross chart movement may explain a result but must not impersonate it.

## 3. Attention Strongly Shapes What Retail Traders Buy

Retail investors face a large search problem. Research finds that news,
abnormal volume, extreme returns, and prominent lists draw attention and alter
what individuals trade. Attention-grabbing assets are not automatically better
trades.

This supports a scanner, but also makes the scanner a powerful choice
architecture. Ranking markets is not neutral.

Sources:

- [Barber and Odean: The Behavior of Individual Investors](https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/behavior%20of%20individual%20investors.pdf)
- [Peng and Xiong: Investor Attention, Overconfidence and Category Learning](https://www.nber.org/papers/w11400)
- [TradingView: Watchlist Alerts](https://www.tradingview.com/support/solutions/43000739708-watchlist-alerts-your-trading-edge/)

TICK implication:

> Pulse should explain why a market is ranked and should be willing to say that
> no market qualifies. It must not present recent movement as a directional
> recommendation.

## 4. Mobile Access and Engagement Mechanics Change Behavior

Mobile access lowers friction and raises attention. A natural-experiment study
of smartphone trading found increased attention and trading volume after app
adoption, alongside stronger sensitivity to short-term returns and sentiment.

The FCA ran a controlled experiment with more than 9,000 participants. Push
notifications and points linked to a prize draw increased trading frequency by
11% and 12%; the same treatments also increased the share of trades placed in
high-risk investments. A leaderboard increased the amount traded even when it
did not increase trade count.

Sources:

- [Cen: Smartphone Trading Technology, Investor Behavior, and Financial Fragility](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3312411)
- [FCA: Digital Engagement Practices Trading-App Experiment](https://www.fca.org.uk/publications/fca-research/research-note-digital-engagement-practices-trading-apps-experiment)
- [IOSCO: Final Report on Digital Engagement Practices](https://www.iosco.org/library/pubdocs/pdf/IOSCOPD794.pdf)

TICK implication:

Allowed engagement:

```text
real market discovery
clear state changes
smooth truthful animation
execution and risk feedback
```

Rejected engagement:

```text
trade streaks
volume rewards
loss-chasing prompts
profit leaderboards
celebration for opening risk
```

## 5. Fast Feedback Does Not Guarantee Rational Learning

Day traders receive unusually frequent and clear feedback, yet experienced
losing traders often continue. Previous gains do affect continued participation,
but the observed persistence of unprofitable trading is inconsistent with a
simple rational-learning explanation.

Source:

- [Barber et al.: Do Day Traders Rationally Learn About Their Ability?](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf)

TICK implication:

> History must explain costs, execution, and net outcomes instead of merely
> counting wins. Session limits and post-loss behavior should be measurable
> even if the first private demo does not impose hard caps.

## 6. Crypto Is Always Open, but Activity Is Not Uniform

Crypto trades continuously, but research documents systematic intraday and
weekly patterns in volatility, volume, and liquidity. Activity often increases
during overlapping European and US market hours, and venue and quote-currency
differences matter. Volatility also affects spreads.

Sources:

- [Hansen, Kim and Kimbrough: Periodicity in Cryptocurrency Volatility and Liquidity](https://arxiv.org/abs/2109.12142)
- [Brauneis, Mestel and Theissen: The Crypto World Trades at Tea Time](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4347853)
- [Mercik and Bedowska-Sojka: When Markets Never Sleep](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6401099)

TICK implication:

> A crypto market's baseline must account for time of day, weekday, venue, and
> its own recent regime. A fixed global threshold will systematically over-rank
> naturally noisy markets and under-rank unusual movement in normally quiet
> markets.

## 7. Retail Crypto Participation Is Highly Procyclical

BIS research using crypto-app adoption across 95 countries found that higher
Bitcoin prices were associated with more new users. During major 2022 shocks,
large holders sold while smaller retail participants bought; estimated retail
users in most economies lost on their Bitcoin holdings.

Sources:

- [BIS: Crypto Trading and Bitcoin Prices](https://www.bis.org/publ/work1049.htm)
- [BIS: Crypto Shocks and Retail Losses](https://www.bis.org/publ/bisbull69.htm)

TICK implication:

> A market becoming more salient during a shock is not evidence that entering
> it is beneficial. Pulse should describe activity, cost, route health, and
> event risk without turning attention into advice.

## What the Evidence Does Not Establish

The reviewed research does not prove:

- that a 90-second chart is the optimal TICK chart;
- that a particular indicator improves TICK user outcomes;
- that market movement above estimated cost has positive expected value;
- that users understand 100x or 500x leverage because the terms are visible;
- that cross-asset discovery improves retention;
- that a faster opening transaction improves financial outcomes;
- that equity day-trader findings transfer unchanged to crypto perps.

Those remain product hypotheses and require TICK-specific measurement.
