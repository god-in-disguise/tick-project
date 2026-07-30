# Annotated Sources

Last reviewed: 2026-07-30

## Evidence Grades

```text
A  Account-level data, controlled experiment, official market/protocol rule
B  Peer-reviewed or serious working paper with relevant market data
C  Official product documentation used as a workflow proxy
D  Educational or qualitative source used only for orientation
```

Product documentation shows what a workflow supports, not how often or how well
real traders use it.

## Trader Outcomes and Behavior

### A - Barber, Lee, Liu and Odean

[The Cross-Section of Speculator Skill: Evidence from Day Trading](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/The%20Cross-Section%20of%20Speculator%20Skill.pdf)

Complete Taiwan market data over 15 years. Finds real cross-sectional skill but
less than 1% predictably earn positive abnormal returns net of fees.

### A - Barber, Lee, Liu and Odean

[Do Day Traders Rationally Learn About Their Ability?](https://faculty.haas.berkeley.edu/odean/papers/Day%20Traders/Day%20Trading%20and%20Learning%20110217.pdf)

Shows persistent participation despite loss histories and reports that
unprofitable experienced traders account for most day-trading volume.

### A - Chague, De-Losso and Giovannetti

[Day Trading for a Living?](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3423101)

Brazilian equity-futures account data. Strong evidence against treating
persistence as proof of developing skill.

### A - Barber and Odean

[Trading Is Hazardous to Your Wealth](https://faculty.haas.berkeley.edu/odean/papers/returns/individual_investor_performance_4-99.pdf)

Large brokerage-account sample separating gross from net performance. Important
support for TICK's net-PnL-first rule.

### A - Odean

[Are Investors Reluctant to Realize Their Losses?](https://faculty.haas.berkeley.edu/odean/papers/disposition/disposition.html)

Account-level evidence of the disposition effect: investors realize winners
more readily than losers.

### B - Barber and Odean review

[The Behavior of Individual Investors](https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/behavior%20of%20individual%20investors.pdf)

Useful synthesis of attention, overtrading, diversification, and performance
findings. Particularly relevant to how Pulse rankings allocate attention.

## Mobile Interfaces and Engagement

### A - Financial Conduct Authority

[Digital Engagement Practices: A Trading Apps Experiment](https://www.fca.org.uk/publications/fca-research/research-note-digital-engagement-practices-trading-apps-experiment)

Controlled experiment with more than 9,000 consumers. Push notifications,
points/prize mechanics, and leaderboards changed trading activity or risk.

### A - IOSCO

[Final Report on Digital Engagement Practices](https://www.iosco.org/library/pubdocs/pdf/IOSCOPD794.pdf)

Current international regulatory synthesis of benefits, conflicts, and retail
harm risks from digital engagement practices.

### B - Xiao Cen

[Smartphone Trading Technology, Investor Behavior, and Financial Fragility](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3312411)

Natural experiment around an app launch. Useful evidence that mobile access
changes attention and trading behavior rather than merely moving an existing
workflow to a smaller screen.

## Crypto Participation and Microstructure

### A - Bank for International Settlements

[Crypto Trading and Bitcoin Prices: Evidence from a New Database of Retail Adoption](https://www.bis.org/publ/work1049.htm)

Daily crypto-app use across 95 countries. Supports the claim that retail entry
is strongly associated with rising prices and attention.

### A - Bank for International Settlements

[Crypto Shocks and Retail Losses](https://www.bis.org/publ/bisbull69.htm)

Documents retail behavior and estimated losses around the 2022 crypto shocks.

### B - Hansen, Kim and Kimbrough

[Periodicity in Cryptocurrency Volatility and Liquidity](https://arxiv.org/abs/2109.12142)

Documents recurring time-of-day, day-of-week, and within-hour patterns across
centralized and decentralized crypto venues.

### B - Brauneis, Mestel and Theissen

[The Crypto World Trades at Tea Time](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4347853)

Large cross-venue and cross-pair study of intraday return, activity,
volatility, and illiquidity patterns.

### B - Mercik and Bedowska-Sojka

[When Markets Never Sleep](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6401099)

Recent high-frequency work linking volatility, spread, venue, quote currency,
and periodicity. Treat as a working paper, not settled fact.

## Current Execution Venue

### A - Gains Network

- [Price Feed](https://docs.gains.trade/developer/integrators/price-feed)
- [Fees and Spread](https://docs.gains.trade/gtrade-leveraged-trading/fees-and-spread)
- [Crypto](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/cryptocurrencies)
- [Forex](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/forex)
- [Commodities](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/commodities)
- [Indices](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/indices)
- [Stocks](https://docs.gains.trade/gtrade-leveraged-trading/asset-classes/stocks)

Official source for current route mechanics, price source, fee model, leverage
ranges, sessions, gaps, and restrictions. Product capabilities must still be
loaded dynamically because protocol configuration changes.

## Cross-Asset Market Structure

### A - NYSE

- [Trading Hours and Calendars](https://www.nyse.com/markets/hours-calendars)
- [Corporate Actions and Market Watch](https://www.nyse.com/regulation/corporate-actions-market-watch-proxy-compliance)

Supports explicit equity sessions, holidays, halts, and corporate-action state.

### A - CME Group

- [CME Trading Hours](https://www.cmegroup.com/trading-hours.html)
- [FX Futures Calendar Spreads and Hours](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-cme-fx-futures-calendar-spreads.html)
- [Interest Rate Products](https://www.cmegroup.com/markets/interest-rates.html)
- [Micro Treasury and Yield Futures](https://www.cmegroup.com/articles/2024/micro-treasury-futures-vs-yield-futures.html)

Official source for futures sessions, expiry-bearing instruments, and the case
for representing liquid rate exposure through futures rather than individual
cash bonds.

### A - Investor.gov

[Bonds and Fixed-Income Products](https://www.investor.gov/introduction-investing/investing-basics/investment-products/bonds-or-fixed-income-products/bonds)

Supports the liquidity-risk distinction between cash bonds and liquid listed
rates products.

### A - Federal Reserve and Bureau of Labor Statistics

- [FOMC Calendar](https://www.federalreserve.gov/fomc/)
- [BLS Release Calendar](https://www.bls.gov/schedule/2026/home.htm)

Primary schedules for event metadata. Events can change availability, spread,
or risk state but must not be turned into direction signals.

## Workflow Proxies

### C - Interactive Brokers and Fidelity

- [IBKR Market Scanners](https://www.interactivebrokers.com/en/?f=%2Fen%2Fsoftware%2Fpdfhighlights%2FPDF-marketscanners.php)
- [IBKR: Mean Reversion](https://www.interactivebrokers.com/campus/glossary-terms/mean-reversion-statistical/)
- [Fidelity: Momentum](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/momentum)
- [Fidelity: Range Trading](https://www.fidelity.com/learning-center/trading-investing/trading/range-trading)

These establish common scanner fields and the operational distinction between
momentum and range-based workflows. They describe tools and concepts rather
than proving strategy profitability.

### C - TradingView

- [Multi-Timeframe Analysis](https://www.tradingview.com/support/solutions/43000591555-leveraging-multi-timeframe-analysis/)
- [Watchlist Alerts](https://www.tradingview.com/support/solutions/43000739708-watchlist-alerts-your-trading-edge/)
- [Multi-Condition Alerts](https://www.tradingview.com/support/solutions/43000761492-multi-condition-alerts/)
- [Crypto Coins Screener](https://www.tradingview.com/support/solutions/43000718742-crypto-coins-screener-discover-hidden-gems/)
- [Stock Screener](https://www.tradingview.com/support/solutions/43000718866-tradingview-stock-screener-trade-smarter-not-harder/)

Supports the workflow pattern of scanning many symbols, orienting with wider
context, and receiving condition-based alerts. It does not prove TICK's exact
windows or UI.

## Intraday Regimes

### B - Gao, Han, Li and Zhou

[Market Intraday Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866)

Documents an intraday momentum relationship in actively traded ETFs that is
stronger during high-volume and high-volatility conditions. Its half-hour
horizon does not establish continuation at TICK's 10-60 second horizon.

### B - Wen, Bouri, Xu and Zhao

[Intraday Return Predictability in Cryptocurrency Markets: Momentum, Reversal,
or Both](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4080253)

Finds both momentum and reversal in Bitcoin, with behavior changing around
jumps, liquidity, macro announcements, and broader market regimes. Supports
classifying observed behavior and testing exact horizons rather than assuming
that a large move will continue.

### C - Bybit

[TP/SL for Perpetual and Futures Contracts](https://www.bybit.com/en/help-center/article/Introduction-to-Take-Profit-Stop-Loss-Perpetual-Futures-Contracts)

Useful operational reference for whole-position versus partial TP/SL,
liquidation trigger differences, and the possibility that a stop does not
protect as expected.

## Source Gaps

The next research pass should add:

1. TICK user interview transcripts and coded workflow observations.
2. TICK scanner shadow outcomes by asset class and session.
3. Route-specific cost and latency distributions for non-crypto markets.
4. Evidence on short-horizon mobile interruption and recovery behavior.
5. Jurisdiction-specific availability research before any public cross-asset
   claim.
