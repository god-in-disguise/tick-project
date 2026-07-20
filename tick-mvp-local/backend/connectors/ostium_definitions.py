from __future__ import annotations

import os

ALL_FEED_CANDIDATES = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "TRX-USD",
    "ADA-USD",
    "HYPE-USD",
    "BNB-USD",
    "XRP-USD",
    "LINK-USD",
    "SPX-USD",
    "DJI-USD",
    "NDX-USD",
    "NIK-JPY",
    "FTSE-GBP",
    "DAX-EUR",
    "HSI-HKD",
    "NVDA-USD",
    "GOOG-USD",
    "AMZN-USD",
    "META-USD",
    "AAPL-USD",
    "MSFT-USD",
    "TSLA-USD",
    "COIN-USD",
    "MSTR-USD",
    "HOOD-USD",
    "CRCL-USD",
    "BMNR-USD",
    "SBET-USD",
    "GLXY-USD",
    "AMD-USD",
    "PLTR-USD",
    "NFLX-USD",
    "ORCL-USD",
    "RIVN-USD",
    "COST-USD",
    "XOM-USD",
    "CVX-USD",
    "GEV-USD",
    "SHEL-USD",
    "ARM-USD",
    "ASML-USD",
    "AVGO-USD",
    "CAT-USD",
    "INTC-USD",
    "SMCI-USD",
    "TSM-USD",
    "MU-USD",
    "SNDK-USD",
    "MP-USD",
    "BB-USD",
    "XAU-USD",
    "XAG-USD",
    "XPD-USD",
    "XPT-USD",
    "BRENT-USD",
    "HG-USD",
    "CL-USD",
    "XLE-USD",
    "HYG-USD",
    "TLT-USD",
    "DRAM-USD",
    "REMX-USD",
]

DEFAULT_FEED_CANDIDATES = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "HYPE-USD",
    "BNB-USD",
    "XRP-USD",
    "LINK-USD",
    "ADA-USD",
    "TRX-USD",
]
_configured_feed = [item.strip().upper() for item in os.getenv("TICK_FEED_PAIRS", "").split(",") if item.strip()]
FEED_CANDIDATES = _configured_feed or DEFAULT_FEED_CANDIDATES

ASSET_NAMES = {
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
    "SOL": "Solana",
    "HYPE": "Hyperliquid",
    "BNB": "BNB",
    "XRP": "XRP",
    "LINK": "Chainlink",
    "TRX": "Tron",
    "ADA": "Cardano",
    "SPX": "S&P 500",
    "DJI": "Dow Jones",
    "NDX": "Nasdaq 100",
    "NIK": "Nikkei 225",
    "FTSE": "FTSE 100",
    "DAX": "DAX",
    "HSI": "Hang Seng",
    "NVDA": "Nvidia",
    "GOOG": "Google",
    "AMZN": "Amazon",
    "META": "Meta",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "TSLA": "Tesla",
    "COIN": "Coinbase",
    "MSTR": "MicroStrategy",
    "HOOD": "Robinhood",
    "CRCL": "Circle",
    "BMNR": "BitMine",
    "SBET": "SharpLink",
    "GLXY": "Galaxy",
    "AMD": "AMD",
    "PLTR": "Palantir",
    "NFLX": "Netflix",
    "ORCL": "Oracle",
    "RIVN": "Rivian",
    "COST": "Costco",
    "XOM": "Exxon",
    "CVX": "Chevron",
    "GEV": "GE Vernova",
    "SHEL": "Shell",
    "ARM": "Arm",
    "ASML": "ASML",
    "AVGO": "Broadcom",
    "CAT": "Caterpillar",
    "INTC": "Intel",
    "SMCI": "Super Micro",
    "TSM": "TSMC",
    "MU": "Micron",
    "SNDK": "SanDisk",
    "MP": "MP Materials",
    "BB": "BlackBerry",
    "XAU": "Gold",
    "XAG": "Silver",
    "XPD": "Palladium",
    "XPT": "Platinum",
    "BRENT": "Brent Oil",
    "HG": "Copper",
    "CL": "Crude Oil",
    "XLE": "Energy ETF",
    "HYG": "High Yield ETF",
    "TLT": "20Y Treasury ETF",
    "DRAM": "Memory ETF",
    "REMX": "Rare Earth ETF",
}

