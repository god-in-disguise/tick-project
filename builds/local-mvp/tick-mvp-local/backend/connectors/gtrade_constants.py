from __future__ import annotations


ARBITRUM_CHAIN_ID = 42161
ARBITRUM_BACKEND = "https://backend-arbitrum.gains.trade"
ARBITRUM_BACKEND_WS = "wss://backend-arbitrum.gains.trade"
PRICING_REST = "https://backend-pricing.eu.gains.trade"
PRICING_WS = "wss://backend-pricing.eu.gains.trade"

DIAMOND_ARBITRUM = "0xFF162c694eAA571f685030649814282eA457f169"
USDC_ARBITRUM = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = (1 << 256) - 1

WATCHLIST_INDEXES = (300, 313, 314, 327, 452, 466, 0, 1, 33, 90, 91, 21, 22)
DEFAULT_PAIR = "BTCDEGEN-USD"

DISPLAY_NAMES = {
    "BTCDEGEN": ("BTC", "Bitcoin"),
    "ETHDEGEN": ("ETH", "Ethereum"),
    "SOLDEGEN": ("SOL", "Solana"),
    "BNBDEGEN": ("BNB", "BNB"),
    "HYPEDEGEN": ("HYPE", "Hyperliquid"),
    "ZECDEGEN": ("ZEC", "Zcash"),
    "BTC": ("BTC", "Bitcoin"),
    "ETH": ("ETH", "Ethereum"),
    "SOL": ("SOL", "Solana"),
    "XAU": ("XAU", "Gold"),
    "XAG": ("XAG", "Silver"),
    "EUR": ("EURUSD", "Euro Dollar"),
    "USD": ("USDJPY", "Dollar Yen"),
}

COMMODITY_SYMBOLS = {"XAU", "XAG", "WTI", "XPT", "XPD", "HG"}
FX_PAIR_PREFIXES = {"EUR", "USD", "GBP", "AUD", "CAD", "JPY", "NZD", "CHF", "CNH", "SGD"}

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "remaining", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "_spender", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "success", "type": "bool"}],
        "type": "function",
    },
]

TRADE_FIELDS = [
    ("user", "address"),
    ("index", "uint32"),
    ("pairIndex", "uint16"),
    ("leverage", "uint24"),
    ("long", "bool"),
    ("isOpen", "bool"),
    ("collateralIndex", "uint8"),
    ("tradeType", "uint8"),
    ("collateralAmount", "uint120"),
    ("openPrice", "uint64"),
    ("tp", "uint64"),
    ("sl", "uint64"),
    ("isCounterTrade", "bool"),
    ("positionSizeToken", "uint160"),
    ("__placeholder", "uint24"),
]

TRADING_ABI = [
    {
        "inputs": [
            {
                "components": [{"name": name, "type": typ} for name, typ in TRADE_FIELDS],
                "name": "trade",
                "type": "tuple",
            },
            {"name": "maxSlippageP", "type": "uint16"},
            {"name": "referrer", "type": "address"},
        ],
        "name": "openTrade",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "_index", "type": "uint32"},
            {"name": "_expectedPrice", "type": "uint64"},
        ],
        "name": "closeTradeMarket",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

MARKET_EXECUTED_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {
                "components": [
                    {"name": "user", "type": "address"},
                    {"name": "index", "type": "uint32"},
                ],
                "indexed": False,
                "name": "orderId",
                "type": "tuple",
            },
            {"indexed": False, "name": "user", "type": "address"},
            {"indexed": False, "name": "index", "type": "uint32"},
            {
                "components": [{"name": name, "type": typ} for name, typ in TRADE_FIELDS],
                "indexed": False,
                "name": "t",
                "type": "tuple",
            },
            {"indexed": False, "name": "open", "type": "bool"},
            {"indexed": False, "name": "oraclePrice", "type": "uint256"},
            {"indexed": False, "name": "marketPrice", "type": "uint256"},
            {"indexed": False, "name": "liqPrice", "type": "uint256"},
            {"indexed": False, "name": "priceImpactP", "type": "uint256"},
            {"indexed": False, "name": "percentProfit", "type": "int256"},
            {"indexed": False, "name": "amountSentToTrader", "type": "uint256"},
            {"indexed": False, "name": "collateralPriceUsd", "type": "uint256"},
        ],
        "name": "MarketExecuted",
        "type": "event",
    }
]

DELEGATE_ABI = [
    {
        "inputs": [{"name": "delegate", "type": "address"}],
        "name": "setTradingDelegate",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"name": "trader", "type": "address"}],
        "name": "getTradingDelegate",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "trader", "type": "address"},
            {"name": "callData", "type": "bytes"},
        ],
        "name": "delegatedTradingAction",
        "outputs": [{"name": "", "type": "bytes"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]
