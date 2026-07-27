from __future__ import annotations

from decimal import Decimal
from typing import Any

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.base import TransactionPreparedHandler, VenueCloseResult, VenueOpenResult, VenueQuote
from tick_mvp.venues.gtrade.pricing import estimate_open
from tick_mvp.venues.gtrade.public import GTradePublicClient
from tick_mvp.venues.gtrade.wallet import GTradeWalletExecutor


class GTradeVenue:
    name = "gtrade"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._public = GTradePublicClient(settings)
        self._wallet = GTradeWalletExecutor(settings, self._public)

    def start(self) -> None:
        self._public.start()
        self._wallet.start()

    def stop(self) -> None:
        self._wallet.stop()
        self._public.stop()

    def quote_open(
        self,
        *,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        max_loss_usd: Decimal | None,
    ) -> VenueQuote:
        pair = self._public.pair(market)
        live = self._public.price(pair.pair)
        return estimate_open(pair, live, side, ticket_usd, leverage, max_loss_usd)

    def open_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        quote_payload: dict[str, Any],
        stop_loss_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueOpenResult:
        pair = self._public.pair(market)
        return self._wallet.open_position(
            private_key_hex=private_key_hex,
            pair=pair,
            side=side,
            ticket_usd=ticket_usd,
            leverage=leverage,
            quote_payload=quote_payload,
            stop_loss_price=stop_loss_price,
            on_transaction_prepared=on_transaction_prepared,
        )

    def close_position(
        self,
        *,
        private_key_hex: str,
        market: str,
        side: TradeSide,
        venue_position_id: str | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueCloseResult:
        pair = self._public.pair(market)
        return self._wallet.close_position(
            private_key_hex=private_key_hex,
            pair=pair,
            side=side,
            venue_position_id=venue_position_id,
            on_transaction_prepared=on_transaction_prepared,
        )

    def collateral_balance_usd(self, *, private_key_hex: str) -> Decimal:
        return self._wallet.collateral_balance_usd(private_key_hex)

    def prepare_wallet(
        self,
        *,
        private_key_hex: str,
        required_collateral_usd: Decimal,
    ) -> dict[str, Any]:
        return self._wallet.prepare_wallet(private_key_hex, required_collateral_usd)
