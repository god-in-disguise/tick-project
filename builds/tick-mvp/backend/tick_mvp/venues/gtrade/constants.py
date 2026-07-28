from __future__ import annotations

ARBITRUM_CHAIN_ID = 42161
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = (1 << 256) - 1

WATCHLIST_INDEXES = (300, 313, 314, 327, 452, 466, 0, 1, 33, 90, 91, 21, 22)

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

LIQUIDATION_PARAMS_FIELDS = [
    ("maxLiqSpreadP", "uint40"),
    ("startLiqThresholdP", "uint40"),
    ("endLiqThresholdP", "uint40"),
    ("startLeverage", "uint24"),
    ("endLeverage", "uint24"),
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
    {
        "inputs": [
            {
                "components": [
                    {"name": "collateralIndex", "type": "uint8"},
                    {"name": "trader", "type": "address"},
                    {"name": "pairIndex", "type": "uint16"},
                    {"name": "index", "type": "uint32"},
                    {"name": "openPrice", "type": "uint64"},
                    {"name": "long", "type": "bool"},
                    {"name": "collateral", "type": "uint256"},
                    {"name": "leverage", "type": "uint256"},
                    {"name": "additionalFeeCollateral", "type": "int256"},
                    {
                        "components": [
                            {"name": name, "type": typ}
                            for name, typ in LIQUIDATION_PARAMS_FIELDS
                        ],
                        "name": "liquidationParams",
                        "type": "tuple",
                    },
                    {"name": "currentPairPrice", "type": "uint64"},
                    {"name": "isCounterTrade", "type": "bool"},
                    {"name": "partialCloseMultiplier", "type": "uint256"},
                    {"name": "beforeOpened", "type": "bool"},
                ],
                "name": "_input",
                "type": "tuple",
            }
        ],
        "name": "getTradeLiquidationPrice",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

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