CRYPTO_SYMBOLS = {"BTC", "ETH", "SOL", "HYPE", "BNB", "XRP", "LINK", "ADA", "TRX"}
INDEX_SYMBOLS = {"SPX", "DJI", "NDX", "NIK", "FTSE", "DAX", "HSI", "US100", "US500", "US30", "UK100", "GER40", "JP225", "HK50"}
COMMODITY_SYMBOLS = {"XAU", "XAG", "XPT", "XPD", "XCU", "WTI", "BRENT", "HG", "CL", "COCOA", "COFFEE", "COTTON", "SUGAR", "DIESEL"}
STOCK_SYMBOLS = {
    "NVDA",
    "TSLA",
    "COIN",
    "MSTR",
    "HOOD",
    "CRCL",
    "BMNR",
    "SBET",
    "GLXY",
    "AMD",
    "PLTR",
    "AAPL",
    "MSFT",
    "GOOG",
    "AMZN",
    "META",
    "NFLX",
    "ORCL",
    "RIVN",
    "COST",
    "XOM",
    "CVX",
    "GEV",
    "SHEL",
    "ARM",
    "ASML",
    "AVGO",
    "CAT",
    "INTC",
    "SMCI",
    "TSM",
    "MU",
    "SNDK",
    "MP",
    "BB",
    "XLE",
    "HYG",
    "TLT",
    "DRAM",
    "REMX",
}


ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

TRADING_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "collateral", "type": "uint256"},
                    {"internalType": "uint192", "name": "openPrice", "type": "uint192"},
                    {"internalType": "uint192", "name": "tp", "type": "uint192"},
                    {"internalType": "uint192", "name": "sl", "type": "uint192"},
                    {"internalType": "address", "name": "trader", "type": "address"},
                    {"internalType": "uint32", "name": "leverage", "type": "uint32"},
                    {"internalType": "uint16", "name": "pairIndex", "type": "uint16"},
                    {"internalType": "uint8", "name": "index", "type": "uint8"},
                    {"internalType": "bool", "name": "buy", "type": "bool"},
                    {"internalType": "bool", "name": "isDayTrade", "type": "bool"},
                ],
                "internalType": "struct IOstiumTradingStorage.Trade",
                "name": "t",
                "type": "tuple",
            },
            {
                "components": [
                    {"internalType": "address", "name": "builder", "type": "address"},
                    {"internalType": "uint32", "name": "builderFee", "type": "uint32"},
                ],
                "internalType": "struct IOstiumTradingStorage.BuilderFee",
                "name": "bf",
                "type": "tuple",
            },
            {"internalType": "enum IOstiumTradingStorage.OpenOrderType", "name": "orderType", "type": "uint8"},
            {"internalType": "uint256", "name": "slippageP", "type": "uint256"},
        ],
        "name": "openTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint16", "name": "pairIndex", "type": "uint16"},
            {"internalType": "uint8", "name": "index", "type": "uint8"},
            {"internalType": "uint16", "name": "closePercentage", "type": "uint16"},
            {"internalType": "uint192", "name": "marketPrice", "type": "uint192"},
            {"internalType": "uint32", "name": "slippageP", "type": "uint32"},
        ],
        "name": "closeTradeMarket",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

PAIR_QUERY = """
query GetPairs {
  pairs(orderBy: id, orderDirection: asc, subgraphError: allow) {
    id
    from
    to
    maxLeverage
    overnightMaxLeverage
    takerFeeP
    group { id name maxLeverage }
  }
}
"""

OPEN_TRADES_QUERY = """
query GetTraderOpenTrades($trader: String!, $skip: Int!, $first: Int!) {
  trades(
    where: { isOpen: true, trader: $trader }
    skip: $skip
    first: $first
    orderBy: timestamp
    orderDirection: desc
  ) {
    id
    tradeID
    trader
    isOpen
    isBuy
    isDayTrade
    index
    collateral
    leverage
    openPrice
    timestamp
    pair { id from to group { id name } }
  }
}
"""

ORDERS_BY_TX_QUERY = """
query GetOrders($txHashes: [String!]!, $skip: Int!, $first: Int!) {
  orders(
    where: { initiatedTx_in: $txHashes }
    skip: $skip
    first: $first
    orderBy: initiatedAt
    orderDirection: desc
  ) {
    id
    tradeID
    orderAction
    orderType
    isBuy
    isPending
    isCancelled
    cancelReason
    collateral
    leverage
    price
    priceAfterImpact
    initiatedTx
    initiatedBlock
    initiatedAt
    executedTx
    executedBlock
    executedAt
    pair { id from to group { id name } }
  }
}
"""
