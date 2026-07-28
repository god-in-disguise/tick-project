from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from tick_mvp.core.config import Settings
from tick_mvp.domain.states import TradeSide
from tick_mvp.venues.aark.pricing import estimate_open
from tick_mvp.venues.aark.public import AarkPublicClient
from tick_mvp.venues.aark.wallet import AarkWalletExecutor
from tick_mvp.venues.base import (
    TransactionPreparedHandler,
    VenueCloseResult,
    VenueOpenResult,
    VenueQuote,
)


class AarkVenue:
    name = "aark"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._public = AarkPublicClient(settings)
        self._wallet = AarkWalletExecutor(settings, self._public)

    def start(self) -> None:
        self._public.start()
        self._wallet.start()

    def stop(self) -> None:
        self._wallet.stop()
        self._public.stop()

    def supports_market(self, market: str) -> bool:
        return self._public.supports_market(market)

    def quote_open(
        self,
        *,
        market: str,
        side: TradeSide,
        ticket_usd: Decimal,
        leverage: Decimal,
        max_loss_usd: Decimal | None,
        take_profit_usd: Decimal | None,
    ) -> VenueQuote:
        row = self._public.market(market)
        return estimate_open(
            row,
            side=side,
            ticket_usd=ticket_usd,
            requested_leverage=leverage,
            max_loss_usd=max_loss_usd,
            take_profit_usd=take_profit_usd,
            execution_fee_usd=self._public.execution_fee_usd(),
            requires_open_challenge=not bool(self._settings.aark_partner_private_key),
            execution_enabled=self._settings.aark_real_execution_enabled,
        )

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
        take_profit_price: Decimal | None,
        on_transaction_prepared: TransactionPreparedHandler | None = None,
    ) -> VenueOpenResult:
        return self._wallet.open_position(
            private_key_hex=private_key_hex,
            market=self._public.market(market),
            side=side,
            ticket_usd=ticket_usd,
            leverage=leverage,
            quote_payload=quote_payload,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
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
        return self._wallet.close_position(
            private_key_hex=private_key_hex,
            market=self._public.market(market),
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
        ensure_transaction_gas: Callable[[], Any] | None = None,
    ) -> dict[str, Any]:
        return self._wallet.prepare_wallet(private_key_hex, required_collateral_usd)

    def markets(self, *, limit: int = 10) -> dict[str, Any]:
        return self._public.markets(limit=limit)

    def chart(self, market: str, *, window_seconds: int = 90) -> dict[str, Any]:
        return self._public.chart(market, window_seconds=window_seconds)

    def tape(self, market: str, *, since: int) -> dict[str, Any]:
        return self._public.tape(market, since=since)
