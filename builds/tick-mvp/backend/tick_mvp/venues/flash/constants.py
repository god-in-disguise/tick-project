from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
FLASH_PROGRAM_ID = "FLASH6Lo6h3iasJKWDs2F8TkW2UKf3s15C8PMGuVfgBn"
SOLANA_MAINNET_CHAIN_ID = 501
USD_DECIMALS = 6
STATE_HEDGE_SECONDS = 0.75
STATE_POLL_SECONDS = 0.10
STATE_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True, slots=True)
class FlashMarket:
    market: str
    symbol: str
    name: str
    asset_class: str
    max_leverage: Decimal
    maintenance_leverage: Decimal
    execution_certified: bool

    @property
    def min_position_size_usd(self) -> Decimal:
        # Flash enforces its small-ticket floor on input collateral rather
        # than one fixed notional across every supported leverage.
        return Decimal(0)

    @property
    def min_collateral_usd(self) -> Decimal:
        return Decimal("10")


MARKETS = {
    row.market: row
    for row in (
        FlashMarket("FLASH-BTC-USD", "BTC", "Bitcoin", "CRYPTO", Decimal("500"), Decimal("500"), True),
        FlashMarket("FLASH-ETH-USD", "ETH", "Ethereum", "CRYPTO", Decimal("500"), Decimal("500"), True),
        # SOL accepted quotes but missed the bounded execution window twice.
        FlashMarket("FLASH-SOL-USD", "SOL", "Solana", "CRYPTO", Decimal("500"), Decimal("500"), False),
        # Flash documents 100x maximum initial leverage and a 200x maintenance
        # threshold for the synthetic pool. A live XAU 200x transaction was
        # rejected by the program with TokenRatioOutOfRange (6022).
        FlashMarket("FLASH-XAU-USD", "XAU", "Gold", "COMMODITY", Decimal("100"), Decimal("200"), False),
        FlashMarket("FLASH-XAG-USD", "XAG", "Silver", "COMMODITY", Decimal("100"), Decimal("200"), False),
        FlashMarket("FLASH-EUR-USD", "EUR", "Euro", "FOREX", Decimal("100"), Decimal("200"), False),
        FlashMarket("FLASH-GBP-USD", "GBP", "British Pound", "FOREX", Decimal("100"), Decimal("200"), False),
        FlashMarket("FLASH-CRUDEOIL-USD", "CRUDEOIL", "Crude Oil", "COMMODITY", Decimal("100"), Decimal("200"), False),
        FlashMarket("FLASH-USDJPY-USD", "USDJPY", "US Dollar / Yen", "FOREX", Decimal("100"), Decimal("200"), False),
        FlashMarket("FLASH-USDCNH-USD", "USDCNH", "US Dollar / Yuan", "FOREX", Decimal("100"), Decimal("200"), False),
    )
}


def market_config(market: str) -> FlashMarket:
    normalized = market.strip().upper()
    try:
        return MARKETS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported Flash market: {market}") from exc
